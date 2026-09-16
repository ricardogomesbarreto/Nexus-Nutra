"""Rotas web do Nexus Nutra."""

from __future__ import annotations

import secrets
import sqlite3
from datetime import date, datetime
from functools import wraps
from urllib.parse import urlparse

from flask import (
    Blueprint,
    abort,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

from .db import get_db

bp = Blueprint("main", __name__)


def _csrf_token() -> str:
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_urlsafe(32)
    return session["csrf_token"]


@bp.app_context_processor
def inject_globals():
    return {"csrf_token": _csrf_token, "today": date.today().isoformat()}


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
    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        token = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token")
        if not token or not secrets.compare_digest(token, session.get("csrf_token", "")):
            abort(403)


def login_required(view):
    @wraps(view)
    def wrapped(**kwargs):
        if g.user is None:
            flash("Entre na sua conta para continuar.", "info")
            return redirect(url_for("main.login", next=request.path))
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


def _safe_next(target: str | None) -> str | None:
    if not target:
        return None
    parsed = urlparse(target)
    return target if not parsed.netloc and target.startswith("/") else None


def _safe_external_url(target: str | None) -> str:
    """Aceita apenas links HTTP(S) para consultas online."""
    if not target:
        return ""
    parsed = urlparse(target.strip())
    return target.strip() if parsed.scheme in {"http", "https"} and parsed.netloc else ""


def _patient_for_nutritionist(patient_id: int):
    return get_db().execute(
        """
        SELECT u.* FROM users u
        JOIN professional_patients pp ON pp.patient_id = u.id
        WHERE u.id = ? AND pp.nutritionist_id = ? AND pp.status = 'active'
        """,
        (patient_id, g.user["id"]),
    ).fetchone()


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


@bp.route("/cadastro", methods=["GET", "POST"])
def register():
    if g.user:
        return redirect(url_for("main.dashboard"))
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        role = request.form.get("role", "patient")
        crn = request.form.get("crn", "").strip() or None
        nutritionist_email = request.form.get("nutritionist_email", "").strip().lower()
        error = None
        if len(name) < 3:
            error = "Informe seu nome completo."
        elif "@" not in email:
            error = "Informe um e-mail válido."
        elif len(password) < 8:
            error = "A senha precisa ter pelo menos 8 caracteres."
        elif role not in {"nutritionist", "patient"}:
            error = "Selecione um perfil válido."
        elif role == "nutritionist" and not crn:
            error = "Informe o CRN para criar um perfil profissional."

        db = get_db()
        nutritionist = None
        if not error and role == "patient" and nutritionist_email:
            nutritionist = db.execute(
                "SELECT id FROM users WHERE email = ? AND role = 'nutritionist'",
                (nutritionist_email,),
            ).fetchone()
            if not nutritionist:
                error = "Nutricionista não encontrado com esse e-mail."
        if error:
            flash(error, "error")
        else:
            try:
                cursor = db.execute(
                    "INSERT INTO users (name, email, password_hash, role, crn) VALUES (?, ?, ?, ?, ?)",
                    (name, email, generate_password_hash(password), role, crn),
                )
                if nutritionist:
                    db.execute(
                        "INSERT INTO professional_patients (nutritionist_id, patient_id) VALUES (?, ?)",
                        (nutritionist["id"], cursor.lastrowid),
                    )
                db.commit()
                flash("Conta criada com sucesso. Agora você já pode entrar.", "success")
                return redirect(url_for("main.login"))
            except sqlite3.IntegrityError:
                flash("Este e-mail já está cadastrado.", "error")
    return render_template("register.html")


@bp.route("/login", methods=["GET", "POST"])
def login():
    if g.user:
        return redirect(url_for("main.dashboard"))
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = get_db().execute(
            "SELECT * FROM users WHERE email = ? AND active = 1", (email,)
        ).fetchone()
        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session["user_id"] = user["id"]
            session["csrf_token"] = secrets.token_urlsafe(32)
            return redirect(_safe_next(request.args.get("next")) or url_for("main.dashboard"))
        flash("E-mail ou senha incorretos.", "error")
    return render_template("login.html")


@bp.post("/logout")
@login_required
def logout():
    session.clear()
    flash("Sessão encerrada com segurança.", "success")
    return redirect(url_for("main.index"))


@bp.get("/dashboard")
@login_required
def dashboard():
    db = get_db()
    if g.user["role"] == "nutritionist":
        stats = db.execute(
            """
            SELECT
              COUNT(DISTINCT pp.patient_id) AS patients,
              COUNT(DISTINCT CASE WHEN date(a.starts_at) = date('now', 'localtime') THEN a.id END) AS today_appointments,
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
               WHERE a.nutritionist_id = ? AND a.starts_at >= datetime('now', '-1 day')
               ORDER BY a.starts_at LIMIT 5""",
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
           WHERE a.patient_id = ? AND a.starts_at >= datetime('now', '-1 day')
           ORDER BY a.starts_at LIMIT 3""",
        (g.user["id"],),
    ).fetchall()
    diary_today = db.execute(
        "SELECT COUNT(*) AS total FROM food_diary WHERE patient_id = ? AND date(recorded_at) = date('now', 'localtime')",
        (g.user["id"],),
    ).fetchone()["total"]
    return render_template(
        "dashboard_patient.html",
        plan=plan,
        weights=list(reversed(weights)),
        appointments=appointments,
        diary_today=diary_today,
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
        if len(name) < 3 or "@" not in email or len(password) < 8:
            flash("Preencha nome, e-mail válido e senha inicial de 8 caracteres.", "error")
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
    return render_template(
        "patient_detail.html", patient=patient, plans=plans, weights=weights, diary=diary
    )


def _number(value, default=0.0) -> float:
    try:
        return max(0.0, float(str(value or "0").replace(",", ".")))
    except ValueError:
        return default


@bp.route("/planos/novo/<int:patient_id>", methods=["GET", "POST"])
@role_required("nutritionist")
def new_plan(patient_id: int):
    patient = _patient_for_nutritionist(patient_id)
    if not patient:
        abort(404)
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        foods = request.form.getlist("food_name[]")
        if not title or not any(food.strip() for food in foods):
            flash("Informe o nome do plano e pelo menos um alimento.", "error")
        else:
            fields = ["calories", "protein", "carbs", "fat", "fiber", "calcium", "iron"]
            values = {field: request.form.getlist(f"{field}[]") for field in fields}
            meal_names = request.form.getlist("meal_name[]")
            quantities = request.form.getlist("quantity[]")
            items = []
            totals = {field: 0.0 for field in fields}
            for index, food in enumerate(foods):
                if not food.strip():
                    continue
                nutrient_values = {
                    field: _number(values[field][index] if index < len(values[field]) else 0)
                    for field in fields
                }
                for field, value in nutrient_values.items():
                    totals[field] += value
                items.append(
                    (
                        meal_names[index].strip() if index < len(meal_names) else "Refeição",
                        food.strip(),
                        quantities[index].strip() if index < len(quantities) else "1 porção",
                        nutrient_values,
                    )
                )
            db = get_db()
            db.execute("UPDATE meal_plans SET active = 0 WHERE patient_id = ?", (patient_id,))
            cursor = db.execute(
                """INSERT INTO meal_plans
                   (nutritionist_id, patient_id, title, objective, guidance, calories, protein, carbs, fat, fiber, calcium, iron)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    g.user["id"], patient_id, title,
                    request.form.get("objective", "").strip(),
                    request.form.get("guidance", "").strip(),
                    *[round(totals[field], 2) for field in fields],
                ),
            )
            for meal_name, food, quantity, nutrients in items:
                db.execute(
                    """INSERT INTO meal_items
                       (plan_id, meal_name, food_name, quantity, calories, protein, carbs, fat, fiber, calcium, iron)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (cursor.lastrowid, meal_name, food, quantity, *[nutrients[f] for f in fields]),
                )
            db.commit()
            flash("Plano alimentar criado e disponibilizado ao paciente.", "success")
            return redirect(url_for("main.plan_detail", plan_id=cursor.lastrowid))
    return render_template("plan_form.html", patient=patient)


@bp.get("/planos/<int:plan_id>")
@login_required
def plan_detail(plan_id: int):
    db = get_db()
    plan = db.execute(
        """SELECT mp.*, p.name AS patient_name, n.name AS nutritionist_name
           FROM meal_plans mp JOIN users p ON p.id = mp.patient_id JOIN users n ON n.id = mp.nutritionist_id
           WHERE mp.id = ?""",
        (plan_id,),
    ).fetchone()
    if not plan or (
        g.user["id"] not in {plan["nutritionist_id"], plan["patient_id"]}
    ):
        abort(404)
    items = db.execute(
        "SELECT * FROM meal_items WHERE plan_id = ? ORDER BY id", (plan_id,)
    ).fetchall()
    meals = {}
    for item in items:
        meals.setdefault(item["meal_name"], []).append(item)
    return render_template("plan_detail.html", plan=plan, meals=meals)


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
            db.execute(
                """INSERT INTO food_diary (patient_id, meal_name, description, adherence, hunger, recorded_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    g.user["id"], meal_name, description,
                    1 if request.form.get("adherence") == "1" else 0,
                    int(_number(request.form.get("hunger"), 3)),
                    request.form.get("recorded_at") or datetime.now().strftime("%Y-%m-%dT%H:%M"),
                ),
            )
            db.commit()
            flash("Refeição registrada no diário.", "success")
            return redirect(url_for("main.diary"))
    entries = db.execute(
        "SELECT * FROM food_diary WHERE patient_id = ? ORDER BY recorded_at DESC LIMIT 30",
        (g.user["id"],),
    ).fetchall()
    return render_template("diary.html", entries=entries)


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
        patient_id = int(request.form.get("patient_id", 0))
        if not _patient_for_nutritionist(patient_id) or not request.form.get("starts_at"):
            flash("Selecione um paciente e uma data válida.", "error")
        else:
            db.execute(
                """INSERT INTO appointments
                   (nutritionist_id, patient_id, starts_at, mode, meeting_url, notes)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    g.user["id"], patient_id, request.form["starts_at"],
                    request.form.get("mode", "online"),
                    _safe_external_url(request.form.get("meeting_url")),
                    request.form.get("notes", "").strip(),
                ),
            )
            db.commit()
            flash("Consulta agendada com sucesso.", "success")
            return redirect(url_for("main.agenda"))
    if g.user["role"] == "nutritionist":
        appointments = db.execute(
            """SELECT a.*, u.name AS contact_name FROM appointments a JOIN users u ON u.id = a.patient_id
               WHERE a.nutritionist_id = ? ORDER BY a.starts_at""",
            (g.user["id"],),
        ).fetchall()
        patients_list = db.execute(
            """SELECT u.id, u.name FROM users u JOIN professional_patients pp ON pp.patient_id = u.id
               WHERE pp.nutritionist_id = ? ORDER BY u.name""",
            (g.user["id"],),
        ).fetchall()
    else:
        appointments = db.execute(
            """SELECT a.*, u.name AS contact_name FROM appointments a JOIN users u ON u.id = a.nutritionist_id
               WHERE a.patient_id = ? ORDER BY a.starts_at""",
            (g.user["id"],),
        ).fetchall()
        patients_list = []
    return render_template("agenda.html", appointments=appointments, patients=patients_list)


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
