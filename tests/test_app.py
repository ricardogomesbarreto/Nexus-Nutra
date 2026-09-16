from __future__ import annotations

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
    assert client.get("/diario").status_code == 200
