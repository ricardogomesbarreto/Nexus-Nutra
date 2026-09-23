"""Rotas web do Nexus Nutra."""

from __future__ import annotations

import secrets
import sqlite3
import unicodedata
from datetime import date, datetime, timedelta, timezone
from functools import wraps
from pathlib import Path
from urllib.parse import urlparse

from flask import (
    Blueprint,
    Response,
    abort,
    current_app,
    flash,
    g,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
    url_for,
)
from werkzeug.security import generate_password_hash
from werkzeug.utils import secure_filename

from .db import get_db

bp = Blueprint("main", __name__)

NUTRIENT_FIELDS = (
    "calories",
    "protein",
    "carbs",
    "fat",
    "fiber",
    "calcium",
    "iron",
    "sodium",
    "saturated_fat",
    "sugars",
)
APPOINTMENT_STATUSES = {
    "scheduled": "Agendada",
    "confirmed": "Confirmada",
    "completed": "Concluída",
    "cancelled": "Cancelada",
    "no_show": "Não compareceu",
}
APPOINTMENT_TRANSITIONS = {
    "scheduled": {"confirmed", "cancelled"},
    "confirmed": {"completed", "cancelled", "no_show"},
    "completed": set(),
    "cancelled": set(),
    "no_show": set(),
}
WEEKDAYS = ("Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo")
ALLOWED_DIARY_PHOTOS = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}


def _csrf_token() -> str:
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_urlsafe(32)
    return session["csrf_token"]


@bp.app_context_processor
def inject_globals():
    return {
        "csrf_token": _csrf_token,
        "today": date.today().isoformat(),
        "appointment_statuses": APPOINTMENT_STATUSES,
        "weekdays": WEEKDAYS,
    }


@bp.app_template_filter("brdate")
def brdate(value: str | None) -> str:
    if not value:
        return "—"
    try:
        raw = value[:16]
        parsed = datetime.fromisoformat(raw)
        return parsed.strftime("%d/%m/%Y às %H:%M") if "T" in value else parsed.strftime("%d/%m/%Y")
    except (TypeError, ValueError):
        return value


@bp.before_app_request
def load_user_and_protect_forms():
    user_id = session.get("user_id")
    g.user = (
        get_db().execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if user_id
        else None
    )
    if g.user and session.get("session_version") != g.user["session_version"]:
        session.clear()
        g.user = None
    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        token = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token")
        if not token or not secrets.compare_digest(token, session.get("csrf_token", "")):
            abort(403)


def login_required(view):
    @wraps(view)
    def wrapped(**kwargs):
        if g.user is None:
            flash("Entre na sua conta para continuar.", "info")
            return redirect(url_for("auth.login", next=request.path))
        return view(**kwargs)

    return wrapped


def role_required(role: str):
    def decorator(view):
        @wraps(view)
        @login_required
        def wrapped(**kwargs):
            if g.user["role"] != role:
                abort(403)
            return view(**kwargs)

        return wrapped

    return decorator


def _safe_external_url(target: str | None) -> str:
    """Aceita apenas links HTTPS para proteger consultas online."""
    if not target:
        return ""
    parsed = urlparse(target.strip())
    return target.strip() if parsed.scheme == "https" and parsed.netloc else ""


def _audit(action: str, entity_type: str, entity_id: int | None, details: str = "") -> None:
    get_db().execute(
        """INSERT INTO audit_log (actor_id, action, entity_type, entity_id, details)
           VALUES (?, ?, ?, ?, ?)""",
        (g.user["id"] if g.user else None, action, entity_type, entity_id, details[:1000]),
    )


def _parse_local_datetime(value: str | None) -> datetime | None:
    try:
        return datetime.fromisoformat(value or "")
    except ValueError:
        return None


def _appointment_for_current_user(appointment_id: int):
    appointment = get_db().execute(
        """SELECT a.*, p.name AS patient_name, n.name AS nutritionist_name,
                  n.email AS nutritionist_email
           FROM appointments a
           JOIN users p ON p.id = a.patient_id
           JOIN users n ON n.id = a.nutritionist_id
           WHERE a.id = ?""",
        (appointment_id,),
    ).fetchone()
    if not appointment or g.user["id"] not in {
        appointment["nutritionist_id"],
        appointment["patient_id"],
    }:
        abort(404)
    return appointment


def _appointment_conflicts(
    nutritionist_id: int,
    starts_at: datetime,
    duration_minutes: int,
    exclude_id: int | None = None,
) -> bool:
    db = get_db()
    end_at = starts_at + timedelta(minutes=duration_minutes)
    rows = db.execute(
        """SELECT id, starts_at, duration_minutes FROM appointments
           WHERE nutritionist_id = ? AND status IN ('scheduled', 'confirmed')""",
        (nutritionist_id,),
    ).fetchall()
    for row in rows:
        if exclude_id and row["id"] == exclude_id:
            continue
        existing_start = _parse_local_datetime(row["starts_at"])
        if not existing_start:
            continue
        existing_end = existing_start + timedelta(minutes=row["duration_minutes"] or 50)
        if starts_at < existing_end and end_at > existing_start:
            return True
    blocks = db.execute(
        """SELECT starts_at, ends_at FROM schedule_blocks
           WHERE nutritionist_id = ?""",
        (nutritionist_id,),
    ).fetchall()
    return any(
        starts_at < block_end and end_at > block_start
        for block in blocks
        if (block_start := _parse_local_datetime(block["starts_at"]))
        and (block_end := _parse_local_datetime(block["ends_at"]))
    )


def _record_appointment_event(
    appointment_id: int,
    event: str,
    *,
    from_status: str | None = None,
    to_status: str | None = None,
    old_starts_at: str | None = None,
    new_starts_at: str | None = None,
    reason: str = "",
) -> None:
    get_db().execute(
        """INSERT INTO appointment_history
           (appointment_id, actor_id, event, from_status, to_status,
            old_starts_at, new_starts_at, reason)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            appointment_id,
            g.user["id"],
            event,
            from_status,
            to_status,
            old_starts_at,
            new_starts_at,
            reason[:500],
        ),
    )


def _patient_for_nutritionist(patient_id: int):
    return get_db().execute(
        """
        SELECT u.* FROM users u
        JOIN professional_patients pp ON pp.patient_id = u.id
        WHERE u.id = ? AND pp.nutritionist_id = ? AND pp.status = 'active'
        """,
        (patient_id, g.user["id"]),
    ).fetchone()


def _plan_for_current_user(plan_id: int):
    plan = get_db().execute(
        """SELECT mp.*, p.name AS patient_name, n.name AS nutritionist_name,
                  n.crn AS nutritionist_crn
           FROM meal_plans mp
           JOIN users p ON p.id = mp.patient_id
           JOIN users n ON n.id = mp.nutritionist_id
           WHERE mp.id = ?""",
        (plan_id,),
    ).fetchone()
    if not plan or g.user["id"] not in {plan["nutritionist_id"], plan["patient_id"]}:
        abort(404)
    return plan


def _plan_items(plan_id: int):
    return get_db().execute(
        """SELECT mi.*, f.category AS food_category,
                  f.household_measure, f.source AS food_source,
                  f.calories AS food_calories_100g, f.allergens AS food_allergens
           FROM meal_items mi
           LEFT JOIN foods f ON f.id = mi.food_id
           WHERE mi.plan_id = ? ORDER BY mi.id""",
        (plan_id,),
    ).fetchall()


def _normalized(value: str) -> str:
    return "".join(
        character
        for character in unicodedata.normalize("NFKD", value.lower())
        if not unicodedata.combining(character)
    )


def _plan_alerts(patient_id: int, items) -> list[dict[str, str]]:
    profile = get_db().execute(
        """SELECT allergies, intolerances, restrictions FROM anamnesis_versions
           WHERE patient_id = ? ORDER BY version DESC LIMIT 1""",
        (patient_id,),
    ).fetchone()
    if not profile:
        return []
    patient_context = _normalized(
        " ".join(str(profile[field] or "") for field in ("allergies", "intolerances", "restrictions"))
    )
    alerts = []
    for item in items:
        allergens = item["food_allergens"] if "food_allergens" in item.keys() else ""
        for allergen in (allergens or "").split(","):
            label = allergen.strip()
            if label and _normalized(label) in patient_context:
                alerts.append({"food": item["food_name"], "allergen": label})
    return alerts


def _can_contact(other_id: int) -> bool:
    if other_id == g.user["id"]:
        return False
    db = get_db()
    if g.user["role"] == "nutritionist":
        relation = db.execute(
            "SELECT 1 FROM professional_patients WHERE nutritionist_id = ? AND patient_id = ?",
            (g.user["id"], other_id),
        ).fetchone()
    else:
        relation = db.execute(
            "SELECT 1 FROM professional_patients WHERE patient_id = ? AND nutritionist_id = ?",
            (g.user["id"], other_id),
        ).fetchone()
    return relation is not None


@bp.get("/")
def index():
    return render_template("index.html")


@bp.get("/offline")
def offline():
    return render_template("offline.html")


@bp.get("/service-worker.js")
def service_worker():
    response = send_from_directory(
        Path(current_app.static_folder) / "js",
        "service-worker.js",
        mimetype="application/javascript",
    )
    response.headers["Service-Worker-Allowed"] = "/"
    response.headers["Cache-Control"] = "no-cache"
    return response


@bp.post("/perfil/sessoes/revogar")
@login_required
def revoke_other_sessions():
    db = get_db()
    new_version = g.user["session_version"] + 1
    db.execute(
        "UPDATE users SET session_version = ? WHERE id = ?",
        (new_version, g.user["id"]),
    )
    _audit("sessions.revoked", "user", g.user["id"])
    db.commit()
    session["session_version"] = new_version
    flash("Outras sessões foram revogadas. Este dispositivo permanece conectado.", "success")
    return redirect(url_for("main.profile"))


@bp.get("/dashboard")
@login_required
def dashboard():
    db = get_db()
    if g.user["role"] == "nutritionist":
        stats = db.execute(
            """
            SELECT
              COUNT(DISTINCT pp.patient_id) AS patients,
              COUNT(DISTINCT CASE WHEN date(a.starts_at) = date('now', 'localtime') AND a.status IN ('scheduled', 'confirmed') THEN a.id END) AS today_appointments,
              COUNT(DISTINCT CASE WHEN datetime(a.starts_at) >= datetime('now', 'localtime') AND a.status = 'scheduled' THEN a.id END) AS pending_confirmations,
              COUNT(DISTINCT CASE WHEN datetime(a.starts_at) > datetime('now', 'localtime') AND a.status IN ('scheduled', 'confirmed') AND datetime(a.starts_at, '-' || a.reminder_minutes || ' minutes') <= datetime('now', 'localtime') THEN a.id END) AS due_reminders,
              COUNT(DISTINCT CASE WHEN m.recipient_id = ? AND m.read_at IS NULL THEN m.id END) AS unread_messages,
              COUNT(DISTINCT CASE WHEN mp.active = 1 THEN mp.patient_id END) AS active_plans
            FROM professional_patients pp
            LEFT JOIN appointments a ON a.nutritionist_id = pp.nutritionist_id
            LEFT JOIN messages m ON m.recipient_id = pp.nutritionist_id
            LEFT JOIN meal_plans mp ON mp.nutritionist_id = pp.nutritionist_id
            WHERE pp.nutritionist_id = ? AND pp.status = 'active'
            """,
            (g.user["id"], g.user["id"]),
        ).fetchone()
        appointments = db.execute(
            """SELECT a.*, u.name AS patient_name FROM appointments a
               JOIN users u ON u.id = a.patient_id
               WHERE a.nutritionist_id = ?
                 AND date(a.starts_at) = date('now', 'localtime')
                 AND a.status IN ('scheduled', 'confirmed')
               ORDER BY a.starts_at LIMIT 8""",
            (g.user["id"],),
        ).fetchall()
        recent = db.execute(
            """SELECT u.id, u.name, u.goal,
                      (SELECT weight FROM weight_records WHERE patient_id = u.id ORDER BY recorded_on DESC LIMIT 1) AS weight
               FROM users u JOIN professional_patients pp ON pp.patient_id = u.id
               WHERE pp.nutritionist_id = ? ORDER BY pp.linked_at DESC LIMIT 5""",
            (g.user["id"],),
        ).fetchall()
        return render_template(
            "dashboard_nutritionist.html", stats=stats, appointments=appointments, recent=recent
        )

    plan = db.execute(
        """SELECT mp.*, u.name AS nutritionist_name FROM meal_plans mp
           JOIN users u ON u.id = mp.nutritionist_id
           WHERE mp.patient_id = ? AND mp.active = 1 ORDER BY mp.created_at DESC LIMIT 1""",
        (g.user["id"],),
    ).fetchone()
    weights = db.execute(
        "SELECT * FROM weight_records WHERE patient_id = ? ORDER BY recorded_on DESC LIMIT 8",
        (g.user["id"],),
    ).fetchall()
    appointments = db.execute(
        """SELECT a.*, u.name AS nutritionist_name FROM appointments a
           JOIN users u ON u.id = a.nutritionist_id
           WHERE a.patient_id = ? AND datetime(a.starts_at) >= datetime('now', '-1 day')
             AND a.status IN ('scheduled', 'confirmed')
           ORDER BY a.starts_at LIMIT 3""",
        (g.user["id"],),
    ).fetchall()
    diary_today = db.execute(
        "SELECT COUNT(*) AS total FROM food_diary WHERE patient_id = ? AND date(recorded_at) = date('now', 'localtime')",
        (g.user["id"],),
    ).fetchone()["total"]
    active_habits = db.execute(
        "SELECT COUNT(*) AS total FROM habit_goals WHERE patient_id = ? AND active = 1",
        (g.user["id"],),
    ).fetchone()["total"]
    week_start = (date.today() - timedelta(days=date.today().weekday())).isoformat()
    checkin_done = db.execute(
        "SELECT 1 FROM weekly_checkins WHERE patient_id = ? AND week_start = ?",
        (g.user["id"], week_start),
    ).fetchone() is not None
    return render_template(
        "dashboard_patient.html",
        plan=plan,
        weights=list(reversed(weights)),
        appointments=appointments,
        diary_today=diary_today,
        active_habits=active_habits,
        checkin_done=checkin_done,
    )


@bp.get("/catalogo/alimentos")
@role_required("nutritionist")
def food_catalog():
    search = request.args.get("q", "").strip()
    category = request.args.get("categoria", "").strip()
    clauses = ["active = 1", "(nutritionist_id IS NULL OR nutritionist_id = ?)"]
    params: list[str | int] = [g.user["id"]]
    if search:
        clauses.append("name LIKE ?")
        params.append(f"%{search}%")
    if category:
        clauses.append("category = ?")
        params.append(category)
    db = get_db()
    foods = db.execute(
        f"SELECT * FROM foods WHERE {' AND '.join(clauses)} ORDER BY category, name",
        params,
    ).fetchall()
    categories = db.execute(
        """SELECT DISTINCT category FROM foods
           WHERE active = 1 AND (nutritionist_id IS NULL OR nutritionist_id = ?)
           ORDER BY category""",
        (g.user["id"],),
    ).fetchall()
    return render_template(
        "food_catalog.html",
        foods=foods,
        categories=categories,
        search=search,
        selected_category=category,
    )


@bp.get("/pacientes")
@role_required("nutritionist")
def patients():
    search = request.args.get("q", "").strip()
    params = [g.user["id"]]
    where = ""
    if search:
        where = "AND (u.name LIKE ? OR u.email LIKE ?)"
        params.extend([f"%{search}%", f"%{search}%"])
    rows = get_db().execute(
        f"""SELECT u.*,
                   (SELECT weight FROM weight_records WHERE patient_id = u.id ORDER BY recorded_on DESC LIMIT 1) AS weight,
                   (SELECT COUNT(*) FROM meal_plans WHERE patient_id = u.id AND active = 1) AS has_plan
            FROM users u JOIN professional_patients pp ON pp.patient_id = u.id
            WHERE pp.nutritionist_id = ? AND pp.status = 'active' {where}
            ORDER BY u.name""",
        params,
    ).fetchall()
    return render_template("patients.html", patients=rows, search=search)


@bp.route("/pacientes/novo", methods=["GET", "POST"])
@role_required("nutritionist")
def new_patient():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        if len(name) < 3 or "@" not in email or not 12 <= len(password) <= 128:
            flash("Preencha nome, e-mail válido e senha inicial de 12 a 128 caracteres.", "error")
        else:
            db = get_db()
            try:
                cursor = db.execute(
                    """INSERT INTO users (name, email, password_hash, role, phone, birth_date, goal, height_cm)
                       VALUES (?, ?, ?, 'patient', ?, ?, ?, ?)""",
                    (
                        name,
                        email,
                        generate_password_hash(password),
                        request.form.get("phone", "").strip(),
                        request.form.get("birth_date") or None,
                        request.form.get("goal", "").strip(),
                        _number(request.form.get("height_cm")),
                    ),
                )
                db.execute(
                    "INSERT INTO professional_patients (nutritionist_id, patient_id) VALUES (?, ?)",
                    (g.user["id"], cursor.lastrowid),
                )
                db.commit()
                flash("Paciente cadastrado e vinculado ao seu consultório.", "success")
                return redirect(url_for("main.patient_detail", patient_id=cursor.lastrowid))
            except sqlite3.IntegrityError:
                flash("Já existe uma conta com esse e-mail.", "error")
    return render_template("patient_form.html")


@bp.get("/pacientes/<int:patient_id>")
@role_required("nutritionist")
def patient_detail(patient_id: int):
    patient = _patient_for_nutritionist(patient_id)
    if not patient:
        abort(404)
    db = get_db()
    plans = db.execute(
        "SELECT * FROM meal_plans WHERE patient_id = ? ORDER BY created_at DESC", (patient_id,)
    ).fetchall()
    weights = db.execute(
        "SELECT * FROM weight_records WHERE patient_id = ? ORDER BY recorded_on", (patient_id,)
    ).fetchall()
    diary = db.execute(
        "SELECT * FROM food_diary WHERE patient_id = ? ORDER BY recorded_at DESC LIMIT 8",
        (patient_id,),
    ).fetchall()
    habits = db.execute(
        """SELECT hg.*,
                  COALESCE((SELECT value FROM habit_logs hl WHERE hl.goal_id = hg.id
                            ORDER BY recorded_on DESC LIMIT 1), 0) AS latest_value
           FROM habit_goals hg WHERE hg.patient_id = ? AND hg.nutritionist_id = ?
             AND hg.active = 1 ORDER BY hg.created_at DESC""",
        (patient_id, g.user["id"]),
    ).fetchall()
    checkins = db.execute(
        """SELECT * FROM weekly_checkins WHERE patient_id = ?
           ORDER BY week_start DESC LIMIT 4""",
        (patient_id,),
    ).fetchall()
    comments = db.execute(
        """SELECT dc.* FROM diary_comments dc JOIN food_diary fd ON fd.id = dc.diary_id
           WHERE fd.patient_id = ? AND dc.nutritionist_id = ? ORDER BY dc.created_at""",
        (patient_id, g.user["id"]),
    ).fetchall()
    comments_by_diary = {}
    for comment in comments:
        comments_by_diary.setdefault(comment["diary_id"], []).append(comment)
    return render_template(
        "patient_detail.html",
        patient=patient,
        plans=plans,
        weights=weights,
        diary=diary,
        habits=habits,
        checkins=checkins,
        comments_by_diary=comments_by_diary,
    )


def _number(value, default=0.0) -> float:
    try:
        return max(0.0, float(str(value or "0").replace(",", ".")))
    except ValueError:
        return default


def _rating(value, default=3) -> int:
    return min(5, max(1, int(_number(value, default))))


def _diary_photo(upload):
    if not upload or not upload.filename:
        return None
    extension = Path(secure_filename(upload.filename)).suffix.lower()
    expected_mime = ALLOWED_DIARY_PHOTOS.get(extension)
    content = upload.read()
    signatures = {
        ".jpg": (b"\xff\xd8\xff",),
        ".jpeg": (b"\xff\xd8\xff",),
        ".png": (b"\x89PNG\r\n\x1a\n",),
        ".webp": (b"RIFF",),
    }
    valid_signature = any(content.startswith(value) for value in signatures.get(extension, ()))
    if extension == ".webp":
        valid_signature = valid_signature and len(content) >= 12 and content[8:12] == b"WEBP"
    if not expected_mime or not valid_signature or len(content) > 5 * 1024 * 1024:
        raise ValueError
    stored_name = f"{secrets.token_hex(24)}{extension}"
    return stored_name, expected_mime, content


@bp.route("/planos/novo/<int:patient_id>", methods=["GET", "POST"])
@role_required("nutritionist")
def new_plan(patient_id: int):
    patient = _patient_for_nutritionist(patient_id)
    if not patient:
        abort(404)
    db = get_db()
    foods_catalog = db.execute(
        """SELECT * FROM foods WHERE active = 1
           AND (nutritionist_id IS NULL OR nutritionist_id = ?)
           ORDER BY category, name""",
        (g.user["id"],),
    ).fetchall()
    clinical_profile = db.execute(
        """SELECT allergies, intolerances, restrictions FROM anamnesis_versions
           WHERE nutritionist_id = ? AND patient_id = ? ORDER BY version DESC LIMIT 1""",
        (g.user["id"], patient_id),
    ).fetchone()
    model = None
    model_items = []
    model_id = int(request.args.get("modelo", 0) or 0)
    if model_id:
        model = db.execute(
            "SELECT * FROM meal_plans WHERE id = ? AND nutritionist_id = ?",
            (model_id, g.user["id"]),
        ).fetchone()
        if model:
            model_items = _plan_items(model_id)
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        foods = request.form.getlist("food_name[]")
        if not title or not any(food.strip() for food in foods):
            flash("Informe o nome do plano e pelo menos um alimento.", "error")
        else:
            values = {
                field: request.form.getlist(f"{field}[]") for field in NUTRIENT_FIELDS
            }
            meal_names = request.form.getlist("meal_name[]")
            quantities = request.form.getlist("quantity[]")
            food_ids = request.form.getlist("food_id[]")
            amounts = request.form.getlist("amount_g[]")
            items = []
            totals = {field: 0.0 for field in NUTRIENT_FIELDS}
            for index, food in enumerate(foods):
                if not food.strip():
                    continue
                food_id = int(food_ids[index]) if index < len(food_ids) and food_ids[index].isdigit() else None
                amount_g = _number(amounts[index]) if index < len(amounts) else 0
                catalog_food = (
                    db.execute(
                        """SELECT * FROM foods WHERE id = ? AND active = 1
                           AND (nutritionist_id IS NULL OR nutritionist_id = ?)""",
                        (food_id, g.user["id"]),
                    ).fetchone()
                    if food_id
                    else None
                )
                if catalog_food and amount_g > 0:
                    factor = amount_g / 100
                    nutrient_values = {
                        field: round(catalog_food[field] * factor, 2)
                        for field in NUTRIENT_FIELDS
                    }
                    food_name = catalog_food["name"]
                    quantity = f"{amount_g:g} g"
                else:
                    nutrient_values = {
                        field: _number(values[field][index] if index < len(values[field]) else 0)
                        for field in NUTRIENT_FIELDS
                    }
                    food_name = food.strip()
                    quantity = (
                        quantities[index].strip()
                        if index < len(quantities) and quantities[index].strip()
                        else "1 porção"
                    )
                for field, value in nutrient_values.items():
                    totals[field] += value
                items.append(
                    (
                        meal_names[index].strip() if index < len(meal_names) else "Refeição",
                        food_name,
                        quantity,
                        nutrient_values,
                        catalog_food["id"] if catalog_food else None,
                        amount_g or None,
                    )
                )
            db.execute("UPDATE meal_plans SET active = 0 WHERE patient_id = ?", (patient_id,))
            nutrient_columns = ", ".join(NUTRIENT_FIELDS)
            target_columns = ", ".join(f"target_{field}" for field in NUTRIENT_FIELDS)
            placeholders = ", ".join("?" for _ in range(7 + len(NUTRIENT_FIELDS) * 2))
            revision_of = (model["revision_of"] or model["id"]) if model else None
            version_number = (model["version_number"] + 1) if model else 1
            cursor = db.execute(
                f"""INSERT INTO meal_plans
                    (nutritionist_id, patient_id, title, objective, guidance,
                     {nutrient_columns}, {target_columns}, revision_of, version_number)
                    VALUES ({placeholders})""",
                (
                    g.user["id"], patient_id, title,
                    request.form.get("objective", "").strip(),
                    request.form.get("guidance", "").strip(),
                    *[round(totals[field], 2) for field in NUTRIENT_FIELDS],
                    *[_number(request.form.get(f"target_{field}")) for field in NUTRIENT_FIELDS],
                    revision_of, version_number,
                ),
            )
            for meal_name, food, quantity, nutrients, food_id, amount_g in items:
                item_placeholders = ", ".join("?" for _ in range(6 + len(NUTRIENT_FIELDS)))
                db.execute(
                    f"""INSERT INTO meal_items
                        (plan_id, meal_name, food_name, quantity, {nutrient_columns},
                         food_id, amount_g)
                        VALUES ({item_placeholders})""",
                    (
                        cursor.lastrowid, meal_name, food, quantity,
                        *[nutrients[field] for field in NUTRIENT_FIELDS], food_id, amount_g,
                    ),
                )
            db.commit()
            flash("Plano alimentar criado e disponibilizado ao paciente.", "success")
            return redirect(url_for("main.plan_detail", plan_id=cursor.lastrowid))
    return render_template(
        "plan_form.html",
        patient=patient,
        foods_catalog=foods_catalog,
        foods_payload=[dict(food) for food in foods_catalog],
        model=model,
        model_items=model_items,
        clinical_profile=clinical_profile,
    )


@bp.get("/planos/<int:plan_id>")
@login_required
def plan_detail(plan_id: int):
    db = get_db()
    plan = _plan_for_current_user(plan_id)
    items = _plan_items(plan_id)
    meals = {}
    alternatives = {}
    for item in items:
        meals.setdefault(item["meal_name"], []).append(item)
        if item["food_category"]:
            alternatives[item["id"]] = db.execute(
                """SELECT name, household_measure FROM foods
                   WHERE category = ? AND id != ? AND active = 1
                     AND (nutritionist_id IS NULL OR nutritionist_id = ?)
                   ORDER BY ABS(calories - ?) LIMIT 2""",
                (
                    item["food_category"],
                    item["food_id"],
                    plan["nutritionist_id"],
                    item["food_calories_100g"],
                ),
            ).fetchall()
    progress = {
        field: round(plan[field] / plan[f"target_{field}"] * 100)
        if plan[f"target_{field}"]
        else None
        for field in NUTRIENT_FIELDS
    }
    return render_template(
        "plan_detail.html",
        plan=plan,
        meals=meals,
        alternatives=alternatives,
        progress=progress,
        alerts=_plan_alerts(plan["patient_id"], items),
    )


@bp.get("/planos/<int:plan_id>/imprimir")
@login_required
def print_plan(plan_id: int):
    plan = _plan_for_current_user(plan_id)
    items = _plan_items(plan_id)
    meals = {}
    for item in items:
        meals.setdefault(item["meal_name"], []).append(item)
    return render_template("plan_print.html", plan=plan, meals=meals)


@bp.route("/diario", methods=["GET", "POST"])
@role_required("patient")
def diary():
    db = get_db()
    if request.method == "POST":
        meal_name = request.form.get("meal_name", "").strip()
        description = request.form.get("description", "").strip()
        if not meal_name or not description:
            flash("Informe a refeição e o que foi consumido.", "error")
        else:
            try:
                photo = _diary_photo(request.files.get("photo"))
            except ValueError:
                flash("Envie uma foto JPG, PNG ou WebP válida de até 5 MB.", "error")
                return redirect(url_for("main.diary"))
            water_ml = min(10000, int(_number(request.form.get("water_ml"))))
            cursor = db.execute(
                """INSERT INTO food_diary
                   (patient_id, meal_name, description, adherence, hunger, mood,
                    satiety, water_ml, symptoms, photo_stored_name, photo_mime,
                    photo_size_bytes, recorded_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    g.user["id"], meal_name, description[:2000],
                    1 if request.form.get("adherence") == "1" else 0,
                    _rating(request.form.get("hunger")),
                    _rating(request.form.get("mood")),
                    _rating(request.form.get("satiety")),
                    water_ml,
                    request.form.get("symptoms", "").strip()[:500],
                    photo[0] if photo else None,
                    photo[1] if photo else None,
                    len(photo[2]) if photo else None,
                    request.form.get("recorded_at") or datetime.now().strftime("%Y-%m-%dT%H:%M"),
                ),
            )
            if photo:
                upload_path = Path(current_app.config["DIARY_UPLOAD_FOLDER"]) / photo[0]
                upload_path.write_bytes(photo[2])
            db.execute(
                """INSERT INTO audit_log (actor_id, action, entity_type, entity_id, details)
                   VALUES (?, 'journey.diary_created', 'food_diary', ?, ?)""",
                (g.user["id"], cursor.lastrowid, meal_name),
            )
            db.commit()
            flash("Refeição registrada no diário.", "success")
            return redirect(url_for("main.diary"))
    entries = db.execute(
        "SELECT * FROM food_diary WHERE patient_id = ? ORDER BY recorded_at DESC LIMIT 30",
        (g.user["id"],),
    ).fetchall()
    comments = db.execute(
        """SELECT dc.*, u.name AS nutritionist_name FROM diary_comments dc
           JOIN users u ON u.id = dc.nutritionist_id
           JOIN food_diary fd ON fd.id = dc.diary_id
           WHERE fd.patient_id = ? ORDER BY dc.created_at""",
        (g.user["id"],),
    ).fetchall()
    comments_by_diary = {}
    for comment in comments:
        comments_by_diary.setdefault(comment["diary_id"], []).append(comment)
    week_summary = db.execute(
        """SELECT COUNT(*) AS entries, COALESCE(SUM(water_ml), 0) AS water_ml,
                  COALESCE(ROUND(AVG(adherence) * 100), 0) AS adherence
           FROM food_diary WHERE patient_id = ?
             AND datetime(recorded_at) >= datetime('now', '-7 days')""",
        (g.user["id"],),
    ).fetchone()
    return render_template(
        "diary.html",
        entries=entries,
        comments_by_diary=comments_by_diary,
        week_summary=week_summary,
    )


@bp.get("/diario/<int:entry_id>/foto")
@login_required
def diary_photo(entry_id: int):
    db = get_db()
    entry = db.execute("SELECT * FROM food_diary WHERE id = ?", (entry_id,)).fetchone()
    if not entry or not entry["photo_stored_name"]:
        abort(404)
    allowed = entry["patient_id"] == g.user["id"]
    if g.user["role"] == "nutritionist":
        allowed = db.execute(
            """SELECT 1 FROM professional_patients
               WHERE nutritionist_id = ? AND patient_id = ? AND status = 'active'""",
            (g.user["id"], entry["patient_id"]),
        ).fetchone() is not None
    if not allowed:
        abort(404)
    response = send_from_directory(
        current_app.config["DIARY_UPLOAD_FOLDER"],
        entry["photo_stored_name"],
        mimetype=entry["photo_mime"],
        as_attachment=False,
    )
    response.headers["Cache-Control"] = "private, no-store"
    return response


@bp.post("/diario/<int:entry_id>/comentarios")
@role_required("nutritionist")
def diary_comment(entry_id: int):
    db = get_db()
    entry = db.execute(
        """SELECT fd.* FROM food_diary fd
           JOIN professional_patients pp ON pp.patient_id = fd.patient_id
           WHERE fd.id = ? AND pp.nutritionist_id = ? AND pp.status = 'active'""",
        (entry_id, g.user["id"]),
    ).fetchone()
    if not entry:
        abort(404)
    content = request.form.get("content", "").strip()
    if len(content) < 3:
        flash("Escreva um comentário com pelo menos 3 caracteres.", "error")
    else:
        cursor = db.execute(
            """INSERT INTO diary_comments (diary_id, nutritionist_id, content)
               VALUES (?, ?, ?)""",
            (entry_id, g.user["id"], content[:500]),
        )
        db.execute(
            """INSERT INTO audit_log (actor_id, action, entity_type, entity_id, details)
               VALUES (?, 'journey.diary_commented', 'diary_comment', ?, ?)""",
            (g.user["id"], cursor.lastrowid, f"diary:{entry_id}"),
        )
        db.commit()
        flash("Comentário enviado ao paciente.", "success")
    return redirect(url_for("main.patient_detail", patient_id=entry["patient_id"]) + "#diario")


@bp.get("/jornada")
@role_required("patient")
def journey():
    db = get_db()
    week_start = (date.today() - timedelta(days=date.today().weekday())).isoformat()
    goals = db.execute(
        """SELECT hg.*,
                  CASE WHEN hg.frequency = 'weekly'
                    THEN COALESCE((SELECT SUM(value) FROM habit_logs hl
                                   WHERE hl.goal_id = hg.id AND hl.recorded_on >= ?), 0)
                    ELSE COALESCE((SELECT value FROM habit_logs hl
                                   WHERE hl.goal_id = hg.id
                                     AND hl.recorded_on = date('now', 'localtime')), 0)
                  END
                  AS today_value
           FROM habit_goals hg WHERE hg.patient_id = ? AND hg.active = 1
           ORDER BY hg.created_at""",
        (week_start, g.user["id"]),
    ).fetchall()
    checkins = db.execute(
        """SELECT * FROM weekly_checkins WHERE patient_id = ?
           ORDER BY week_start DESC LIMIT 8""",
        (g.user["id"],),
    ).fetchall()
    current_checkin = next((item for item in checkins if item["week_start"] == week_start), None)
    summary = db.execute(
        """SELECT COUNT(*) AS diary_entries,
                  COALESCE(ROUND(AVG(mood), 1), 0) AS mood,
                  COALESCE(SUM(water_ml), 0) AS water_ml
           FROM food_diary WHERE patient_id = ?
             AND datetime(recorded_at) >= datetime('now', '-7 days')""",
        (g.user["id"],),
    ).fetchone()
    return render_template(
        "journey.html",
        goals=goals,
        checkins=checkins,
        current_checkin=current_checkin,
        summary=summary,
    )


@bp.post("/jornada/check-in")
@role_required("patient")
def save_checkin():
    db = get_db()
    week_start = (date.today() - timedelta(days=date.today().weekday())).isoformat()
    values = (
        _rating(request.form.get("energy")),
        _rating(request.form.get("sleep_quality")),
        _rating(request.form.get("confidence")),
        request.form.get("wins", "").strip()[:1000],
        request.form.get("challenges", "").strip()[:1000],
        request.form.get("support_needed", "").strip()[:1000],
    )
    db.execute(
        """INSERT INTO weekly_checkins
           (patient_id, week_start, energy, sleep_quality, confidence, wins,
            challenges, support_needed)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(patient_id, week_start) DO UPDATE SET
             energy = excluded.energy, sleep_quality = excluded.sleep_quality,
             confidence = excluded.confidence, wins = excluded.wins,
             challenges = excluded.challenges, support_needed = excluded.support_needed,
             updated_at = CURRENT_TIMESTAMP""",
        (g.user["id"], week_start, *values),
    )
    db.commit()
    flash("Check-in semanal salvo. Obrigado por compartilhar sua semana.", "success")
    return redirect(url_for("main.journey"))


@bp.post("/jornada/habitos/<int:goal_id>")
@role_required("patient")
def log_habit(goal_id: int):
    db = get_db()
    goal = db.execute(
        "SELECT * FROM habit_goals WHERE id = ? AND patient_id = ? AND active = 1",
        (goal_id, g.user["id"]),
    ).fetchone()
    if not goal:
        abort(404)
    value = _number(request.form.get("value"))
    if value < 0 or value > goal["target_value"] * 10:
        flash("Informe um valor válido para o hábito.", "error")
    else:
        db.execute(
            """INSERT INTO habit_logs (goal_id, patient_id, value, recorded_on, note)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(goal_id, recorded_on) DO UPDATE SET
                 value = excluded.value, note = excluded.note""",
            (
                goal_id, g.user["id"], value, date.today().isoformat(),
                request.form.get("note", "").strip()[:300],
            ),
        )
        db.commit()
        flash("Progresso do hábito atualizado.", "success")
    return redirect(url_for("main.journey"))


@bp.post("/pacientes/<int:patient_id>/habitos")
@role_required("nutritionist")
def create_habit(patient_id: int):
    patient = _patient_for_nutritionist(patient_id)
    if not patient:
        abort(404)
    title = request.form.get("title", "").strip()
    unit = request.form.get("unit", "").strip()
    target = _number(request.form.get("target_value"))
    frequency = request.form.get("frequency", "daily")
    if len(title) < 3 or not unit or target <= 0 or frequency not in {"daily", "weekly"}:
        flash("Informe título, meta, unidade e frequência válidos.", "error")
    else:
        db = get_db()
        cursor = db.execute(
            """INSERT INTO habit_goals
               (nutritionist_id, patient_id, title, target_value, unit, frequency)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (g.user["id"], patient_id, title[:120], target, unit[:30], frequency),
        )
        db.execute(
            """INSERT INTO audit_log (actor_id, action, entity_type, entity_id, details)
               VALUES (?, 'journey.habit_created', 'habit_goal', ?, ?)""",
            (g.user["id"], cursor.lastrowid, title[:120]),
        )
        db.commit()
        flash("Meta de hábito compartilhada com o paciente.", "success")
    return redirect(url_for("main.patient_detail", patient_id=patient_id) + "#habitos")


@bp.route("/evolucao", methods=["GET", "POST"])
@role_required("patient")
def progress():
    db = get_db()
    if request.method == "POST":
        weight = _number(request.form.get("weight"))
        recorded_on = request.form.get("recorded_on") or date.today().isoformat()
        if not 20 <= weight <= 400:
            flash("Informe um peso válido entre 20 e 400 kg.", "error")
        else:
            db.execute(
                """INSERT INTO weight_records (patient_id, weight, recorded_on, notes)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(patient_id, recorded_on) DO UPDATE SET weight = excluded.weight, notes = excluded.notes""",
                (g.user["id"], weight, recorded_on, request.form.get("notes", "").strip()),
            )
            db.commit()
            flash("Evolução atualizada.", "success")
            return redirect(url_for("main.progress"))
    records = db.execute(
        "SELECT * FROM weight_records WHERE patient_id = ? ORDER BY recorded_on",
        (g.user["id"],),
    ).fetchall()
    return render_template("progress.html", records=records)


@bp.route("/agenda", methods=["GET", "POST"])
@login_required
def agenda():
    db = get_db()
    if request.method == "POST":
        if g.user["role"] != "nutritionist":
            abort(403)
        patient_id = int(_number(request.form.get("patient_id")))
        starts_at = _parse_local_datetime(request.form.get("starts_at"))
        duration_minutes = int(
            _number(request.form.get("duration_minutes") or "50", 50)
        )
        duration_minutes = min(240, max(15, duration_minutes))
        mode = request.form.get("mode", "online")
        meeting_url = _safe_external_url(request.form.get("meeting_url"))
        if not _patient_for_nutritionist(patient_id) or not starts_at:
            flash("Selecione um paciente e uma data válida.", "error")
        elif starts_at <= datetime.now():
            flash("Escolha um horário futuro para a consulta.", "error")
        elif mode not in {"online", "in_person"}:
            flash("Selecione uma modalidade válida.", "error")
        elif mode == "online" and request.form.get("meeting_url") and not meeting_url:
            flash("O link da consulta online deve utilizar HTTPS.", "error")
        elif _appointment_conflicts(g.user["id"], starts_at, duration_minutes):
            flash("Este horário conflita com outra consulta ou bloqueio da agenda.", "error")
        else:
            cursor = db.execute(
                """INSERT INTO appointments
                   (nutritionist_id, patient_id, starts_at, mode, meeting_url, notes,
                    duration_minutes, reminder_minutes)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    g.user["id"],
                    patient_id,
                    starts_at.isoformat(timespec="minutes"),
                    mode,
                    meeting_url,
                    request.form.get("notes", "").strip(),
                    duration_minutes,
                    min(
                        10080,
                        max(
                            0,
                            int(
                                _number(
                                    request.form.get("reminder_minutes") or "1440",
                                    1440,
                                )
                            ),
                        ),
                    ),
                ),
            )
            _record_appointment_event(
                cursor.lastrowid,
                "created",
                to_status="scheduled",
                new_starts_at=starts_at.isoformat(timespec="minutes"),
            )
            _audit("appointment.created", "appointment", cursor.lastrowid)
            db.commit()
            flash("Consulta agendada com sucesso.", "success")
            return redirect(url_for("main.agenda"))
    if g.user["role"] == "nutritionist":
        appointments = db.execute(
            """SELECT a.*, u.name AS contact_name,
                      (SELECT COUNT(*) FROM appointment_history h WHERE h.appointment_id = a.id) AS history_count
               FROM appointments a JOIN users u ON u.id = a.patient_id
               WHERE a.nutritionist_id = ? ORDER BY a.starts_at""",
            (g.user["id"],),
        ).fetchall()
        patients_list = db.execute(
            """SELECT u.id, u.name FROM users u JOIN professional_patients pp ON pp.patient_id = u.id
               WHERE pp.nutritionist_id = ? ORDER BY u.name""",
            (g.user["id"],),
        ).fetchall()
        availability = db.execute(
            """SELECT * FROM availability_slots
               WHERE nutritionist_id = ? AND active = 1
               ORDER BY weekday, start_time""",
            (g.user["id"],),
        ).fetchall()
        blocks = db.execute(
            """SELECT * FROM schedule_blocks
               WHERE nutritionist_id = ? AND datetime(ends_at) >= datetime('now', 'localtime')
               ORDER BY starts_at LIMIT 20""",
            (g.user["id"],),
        ).fetchall()
    else:
        appointments = db.execute(
            """SELECT a.*, u.name AS contact_name,
                      (SELECT COUNT(*) FROM appointment_history h WHERE h.appointment_id = a.id) AS history_count
               FROM appointments a JOIN users u ON u.id = a.nutritionist_id
               WHERE a.patient_id = ? ORDER BY a.starts_at""",
            (g.user["id"],),
        ).fetchall()
        patients_list = []
        availability = []
        blocks = []
    history_rows = []
    selected_id = int(_number(request.args.get("historico")))
    if selected_id:
        _appointment_for_current_user(selected_id)
        history_rows = db.execute(
            """SELECT h.*, u.name AS actor_name FROM appointment_history h
               JOIN users u ON u.id = h.actor_id
               WHERE h.appointment_id = ? ORDER BY h.created_at DESC, h.id DESC""",
            (selected_id,),
        ).fetchall()
    return render_template(
        "agenda.html",
        appointments=appointments,
        patients=patients_list,
        availability=availability,
        blocks=blocks,
        history_rows=history_rows,
        selected_id=selected_id,
    )


@bp.post("/agenda/<int:appointment_id>/status")
@login_required
def update_appointment_status(appointment_id: int):
    appointment = _appointment_for_current_user(appointment_id)
    new_status = request.form.get("status", "")
    reason = request.form.get("reason", "").strip()
    allowed = APPOINTMENT_TRANSITIONS.get(appointment["status"], set())
    if new_status not in allowed:
        flash("Esta mudança de status não é permitida.", "error")
        return redirect(url_for("main.agenda"))
    if g.user["role"] == "patient" and new_status not in {"confirmed", "cancelled"}:
        abort(403)
    if new_status in {"cancelled", "no_show"} and len(reason) < 3:
        flash("Informe o motivo para registrar esta alteração.", "error")
        return redirect(url_for("main.agenda"))
    db = get_db()
    db.execute(
        """UPDATE appointments
           SET status = ?, cancellation_reason = ?, updated_at = CURRENT_TIMESTAMP
           WHERE id = ?""",
        (new_status, reason if new_status == "cancelled" else None, appointment_id),
    )
    _record_appointment_event(
        appointment_id,
        "status_changed",
        from_status=appointment["status"],
        to_status=new_status,
        reason=reason,
    )
    _audit(
        "appointment.status_changed",
        "appointment",
        appointment_id,
        f"{appointment['status']}->{new_status}",
    )
    db.commit()
    flash(f"Consulta marcada como {APPOINTMENT_STATUSES[new_status].lower()}.", "success")
    return redirect(url_for("main.agenda"))


@bp.post("/agenda/<int:appointment_id>/reagendar")
@login_required
def reschedule_appointment(appointment_id: int):
    appointment = _appointment_for_current_user(appointment_id)
    starts_at = _parse_local_datetime(request.form.get("starts_at"))
    reason = request.form.get("reason", "").strip()
    if appointment["status"] in {"completed", "cancelled", "no_show"}:
        flash("Consultas encerradas não podem ser reagendadas.", "error")
    elif not starts_at or starts_at <= datetime.now():
        flash("Escolha uma nova data futura.", "error")
    elif len(reason) < 3:
        flash("Informe o motivo do reagendamento.", "error")
    elif _appointment_conflicts(
        appointment["nutritionist_id"],
        starts_at,
        appointment["duration_minutes"],
        exclude_id=appointment_id,
    ):
        flash("O novo horário conflita com outra consulta ou bloqueio.", "error")
    else:
        db = get_db()
        new_value = starts_at.isoformat(timespec="minutes")
        db.execute(
            """UPDATE appointments
               SET starts_at = ?, status = 'scheduled', updated_at = CURRENT_TIMESTAMP
               WHERE id = ?""",
            (new_value, appointment_id),
        )
        _record_appointment_event(
            appointment_id,
            "rescheduled",
            from_status=appointment["status"],
            to_status="scheduled",
            old_starts_at=appointment["starts_at"],
            new_starts_at=new_value,
            reason=reason,
        )
        _audit("appointment.rescheduled", "appointment", appointment_id, reason)
        db.commit()
        flash("Consulta reagendada e enviada para nova confirmação.", "success")
    return redirect(url_for("main.agenda"))


@bp.get("/agenda/<int:appointment_id>.ics")
@login_required
def appointment_ics(appointment_id: int):
    appointment = _appointment_for_current_user(appointment_id)
    starts_at = _parse_local_datetime(appointment["starts_at"])
    if not starts_at:
        abort(404)
    ends_at = starts_at + timedelta(minutes=appointment["duration_minutes"] or 50)

    def escape_ics(value: str) -> str:
        return value.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")

    description = appointment["notes"] or "Consulta de acompanhamento nutricional"
    if appointment["meeting_url"]:
        description = f"{description}\n{appointment['meeting_url']}"
    content = "\r\n".join(
        (
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//Nexus Nutra//Agenda Segura//PT-BR",
            "CALSCALE:GREGORIAN",
            "BEGIN:VEVENT",
            f"UID:nexus-nutra-appointment-{appointment_id}@local",
            f"DTSTAMP:{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}",
            f"DTSTART:{starts_at.strftime('%Y%m%dT%H%M%S')}",
            f"DTEND:{ends_at.strftime('%Y%m%dT%H%M%S')}",
            "SUMMARY:Consulta nutricional — Nexus Nutra",
            f"DESCRIPTION:{escape_ics(description)}",
            f"STATUS:{'CANCELLED' if appointment['status'] == 'cancelled' else 'CONFIRMED'}",
            "END:VEVENT",
            "END:VCALENDAR",
            "",
        )
    )
    return Response(
        content,
        mimetype="text/calendar",
        headers={"Content-Disposition": f"attachment; filename=consulta-{appointment_id}.ics"},
    )


@bp.post("/agenda/disponibilidade")
@role_required("nutritionist")
def add_availability():
    weekday_value = request.form.get("weekday", "")
    weekday = int(weekday_value) if weekday_value.isdigit() else -1
    start_time = request.form.get("start_time", "")
    end_time = request.form.get("end_time", "")
    if weekday not in range(7) or not start_time or not end_time or start_time >= end_time:
        flash("Informe um dia e um intervalo de disponibilidade válido.", "error")
    else:
        db = get_db()
        try:
            cursor = db.execute(
                """INSERT INTO availability_slots
                   (nutritionist_id, weekday, start_time, end_time)
                   VALUES (?, ?, ?, ?)""",
                (g.user["id"], weekday, start_time, end_time),
            )
            _audit("availability.created", "availability", cursor.lastrowid)
            db.commit()
            flash("Disponibilidade semanal adicionada.", "success")
        except sqlite3.IntegrityError:
            flash("Este intervalo já está cadastrado.", "info")
    return redirect(url_for("main.agenda"))


@bp.post("/agenda/disponibilidade/<int:slot_id>/remover")
@role_required("nutritionist")
def remove_availability(slot_id: int):
    db = get_db()
    cursor = db.execute(
        "DELETE FROM availability_slots WHERE id = ? AND nutritionist_id = ?",
        (slot_id, g.user["id"]),
    )
    if cursor.rowcount:
        _audit("availability.removed", "availability", slot_id)
        db.commit()
        flash("Disponibilidade removida.", "success")
    return redirect(url_for("main.agenda"))


@bp.post("/agenda/bloqueios")
@role_required("nutritionist")
def add_schedule_block():
    starts_at = _parse_local_datetime(request.form.get("starts_at"))
    ends_at = _parse_local_datetime(request.form.get("ends_at"))
    if not starts_at or not ends_at or ends_at <= starts_at:
        flash("Informe um intervalo de bloqueio válido.", "error")
    else:
        db = get_db()
        cursor = db.execute(
            """INSERT INTO schedule_blocks (nutritionist_id, starts_at, ends_at, reason)
               VALUES (?, ?, ?, ?)""",
            (
                g.user["id"],
                starts_at.isoformat(timespec="minutes"),
                ends_at.isoformat(timespec="minutes"),
                request.form.get("reason", "").strip(),
            ),
        )
        _audit("schedule_block.created", "schedule_block", cursor.lastrowid)
        db.commit()
        flash("Período bloqueado na agenda.", "success")
    return redirect(url_for("main.agenda"))


@bp.post("/agenda/bloqueios/<int:block_id>/remover")
@role_required("nutritionist")
def remove_schedule_block(block_id: int):
    db = get_db()
    cursor = db.execute(
        "DELETE FROM schedule_blocks WHERE id = ? AND nutritionist_id = ?",
        (block_id, g.user["id"]),
    )
    if cursor.rowcount:
        _audit("schedule_block.removed", "schedule_block", block_id)
        db.commit()
        flash("Bloqueio removido da agenda.", "success")
    return redirect(url_for("main.agenda"))


@bp.route("/chat", methods=["GET"])
@bp.route("/chat/<int:contact_id>", methods=["GET", "POST"])
@login_required
def chat(contact_id: int | None = None):
    db = get_db()
    if g.user["role"] == "nutritionist":
        contacts = db.execute(
            """SELECT u.id, u.name, u.email FROM users u JOIN professional_patients pp ON pp.patient_id = u.id
               WHERE pp.nutritionist_id = ? ORDER BY u.name""",
            (g.user["id"],),
        ).fetchall()
    else:
        contacts = db.execute(
            """SELECT u.id, u.name, u.email FROM users u JOIN professional_patients pp ON pp.nutritionist_id = u.id
               WHERE pp.patient_id = ?""",
            (g.user["id"],),
        ).fetchall()
    if contact_id is None and contacts:
        return redirect(url_for("main.chat", contact_id=contacts[0]["id"]))
    contact = next((row for row in contacts if row["id"] == contact_id), None)
    if contact_id and (not contact or not _can_contact(contact_id)):
        abort(404)
    if request.method == "POST":
        body = request.form.get("body", "").strip()
        if body:
            db.execute(
                "INSERT INTO messages (sender_id, recipient_id, body) VALUES (?, ?, ?)",
                (g.user["id"], contact_id, body[:2000]),
            )
            db.commit()
        return redirect(url_for("main.chat", contact_id=contact_id))
    messages = []
    if contact:
        messages = db.execute(
            """SELECT * FROM messages
               WHERE (sender_id = ? AND recipient_id = ?) OR (sender_id = ? AND recipient_id = ?)
               ORDER BY created_at""",
            (g.user["id"], contact_id, contact_id, g.user["id"]),
        ).fetchall()
        db.execute(
            "UPDATE messages SET read_at = CURRENT_TIMESTAMP WHERE sender_id = ? AND recipient_id = ? AND read_at IS NULL",
            (contact_id, g.user["id"]),
        )
        db.commit()
    return render_template("chat.html", contacts=contacts, contact=contact, messages=messages)


@bp.route("/perfil", methods=["GET", "POST"])
@login_required
def profile():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if len(name) < 3:
            flash("Informe um nome válido.", "error")
        else:
            db = get_db()
            db.execute(
                """UPDATE users SET name = ?, phone = ?, birth_date = ?, goal = ?, height_cm = ?, crn = ?
                   WHERE id = ?""",
                (
                    name,
                    request.form.get("phone", "").strip(),
                    request.form.get("birth_date") or None,
                    request.form.get("goal", "").strip(),
                    _number(request.form.get("height_cm")) or None,
                    request.form.get("crn", "").strip() or None,
                    g.user["id"],
                ),
            )
            db.commit()
            flash("Perfil atualizado.", "success")
            return redirect(url_for("main.profile"))
    return render_template("profile.html")
