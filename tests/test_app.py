from __future__ import annotations

import sqlite3

from nexus_nutra import create_app
from nexus_nutra.db import get_db


def register(client, token, name, email, password, role, **extra):
    payload = {
        "csrf_token": token,
        "name": name,
        "email": email,
        "password": password,
        "role": role,
    }
    payload.update(extra)
    return client.post("/cadastro", data=payload, follow_redirects=True)


def login(client, token, email, password):
    return client.post(
        "/login",
        data={"csrf_token": token, "email": email, "password": password},
        follow_redirects=True,
    )


def test_home_and_security_headers(client):
    response = client.get("/")
    assert response.status_code == 200
    assert b"Nexus Nutra" in response.data
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "SAMEORIGIN"


def test_registration_login_and_role_dashboard(client, token):
    response = register(
        client,
        token,
        "Marina Nutricionista",
        "marina@example.com",
        "senha-segura",
        "nutritionist",
        crn="CRN-6 12345",
    )
    assert b"Conta criada com sucesso" in response.data

    response = login(client, token, "marina@example.com", "senha-segura")
    assert response.status_code == 200
    assert b"PAINEL PROFISSIONAL" in response.data
    assert b"Pacientes ativos" in response.data


def test_csrf_blocks_invalid_post(client):
    response = client.post(
        "/cadastro",
        data={"name": "Teste", "email": "teste@example.com", "password": "12345678"},
    )
    assert response.status_code == 403


def test_nutritionist_creates_patient_and_plan(app, client, token):
    register(
        client,
        token,
        "Marina Nutricionista",
        "marina@example.com",
        "senha-segura",
        "nutritionist",
        crn="CRN-6 12345",
    )
    login(client, token, "marina@example.com", "senha-segura")

    with client.session_transaction() as session:
        logged_token = session["csrf_token"]

    response = client.post(
        "/pacientes/novo",
        data={
            "csrf_token": logged_token,
            "name": "Joao Paciente",
            "email": "joao@example.com",
            "password": "senha-paciente",
            "goal": "Melhorar a composicao corporal",
            "height_cm": "175",
        },
        follow_redirects=True,
    )
    assert b"Joao Paciente" in response.data

    with app.app_context():
        patient = get_db().execute(
            "SELECT id FROM users WHERE email = ?", ("joao@example.com",)
        ).fetchone()
        patient_id = patient["id"]

    response = client.post(
        f"/planos/novo/{patient_id}",
        data={
            "csrf_token": logged_token,
            "title": "Plano inicial",
            "objective": "Reeducacao alimentar",
            "guidance": "Manter hidratacao.",
            "meal_name[]": ["Cafe da manha", "Almoco"],
            "food_name[]": ["Aveia", "Arroz integral"],
            "quantity[]": ["40 g", "100 g"],
            "calories[]": ["150", "130"],
            "protein[]": ["5", "3"],
            "carbs[]": ["27", "28"],
            "fat[]": ["3", "1"],
            "fiber[]": ["4", "2.5"],
            "calcium[]": ["20", "10"],
            "iron[]": ["1.5", "0.8"],
        },
        follow_redirects=True,
    )
    assert b"Plano alimentar criado" in response.data
    assert b"280" in response.data

    with app.app_context():
        plan = get_db().execute("SELECT * FROM meal_plans").fetchone()
        assert plan["calories"] == 280
        assert plan["protein"] == 8
        assert plan["fiber"] == 6.5

    client.post(
        "/agenda",
        data={
            "csrf_token": logged_token,
            "patient_id": patient_id,
            "starts_at": "2026-10-01T10:00",
            "mode": "online",
            "meeting_url": "javascript:alert(1)",
        },
    )
    with app.app_context():
        appointment = get_db().execute("SELECT * FROM appointments").fetchone()
        assert appointment["meeting_url"] == ""


def test_patient_cannot_open_professional_patient_list(client, token):
    register(
        client,
        token,
        "Joana Paciente",
        "joana@example.com",
        "senha-segura",
        "patient",
    )
    login(client, token, "joana@example.com", "senha-segura")
    assert client.get("/pacientes").status_code == 403
    assert client.get("/catalogo/alimentos").status_code == 403
    assert client.get("/diario").status_code == 200


def test_catalog_calculates_plan_and_generates_print_view(app, client, token):
    register(
        client,
        token,
        "Marina Nutricionista",
        "marina@example.com",
        "senha-segura",
        "nutritionist",
        crn="CRN-6 12345",
    )
    login(client, token, "marina@example.com", "senha-segura")
    with client.session_transaction() as session:
        logged_token = session["csrf_token"]

    client.post(
        "/pacientes/novo",
        data={
            "csrf_token": logged_token,
            "name": "Joao Paciente",
            "email": "joao@example.com",
            "password": "senha-paciente",
            "goal": "Melhorar a composicao corporal",
        },
    )
    with app.app_context():
        db = get_db()
        patient_id = db.execute(
            "SELECT id FROM users WHERE email = ?", ("joao@example.com",)
        ).fetchone()["id"]
        food = db.execute(
            "SELECT * FROM foods WHERE name = ?", ("Arroz integral, cozido",)
        ).fetchone()

    catalog_response = client.get("/catalogo/alimentos?q=Arroz")
    assert catalog_response.status_code == 200
    assert b"Arroz integral" in catalog_response.data
    assert b"BASE ALIMENTAR BRASILEIRA" in catalog_response.data

    response = client.post(
        f"/planos/novo/{patient_id}",
        data={
            "csrf_token": logged_token,
            "title": "Plano calculado",
            "objective": "Meta personalizada",
            "target_calories": "200",
            "target_protein": "10",
            "meal_name[]": ["Almoço"],
            "food_name[]": ["valor adulterado no cliente"],
            "food_id[]": [str(food["id"])],
            "amount_g[]": ["150"],
            "quantity[]": [""],
            "calories[]": ["9999"],
            "protein[]": ["9999"],
            "carbs[]": ["9999"],
            "fat[]": ["9999"],
            "fiber[]": ["9999"],
            "calcium[]": ["9999"],
            "iron[]": ["9999"],
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Plano alimentar criado" in response.data
    assert b"Reutilizar plano" in response.data

    with app.app_context():
        db = get_db()
        plan = db.execute("SELECT * FROM meal_plans").fetchone()
        item = db.execute("SELECT * FROM meal_items").fetchone()
        assert plan["calories"] == 186
        assert plan["protein"] == 3.9
        assert plan["target_calories"] == 200
        assert item["food_name"] == "Arroz integral, cozido"
        assert item["amount_g"] == 150
        plan_id = plan["id"]

    print_response = client.get(f"/planos/{plan_id}/imprimir")
    assert print_response.status_code == 200
    assert b"Imprimir ou salvar em PDF" in print_response.data
    assert b"CRN-6 12345" in print_response.data

    model_response = client.get(f"/planos/novo/{patient_id}?modelo={plan_id}")
    assert model_response.status_code == 200
    assert b"Modelo carregado" in model_response.data
    assert b"Arroz integral" in model_response.data


def test_v10_database_is_migrated_without_losing_schema(tmp_path):
    database = tmp_path / "legacy.db"
    connection = sqlite3.connect(database)
    connection.executescript(
        """
        CREATE TABLE meal_plans (
            id INTEGER PRIMARY KEY,
            nutritionist_id INTEGER NOT NULL,
            patient_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            objective TEXT,
            guidance TEXT,
            calories REAL NOT NULL DEFAULT 0,
            protein REAL NOT NULL DEFAULT 0,
            carbs REAL NOT NULL DEFAULT 0,
            fat REAL NOT NULL DEFAULT 0,
            fiber REAL NOT NULL DEFAULT 0,
            calcium REAL NOT NULL DEFAULT 0,
            iron REAL NOT NULL DEFAULT 0,
            active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE meal_items (
            id INTEGER PRIMARY KEY,
            plan_id INTEGER NOT NULL,
            meal_name TEXT NOT NULL,
            food_name TEXT NOT NULL,
            quantity TEXT NOT NULL,
            calories REAL NOT NULL DEFAULT 0,
            protein REAL NOT NULL DEFAULT 0,
            carbs REAL NOT NULL DEFAULT 0,
            fat REAL NOT NULL DEFAULT 0,
            fiber REAL NOT NULL DEFAULT 0,
            calcium REAL NOT NULL DEFAULT 0,
            iron REAL NOT NULL DEFAULT 0
        );
        """
    )
    connection.commit()
    connection.close()

    application = create_app(
        {"TESTING": True, "SECRET_KEY": "test-secret", "DATABASE": str(database)}
    )
    with application.app_context():
        db = get_db()
        plan_columns = {
            row["name"] for row in db.execute("PRAGMA table_info(meal_plans)")
        }
        item_columns = {
            row["name"] for row in db.execute("PRAGMA table_info(meal_items)")
        }
        assert "target_calories" in plan_columns
        assert {"food_id", "amount_g"} <= item_columns
        assert db.execute("SELECT COUNT(*) FROM foods").fetchone()[0] == 18
