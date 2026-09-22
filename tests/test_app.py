from __future__ import annotations

import sqlite3
from io import BytesIO
from urllib.parse import urlsplit

import pytest
from werkzeug.security import check_password_hash

from nexus_nutra import create_app
from nexus_nutra.db import get_db


def register(client, token, name, email, password, role, **extra):
    payload = {
        "csrf_token": token,
        "name": name,
        "email": email,
        "password": password,
        "role": role,
        "privacy_consent": "1",
    }
    payload.update(extra)
    return client.post("/cadastro", data=payload, follow_redirects=True)


def login(client, token, email, password):
    return client.post(
        "/login",
        data={"csrf_token": token, "email": email, "password": password},
        follow_redirects=True,
    )


def create_professional_with_patient(app, client, token):
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
        },
    )
    with app.app_context():
        db = get_db()
        nutritionist_id = db.execute(
            "SELECT id FROM users WHERE email = 'marina@example.com'"
        ).fetchone()["id"]
        patient_id = db.execute(
            "SELECT id FROM users WHERE email = 'joao@example.com'"
        ).fetchone()["id"]
    return logged_token, nutritionist_id, patient_id


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

    response = client.post(
        "/agenda",
        data={
            "csrf_token": logged_token,
            "patient_id": patient_id,
            "starts_at": "2099-10-01T10:00",
            "mode": "online",
            "meeting_url": "javascript:alert(1)",
        },
    )
    assert b"deve utilizar HTTPS" in response.data
    with app.app_context():
        assert get_db().execute("SELECT COUNT(*) FROM appointments").fetchone()[0] == 0


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


def test_versioned_migrations_create_security_foundation(app):
    with app.app_context():
        db = get_db()
        versions = {
            row["version"] for row in db.execute("SELECT version FROM schema_migrations")
        }
        appointment_columns = {
            row["name"] for row in db.execute("PRAGMA table_info(appointments)")
        }
        user_columns = {row["name"] for row in db.execute("PRAGMA table_info(users)")}
        assert versions == {1, 2, 3, 4, 5}
        assert {"duration_minutes", "reminder_minutes", "cancellation_reason"} <= appointment_columns
        assert {"failed_login_attempts", "locked_until", "session_version"} <= user_columns
        assert db.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'appointment_history'"
        ).fetchone()
        assert db.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'identity_tokens'"
        ).fetchone()


def test_secure_agenda_prevents_conflicts_and_exports_ics(app, client, token):
    logged_token, _nutritionist_id, patient_id = create_professional_with_patient(
        app, client, token
    )
    payload = {
        "csrf_token": logged_token,
        "patient_id": patient_id,
        "starts_at": "2099-10-01T10:00",
        "duration_minutes": "60",
        "reminder_minutes": "1440",
        "mode": "online",
        "meeting_url": "https://meet.example.com/consulta",
        "notes": "Retorno nutricional",
    }
    response = client.post("/agenda", data=payload, follow_redirects=True)
    assert b"Consulta agendada com sucesso" in response.data
    assert b"Fluxo rastre" in response.data

    response = client.post(
        "/agenda",
        data={**payload, "starts_at": "2099-10-01T10:30"},
        follow_redirects=True,
    )
    assert b"conflita com outra consulta" in response.data

    with app.app_context():
        db = get_db()
        appointment = db.execute("SELECT * FROM appointments").fetchone()
        appointment_id = appointment["id"]
        assert appointment["duration_minutes"] == 60
        assert appointment["meeting_url"].startswith("https://")
        assert db.execute(
            "SELECT COUNT(*) FROM appointment_history WHERE appointment_id = ?",
            (appointment_id,),
        ).fetchone()[0] == 1
        assert db.execute(
            "SELECT COUNT(*) FROM audit_log WHERE action = 'appointment.created'"
        ).fetchone()[0] == 1

    response = client.get(f"/agenda/{appointment_id}.ics")
    assert response.status_code == 200
    assert response.mimetype == "text/calendar"
    assert b"BEGIN:VCALENDAR" in response.data
    assert b"Consulta nutricional" in response.data


def test_appointment_transitions_and_reschedule_are_audited(app, client, token):
    logged_token, _nutritionist_id, patient_id = create_professional_with_patient(
        app, client, token
    )
    client.post(
        "/agenda",
        data={
            "csrf_token": logged_token,
            "patient_id": patient_id,
            "starts_at": "2099-11-10T09:00",
            "duration_minutes": "50",
            "mode": "in_person",
        },
    )
    with app.app_context():
        appointment_id = get_db().execute("SELECT id FROM appointments").fetchone()["id"]

    response = client.post(
        f"/agenda/{appointment_id}/status",
        data={"csrf_token": logged_token, "status": "confirmed"},
        follow_redirects=True,
    )
    assert b"marcada como confirmada" in response.data

    response = client.post(
        f"/agenda/{appointment_id}/reagendar",
        data={
            "csrf_token": logged_token,
            "starts_at": "2099-11-11T14:00",
            "reason": "Solicitacao do paciente",
        },
        follow_redirects=True,
    )
    assert b"enviada para nova confirma" in response.data

    with app.app_context():
        db = get_db()
        appointment = db.execute(
            "SELECT * FROM appointments WHERE id = ?", (appointment_id,)
        ).fetchone()
        events = db.execute(
            "SELECT event FROM appointment_history WHERE appointment_id = ? ORDER BY id",
            (appointment_id,),
        ).fetchall()
        assert appointment["status"] == "scheduled"
        assert appointment["starts_at"] == "2099-11-11T14:00"
        assert [event["event"] for event in events] == [
            "created",
            "status_changed",
            "rescheduled",
        ]


def test_schedule_block_prevents_appointment(app, client, token):
    logged_token, _nutritionist_id, patient_id = create_professional_with_patient(
        app, client, token
    )
    client.post(
        "/agenda/bloqueios",
        data={
            "csrf_token": logged_token,
            "starts_at": "2099-12-01T12:00",
            "ends_at": "2099-12-01T14:00",
            "reason": "Intervalo",
        },
    )
    response = client.post(
        "/agenda",
        data={
            "csrf_token": logged_token,
            "patient_id": patient_id,
            "starts_at": "2099-12-01T13:00",
            "duration_minutes": "30",
            "mode": "in_person",
        },
        follow_redirects=True,
    )
    assert b"conflita com outra consulta ou bloqueio" in response.data


def test_login_is_temporarily_locked_after_repeated_failures(client, token):
    register(
        client,
        token,
        "Marina Nutricionista",
        "marina@example.com",
        "senha-segura",
        "nutritionist",
        crn="CRN-6 12345",
    )
    for _attempt in range(5):
        response = login(client, token, "marina@example.com", "senha-incorreta")
        assert response.status_code == 200
    response = login(client, token, "marina@example.com", "senha-segura")
    assert response.status_code == 429
    assert b"temporariamente bloqueado" in response.data


def test_email_verification_uses_single_use_hashed_token(app, client, token):
    app.config["REQUIRE_EMAIL_VERIFICATION"] = True
    response = register(
        client,
        token,
        "Marina Nutricionista",
        "marina@example.com",
        "senha-segura",
        "nutritionist",
        crn="CRN-6 12345",
    )
    assert b"Enviamos um link para confirmar" in response.data
    message = app.extensions["mail_outbox"][-1]
    verification_url = next(
        line for line in message["body"].splitlines() if line.startswith("https://")
    )
    verification_path = urlsplit(verification_url).path
    raw_token = verification_path.rsplit("/", 1)[-1]

    with app.app_context():
        db = get_db()
        user = db.execute(
            "SELECT * FROM users WHERE email = 'marina@example.com'"
        ).fetchone()
        stored = db.execute(
            "SELECT token_hash FROM identity_tokens WHERE user_id = ?",
            (user["id"],),
        ).fetchone()["token_hash"]
        assert user["email_verified_at"] is None
        assert stored != raw_token
        assert len(stored) == 64

    blocked = login(client, token, "marina@example.com", "senha-segura")
    assert b"Reenviar confirma" in blocked.data

    verified = client.get(verification_path, follow_redirects=True)
    assert b"E-mail confirmado" in verified.data
    assert login(client, token, "marina@example.com", "senha-segura").status_code == 200
    assert client.get(verification_path).status_code == 400

    with app.app_context():
        db = get_db()
        assert db.execute(
            "SELECT email_verified_at FROM users WHERE email = 'marina@example.com'"
        ).fetchone()["email_verified_at"]
        assert db.execute(
            "SELECT COUNT(*) FROM audit_log WHERE action = 'identity.email_verified'"
        ).fetchone()[0] == 1


def test_password_reset_is_generic_single_use_and_revokes_sessions(app, client, token):
    register(
        client,
        token,
        "Marina Nutricionista",
        "marina@example.com",
        "senha-segura",
        "nutritionist",
        crn="CRN-6 12345",
    )
    app.extensions["mail_outbox"].clear()

    unknown = client.post(
        "/recuperar-senha",
        data={"csrf_token": token, "email": "inexistente@example.com"},
        follow_redirects=True,
    )
    assert b"Se houver uma conta ativa" in unknown.data
    assert app.extensions["mail_outbox"] == []

    other_client = app.test_client()
    other_client.get("/login")
    with other_client.session_transaction() as other_session:
        other_token = other_session["csrf_token"]
    login(other_client, other_token, "marina@example.com", "senha-segura")
    assert other_client.get("/dashboard").status_code == 200

    response = client.post(
        "/recuperar-senha",
        data={"csrf_token": token, "email": "marina@example.com"},
        follow_redirects=True,
    )
    assert b"Se houver uma conta ativa" in response.data
    reset_message = app.extensions["mail_outbox"][-1]
    reset_url = next(
        line for line in reset_message["body"].splitlines() if line.startswith("https://")
    )
    reset_path = urlsplit(reset_url).path
    raw_token = reset_path.rsplit("/", 1)[-1]

    with app.app_context():
        db = get_db()
        token_row = db.execute(
            "SELECT token_hash FROM identity_tokens WHERE purpose = 'reset_password'"
        ).fetchone()
        assert token_row["token_hash"] != raw_token

    reset_response = client.post(
        reset_path,
        data={
            "csrf_token": token,
            "password": "nova-senha-segura",
            "password_confirmation": "nova-senha-segura",
        },
        follow_redirects=True,
    )
    assert b"Senha redefinida" in reset_response.data
    assert client.get(reset_path).status_code == 400
    assert other_client.get("/dashboard", follow_redirects=False).status_code == 302

    with app.app_context():
        db = get_db()
        user = db.execute(
            "SELECT * FROM users WHERE email = 'marina@example.com'"
        ).fetchone()
        assert user["session_version"] == 2
        assert check_password_hash(user["password_hash"], "nova-senha-segura")
        assert db.execute(
            "SELECT COUNT(*) FROM audit_log WHERE action = 'identity.password_reset_completed'"
        ).fetchone()[0] == 1


def test_production_rejects_incomplete_identity_configuration(tmp_path, monkeypatch):
    monkeypatch.setenv("FLASK_ENV", "production")
    monkeypatch.delenv("SECRET_KEY", raising=False)
    monkeypatch.delenv("SMTP_HOST", raising=False)
    monkeypatch.setenv("PUBLIC_BASE_URL", "http://nutra.example.com")
    with pytest.raises(RuntimeError, match="Configuração de produção incompleta"):
        create_app({"DATABASE": str(tmp_path / "production.db")})


def test_clinical_record_preserves_versions_and_calculates_metrics(app, client, token):
    logged_token, nutritionist_id, patient_id = create_professional_with_patient(
        app, client, token
    )
    path = f"/pacientes/{patient_id}/prontuario"

    response = client.post(
        path + "/anamnese",
        data={
            "csrf_token": logged_token,
            "medical_history": "Hipertensão controlada",
            "allergies": "Amendoim",
            "water_intake_liters": "2,3",
        },
        follow_redirects=True,
    )
    assert b"vers\xc3\xa3o 1" in response.data
    client.post(
        path + "/anamnese",
        data={
            "csrf_token": logged_token,
            "medical_history": "Hipertensão controlada e acompanhada",
            "allergies": "Amendoim",
            "water_intake_liters": "2.5",
        },
    )
    response = client.post(
        path + "/avaliacoes",
        data={
            "csrf_token": logged_token,
            "assessed_on": "2026-09-17",
            "weight_kg": "70",
            "height_cm": "175",
            "waist_cm": "80",
            "hip_cm": "100",
            "bmi": "999",
            "body_fat_percent": "22",
        },
        follow_redirects=True,
    )
    assert b"c\xc3\xa1lculo autom\xc3\xa1tico de IMC" in response.data
    assert b"22.9" in response.data

    with app.app_context():
        db = get_db()
        anamneses = db.execute(
            "SELECT version, medical_history FROM anamnesis_versions ORDER BY version"
        ).fetchall()
        assessment = db.execute("SELECT * FROM anthropometric_assessments").fetchone()
        assert [(row["version"], row["medical_history"]) for row in anamneses] == [
            (1, "Hipertensão controlada"),
            (2, "Hipertensão controlada e acompanhada"),
        ]
        assert assessment["nutritionist_id"] == nutritionist_id
        assert assessment["bmi"] == 22.86
        assert assessment["waist_hip_ratio"] == 0.8
        assert db.execute(
            "SELECT COUNT(*) FROM audit_log WHERE action LIKE 'clinical.%'"
        ).fetchone()[0] == 3


def test_clinical_notes_consents_report_and_access_control(app, client, token):
    logged_token, _nutritionist_id, patient_id = create_professional_with_patient(
        app, client, token
    )
    path = f"/pacientes/{patient_id}/prontuario"
    client.post(
        path + "/notas",
        data={
            "csrf_token": logged_token,
            "note_type": "goal",
            "title": "Meta de curto prazo",
            "content": "Aumentar consumo de fibras durante quatro semanas.",
        },
    )
    client.post(
        path + "/consentimentos",
        data={
            "csrf_token": logged_token,
            "purpose": "Acompanhamento remoto",
            "policy_version": "2026.1",
            "status": "granted",
        },
    )
    report = client.get(path + "/relatorio")
    assert report.status_code == 200
    assert b"Marina Nutricionista" in report.data
    assert b"CRN-6 12345" in report.data
    assert b"Meta de curto prazo" in report.data
    assert b"IMC = peso" in report.data

    client.post("/logout", data={"csrf_token": logged_token})
    client.get("/login")
    with client.session_transaction() as session:
        patient_token = session["csrf_token"]
    login(client, patient_token, "joao@example.com", "senha-paciente")
    assert client.get(path).status_code == 403
    assert client.get(path + "/relatorio").status_code == 403


def test_clinical_attachment_validates_type_and_restricts_download(app, client, token):
    logged_token, _nutritionist_id, patient_id = create_professional_with_patient(
        app, client, token
    )
    path = f"/pacientes/{patient_id}/prontuario"
    rejected = client.post(
        path + "/anexos",
        data={
            "csrf_token": logged_token,
            "attachment": (BytesIO(b"not executable"), "laudo.exe"),
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert b"PDF, JPG ou PNG" in rejected.data

    accepted = client.post(
        path + "/anexos",
        data={
            "csrf_token": logged_token,
            "attachment": (BytesIO(b"%PDF-1.4 clinical"), "exame.pdf"),
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert b"Documento anexado" in accepted.data
    with app.app_context():
        attachment = get_db().execute("SELECT * FROM clinical_attachments").fetchone()
        assert attachment["original_name"] == "exame.pdf"
        assert attachment["stored_name"] != "exame.pdf"
        attachment_id = attachment["id"]
    downloaded = client.get(path + f"/anexos/{attachment_id}")
    assert downloaded.status_code == 200
    assert downloaded.data == b"%PDF-1.4 clinical"
    assert "attachment" in downloaded.headers["Content-Disposition"]


def test_original_icon_system_is_available_and_used(client):
    sprite = client.get("/static/img/nexus-icons.svg")
    home = client.get("/")
    assert sprite.status_code == 200
    assert sprite.data.count(b"<symbol") >= 25
    assert b'id="icon-dashboard"' in sprite.data
    assert b"nexus-icons.svg#icon-patients" in home.data


def test_nutrition_workspace_creates_custom_food_and_calculated_recipe(
    app, client, token
):
    logged_token, nutritionist_id, _patient_id = create_professional_with_patient(
        app, client, token
    )
    response = client.post(
        "/nutricao",
        data={
            "csrf_token": logged_token,
            "kind": "food",
            "name": "Pasta de castanha da casa",
            "category": "Oleaginosas",
            "household_measure": "1 colher (20 g)",
            "allergens": "castanhas",
            "calories": "600",
            "protein": "20",
            "carbs": "20",
            "fat": "50",
            "fiber": "8",
            "calcium": "100",
            "iron": "3",
            "sodium": "10",
            "saturated_fat": "8",
            "sugars": "5",
        },
        follow_redirects=True,
    )
    assert b"Alimento personalizado adicionado" in response.data

    with app.app_context():
        db = get_db()
        custom = db.execute(
            "SELECT * FROM foods WHERE name = 'Pasta de castanha da casa'"
        ).fetchone()
        banana = db.execute(
            "SELECT id FROM foods WHERE name = 'Banana prata, crua'"
        ).fetchone()
        assert custom["nutritionist_id"] == nutritionist_id
        assert custom["sodium"] == 10

    response = client.post(
        "/nutricao",
        data={
            "csrf_token": logged_token,
            "kind": "recipe",
            "recipe_name": "Creme energético da casa",
            "yield_g": "200",
            "servings": "2",
            "recipe_food_id[]": [str(banana["id"]), str(custom["id"])],
            "recipe_amount_g[]": ["100", "100"],
            "instructions": "Misturar e servir.",
        },
        follow_redirects=True,
    )
    assert b"Receita calculada" in response.data
    with app.app_context():
        db = get_db()
        recipe = db.execute(
            "SELECT * FROM recipes WHERE name = 'Creme energético da casa'"
        ).fetchone()
        catalog_food = db.execute(
            "SELECT * FROM foods WHERE recipe_id = ?", (recipe["id"],)
        ).fetchone()
        assert recipe["calories"] == 698
        assert recipe["servings"] == 2
        assert catalog_food["calories"] == 349
        assert catalog_food["household_measure"] == "1 porção (100 g)"
        assert "castanhas" in catalog_food["allergens"]
        assert db.execute(
            "SELECT COUNT(*) FROM recipe_items WHERE recipe_id = ?", (recipe["id"],)
        ).fetchone()[0] == 2


def test_plan_alerts_allergen_and_versions_revision(app, client, token):
    logged_token, _nutritionist_id, patient_id = create_professional_with_patient(
        app, client, token
    )
    client.post(
        f"/pacientes/{patient_id}/prontuario/anamnese",
        data={"csrf_token": logged_token, "allergies": "Glúten"},
    )
    with app.app_context():
        bread = get_db().execute(
            "SELECT id FROM foods WHERE name = 'Pão francês'"
        ).fetchone()

    def publish(title, model_id=None):
        suffix = f"?modelo={model_id}" if model_id else ""
        return client.post(
            f"/planos/novo/{patient_id}{suffix}",
            data={
                "csrf_token": logged_token,
                "title": title,
                "meal_name[]": ["Café da manhã"],
                "food_name[]": ["Pão francês"],
                "food_id[]": [str(bread["id"])],
                "amount_g[]": ["50"],
                "quantity[]": [""],
            },
            follow_redirects=True,
        )

    first = publish("Plano seguro v1")
    assert b"Alerta de alergia ou restri" in first.data
    assert b"gl\xc3\xbaten" in first.data
    with app.app_context():
        first_id = get_db().execute(
            "SELECT id FROM meal_plans WHERE title = 'Plano seguro v1'"
        ).fetchone()["id"]
    second = publish("Plano seguro v2", first_id)
    assert b"VERS\xc3\x83O 2" in second.data
    with app.app_context():
        db = get_db()
        revision = db.execute(
            "SELECT * FROM meal_plans WHERE title = 'Plano seguro v2'"
        ).fetchone()
        assert revision["revision_of"] == first_id
        assert revision["version_number"] == 2
        assert revision["sodium"] >= 0
