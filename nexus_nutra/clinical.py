"""Prontuário clínico versionado e restrito ao nutricionista responsável."""

from __future__ import annotations

import secrets
from datetime import date
from pathlib import Path

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    g,
    redirect,
    render_template,
    request,
    send_from_directory,
    url_for,
)
from werkzeug.utils import secure_filename

from .db import get_db
from .routes import role_required

bp = Blueprint("clinical", __name__, url_prefix="/pacientes/<int:patient_id>/prontuario")

ANAMNESIS_FIELDS = (
    "medical_history",
    "family_history",
    "dietary_history",
    "activity_history",
    "allergies",
    "intolerances",
    "preferences",
    "restrictions",
    "medications",
    "supplements",
    "symptoms",
    "sleep_notes",
    "bowel_habits",
)
MEASUREMENT_FIELDS = (
    "waist_cm",
    "abdomen_cm",
    "hip_cm",
    "arm_cm",
    "thigh_cm",
    "calf_cm",
    "body_fat_percent",
    "muscle_mass_kg",
    "visceral_fat",
)
ALLOWED_ATTACHMENTS = {
    ".pdf": "application/pdf",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
}


def _has_valid_signature(extension: str, content: bytes) -> bool:
    signatures = {
        ".pdf": (b"%PDF-",),
        ".jpg": (b"\xff\xd8\xff",),
        ".jpeg": (b"\xff\xd8\xff",),
        ".png": (b"\x89PNG\r\n\x1a\n",),
    }
    return any(content.startswith(signature) for signature in signatures.get(extension, ()))


def _patient(patient_id: int):
    patient = get_db().execute(
        """SELECT u.* FROM users u
           JOIN professional_patients pp ON pp.patient_id = u.id
           WHERE u.id = ? AND pp.nutritionist_id = ? AND pp.status = 'active'""",
        (patient_id, g.user["id"]),
    ).fetchone()
    if not patient:
        abort(404)
    return patient


def _positive_number(value: str | None, required: bool = False) -> float | None:
    raw = (value or "").strip().replace(",", ".")
    if not raw:
        if required:
            raise ValueError
        return None
    number = float(raw)
    if number <= 0:
        raise ValueError
    return number


def _audit(action: str, entity_type: str, entity_id: int, details: str = "") -> None:
    get_db().execute(
        """INSERT INTO audit_log (actor_id, action, entity_type, entity_id, details)
           VALUES (?, ?, ?, ?, ?)""",
        (g.user["id"], action, entity_type, entity_id, details[:1000]),
    )


def _record_data(patient_id: int) -> dict:
    db = get_db()
    params = (g.user["id"], patient_id)
    return {
        "anamnesis": db.execute(
            """SELECT a.*, u.name AS author_name FROM anamnesis_versions a
               JOIN users u ON u.id = a.created_by
               WHERE a.nutritionist_id = ? AND a.patient_id = ?
               ORDER BY a.version DESC LIMIT 1""",
            params,
        ).fetchone(),
        "assessments": db.execute(
            """SELECT a.*, u.name AS author_name FROM anthropometric_assessments a
               JOIN users u ON u.id = a.created_by
               WHERE a.nutritionist_id = ? AND a.patient_id = ?
               ORDER BY a.assessed_on DESC, a.id DESC""",
            params,
        ).fetchall(),
        "notes": db.execute(
            """SELECT n.*, u.name AS author_name FROM clinical_notes n
               JOIN users u ON u.id = n.author_id
               WHERE n.nutritionist_id = ? AND n.patient_id = ?
               ORDER BY n.created_at DESC, n.id DESC""",
            params,
        ).fetchall(),
        "consents": db.execute(
            """SELECT c.*, u.name AS author_name FROM clinical_consents c
               JOIN users u ON u.id = c.recorded_by
               WHERE c.nutritionist_id = ? AND c.patient_id = ?
               ORDER BY c.recorded_at DESC, c.id DESC""",
            params,
        ).fetchall(),
        "attachments": db.execute(
            """SELECT a.*, u.name AS author_name FROM clinical_attachments a
               JOIN users u ON u.id = a.uploaded_by
               WHERE a.nutritionist_id = ? AND a.patient_id = ?
               ORDER BY a.created_at DESC, a.id DESC""",
            params,
        ).fetchall(),
    }


@bp.get("")
@role_required("nutritionist")
def record(patient_id: int):
    patient = _patient(patient_id)
    return render_template(
        "clinical_record.html", patient=patient, today=date.today().isoformat(), **_record_data(patient_id)
    )


@bp.post("/anamnese")
@role_required("nutritionist")
def save_anamnesis(patient_id: int):
    _patient(patient_id)
    try:
        water = _positive_number(request.form.get("water_intake_liters"))
    except ValueError:
        flash("Informe o consumo de água com um número positivo.", "error")
        return redirect(url_for("clinical.record", patient_id=patient_id) + "#anamnese")
    db = get_db()
    version = db.execute(
        """SELECT COALESCE(MAX(version), 0) + 1 FROM anamnesis_versions
           WHERE nutritionist_id = ? AND patient_id = ?""",
        (g.user["id"], patient_id),
    ).fetchone()[0]
    values = [request.form.get(field, "").strip() for field in ANAMNESIS_FIELDS]
    placeholders = ", ".join("?" for _ in ANAMNESIS_FIELDS)
    cursor = db.execute(
        f"""INSERT INTO anamnesis_versions
            (nutritionist_id, patient_id, version, {', '.join(ANAMNESIS_FIELDS)},
             water_intake_liters, created_by)
            VALUES (?, ?, ?, {placeholders}, ?, ?)""",
        (g.user["id"], patient_id, version, *values, water, g.user["id"]),
    )
    _audit("clinical.anamnesis_created", "anamnesis", cursor.lastrowid, f"versao={version}")
    db.commit()
    flash(f"Anamnese salva como versão {version}. O histórico anterior foi preservado.", "success")
    return redirect(url_for("clinical.record", patient_id=patient_id) + "#anamnese")


@bp.post("/avaliacoes")
@role_required("nutritionist")
def add_assessment(patient_id: int):
    patient = _patient(patient_id)
    try:
        weight = _positive_number(request.form.get("weight_kg"), required=True)
        height = _positive_number(request.form.get("height_cm"), required=True)
        measurements = [_positive_number(request.form.get(field)) for field in MEASUREMENT_FIELDS]
    except (TypeError, ValueError):
        flash("Peso, altura e medidas devem ser números positivos.", "error")
        return redirect(url_for("clinical.record", patient_id=patient_id) + "#avaliacoes")
    assessed_on = request.form.get("assessed_on") or date.today().isoformat()
    try:
        date.fromisoformat(assessed_on)
    except ValueError:
        flash("Informe uma data de avaliação válida.", "error")
        return redirect(url_for("clinical.record", patient_id=patient_id) + "#avaliacoes")
    bmi = round(weight / ((height / 100) ** 2), 2)
    hip = measurements[2]
    waist_hip_ratio = round(measurements[0] / hip, 2) if measurements[0] and hip else None
    db = get_db()
    columns = ", ".join(MEASUREMENT_FIELDS)
    placeholders = ", ".join("?" for _ in MEASUREMENT_FIELDS)
    cursor = db.execute(
        f"""INSERT INTO anthropometric_assessments
            (nutritionist_id, patient_id, assessed_on, weight_kg, height_cm, bmi,
             {columns}, waist_hip_ratio, notes, created_by)
            VALUES (?, ?, ?, ?, ?, ?, {placeholders}, ?, ?, ?)""",
        (
            g.user["id"], patient_id, assessed_on, weight, height, bmi, *measurements,
            waist_hip_ratio, request.form.get("notes", "").strip(), g.user["id"],
        ),
    )
    if not patient["height_cm"]:
        db.execute("UPDATE users SET height_cm = ? WHERE id = ?", (height, patient_id))
    _audit("clinical.assessment_created", "assessment", cursor.lastrowid, f"imc={bmi}")
    db.commit()
    flash("Avaliação antropométrica registrada com cálculo automático de IMC.", "success")
    return redirect(url_for("clinical.record", patient_id=patient_id) + "#avaliacoes")


@bp.post("/notas")
@role_required("nutritionist")
def add_note(patient_id: int):
    _patient(patient_id)
    note_type = request.form.get("note_type", "evolution")
    title = request.form.get("title", "").strip()
    content = request.form.get("content", "").strip()
    if note_type not in {"evolution", "goal", "observation"} or not title or not content:
        flash("Preencha tipo, título e conteúdo da nota clínica.", "error")
        return redirect(url_for("clinical.record", patient_id=patient_id) + "#evolucao")
    db = get_db()
    cursor = db.execute(
        """INSERT INTO clinical_notes
           (nutritionist_id, patient_id, note_type, title, content, author_id)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (g.user["id"], patient_id, note_type, title, content, g.user["id"]),
    )
    _audit("clinical.note_created", "clinical_note", cursor.lastrowid, note_type)
    db.commit()
    flash("Registro clínico adicionado à linha do tempo.", "success")
    return redirect(url_for("clinical.record", patient_id=patient_id) + "#evolucao")


@bp.post("/consentimentos")
@role_required("nutritionist")
def add_consent(patient_id: int):
    _patient(patient_id)
    purpose = request.form.get("purpose", "").strip()
    policy_version = request.form.get("policy_version", "").strip()
    status = request.form.get("status", "pending")
    if not purpose or not policy_version or status not in {"granted", "revoked", "pending"}:
        flash("Preencha finalidade, versão e situação do consentimento.", "error")
        return redirect(url_for("clinical.record", patient_id=patient_id) + "#consentimentos")
    db = get_db()
    cursor = db.execute(
        """INSERT INTO clinical_consents
           (nutritionist_id, patient_id, purpose, policy_version, status, recorded_by)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (g.user["id"], patient_id, purpose, policy_version, status, g.user["id"]),
    )
    _audit("clinical.consent_recorded", "clinical_consent", cursor.lastrowid, status)
    db.commit()
    flash("Evento de consentimento registrado sem apagar o histórico.", "success")
    return redirect(url_for("clinical.record", patient_id=patient_id) + "#consentimentos")


@bp.post("/anexos")
@role_required("nutritionist")
def add_attachment(patient_id: int):
    _patient(patient_id)
    uploaded = request.files.get("attachment")
    original_name = secure_filename(uploaded.filename if uploaded else "")
    extension = Path(original_name).suffix.lower()
    expected_mime = ALLOWED_ATTACHMENTS.get(extension)
    if not uploaded or not original_name or not expected_mime or uploaded.mimetype != expected_mime:
        flash("Envie um arquivo PDF, JPG ou PNG válido de até 5 MB.", "error")
        return redirect(url_for("clinical.record", patient_id=patient_id) + "#anexos")
    content = uploaded.read()
    if (
        not content
        or len(content) > current_app.config["MAX_CONTENT_LENGTH"]
        or not _has_valid_signature(extension, content)
    ):
        flash("O arquivo não corresponde ao formato informado ou ultrapassa 5 MB.", "error")
        return redirect(url_for("clinical.record", patient_id=patient_id) + "#anexos")
    stored_name = f"{secrets.token_hex(20)}{extension}"
    upload_folder = Path(current_app.config["CLINICAL_UPLOAD_FOLDER"])
    upload_folder.mkdir(parents=True, exist_ok=True)
    (upload_folder / stored_name).write_bytes(content)
    db = get_db()
    cursor = db.execute(
        """INSERT INTO clinical_attachments
           (nutritionist_id, patient_id, original_name, stored_name, mime_type,
            size_bytes, uploaded_by)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            g.user["id"], patient_id, original_name, stored_name, expected_mime,
            len(content), g.user["id"],
        ),
    )
    _audit("clinical.attachment_uploaded", "clinical_attachment", cursor.lastrowid, original_name)
    db.commit()
    flash("Documento anexado ao prontuário com acesso restrito.", "success")
    return redirect(url_for("clinical.record", patient_id=patient_id) + "#anexos")


@bp.get("/anexos/<int:attachment_id>")
@role_required("nutritionist")
def download_attachment(patient_id: int, attachment_id: int):
    _patient(patient_id)
    attachment = get_db().execute(
        """SELECT * FROM clinical_attachments
           WHERE id = ? AND patient_id = ? AND nutritionist_id = ?""",
        (attachment_id, patient_id, g.user["id"]),
    ).fetchone()
    if not attachment:
        abort(404)
    return send_from_directory(
        current_app.config["CLINICAL_UPLOAD_FOLDER"],
        attachment["stored_name"],
        as_attachment=True,
        download_name=attachment["original_name"],
        mimetype=attachment["mime_type"],
    )


@bp.get("/relatorio")
@role_required("nutritionist")
def report(patient_id: int):
    patient = _patient(patient_id)
    return render_template(
        "clinical_report.html",
        patient=patient,
        generated_on=date.today().isoformat(),
        **_record_data(patient_id),
    )
