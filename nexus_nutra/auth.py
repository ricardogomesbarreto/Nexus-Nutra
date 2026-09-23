"""Autenticação e fluxos seguros de identidade do Nexus Nutra."""

from __future__ import annotations

import hashlib
import secrets
import sqlite3
from datetime import datetime, timedelta
from urllib.parse import urlparse

from flask import (
    Blueprint,
    current_app,
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
from .mailer import send_email

bp = Blueprint("auth", __name__)

PRIVACY_POLICY_VERSION = "2026-09"
TOKEN_PURPOSES = {"verify_email", "reset_password"}
MIN_PASSWORD_LENGTH = 12
MAX_PASSWORD_LENGTH = 128


def password_is_valid(password: str) -> bool:
    """Aceita frases-senha longas sem impor regras de composição frágeis."""
    return MIN_PASSWORD_LENGTH <= len(password) <= MAX_PASSWORD_LENGTH


def _safe_next(target: str | None) -> str | None:
    if not target:
        return None
    parsed = urlparse(target)
    return target if not parsed.netloc and target.startswith("/") else None


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _audit_identity(db, user_id: int, action: str, details: str = "") -> None:
    db.execute(
        """INSERT INTO audit_log (actor_id, action, entity_type, entity_id, details)
           VALUES (?, ?, 'user', ?, ?)""",
        (user_id, action, user_id, details[:1000]),
    )


def _issue_token(db, user_id: int, purpose: str, lifetime: timedelta) -> str:
    if purpose not in TOKEN_PURPOSES:
        raise ValueError("Finalidade de token inválida.")
    db.execute(
        """UPDATE identity_tokens SET used_at = CURRENT_TIMESTAMP
           WHERE user_id = ? AND purpose = ? AND used_at IS NULL""",
        (user_id, purpose),
    )
    token = secrets.token_urlsafe(32)
    expires_at = (datetime.now() + lifetime).isoformat(timespec="seconds")
    db.execute(
        """INSERT INTO identity_tokens (user_id, purpose, token_hash, expires_at)
           VALUES (?, ?, ?, ?)""",
        (user_id, purpose, _token_hash(token), expires_at),
    )
    return token


def _active_token(token: str, purpose: str):
    return get_db().execute(
        """SELECT t.*, u.email, u.name FROM identity_tokens t
           JOIN users u ON u.id = t.user_id
           WHERE t.token_hash = ? AND t.purpose = ? AND t.used_at IS NULL
             AND datetime(t.expires_at) > datetime('now', 'localtime')
             AND u.active = 1""",
        (_token_hash(token), purpose),
    ).fetchone()


def _public_link(endpoint: str, token: str) -> str:
    base_url = current_app.config["PUBLIC_BASE_URL"].rstrip("/")
    return f"{base_url}{url_for(endpoint, token=token)}"


def _within_request_limit(db, user_id: int, purpose: str) -> bool:
    total = db.execute(
        """SELECT COUNT(*) FROM identity_tokens
           WHERE user_id = ? AND purpose = ?
             AND datetime(created_at) >= datetime('now', '-1 hour')""",
        (user_id, purpose),
    ).fetchone()[0]
    return total < 3


def _send_verification(user) -> bool:
    db = get_db()
    if not _within_request_limit(db, user["id"], "verify_email"):
        return True
    token = _issue_token(db, user["id"], "verify_email", timedelta(hours=24))
    _audit_identity(db, user["id"], "identity.verification_requested")
    db.commit()
    link = _public_link("auth.verify_email", token)
    return send_email(
        user["email"],
        "Confirme seu e-mail — Nexus Nutra",
        (
            f"Olá, {user['name']}.\n\n"
            "Confirme seu e-mail para ativar sua conta no Nexus Nutra:\n"
            f"{link}\n\n"
            "O link expira em 24 horas e pode ser utilizado apenas uma vez. "
            "Se você não criou esta conta, ignore esta mensagem."
        ),
    )


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
        accepted_privacy = request.form.get("privacy_consent") == "1"
        error = None
        if len(name) < 3:
            error = "Informe seu nome completo."
        elif "@" not in email:
            error = "Informe um e-mail válido."
        elif not password_is_valid(password):
            error = "A senha precisa ter entre 12 e 128 caracteres."
        elif role not in {"nutritionist", "patient"}:
            error = "Selecione um perfil válido."
        elif role == "nutritionist" and not crn:
            error = "Informe o CRN para criar um perfil profissional."
        elif not accepted_privacy:
            error = "Aceite a Política de Privacidade para criar sua conta."

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
                    """INSERT INTO users
                       (name, email, password_hash, role, crn,
                        privacy_policy_version, privacy_accepted_at)
                       VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)""",
                    (
                        name,
                        email,
                        generate_password_hash(password),
                        role,
                        crn,
                        PRIVACY_POLICY_VERSION,
                    ),
                )
                if nutritionist:
                    db.execute(
                        "INSERT INTO professional_patients (nutritionist_id, patient_id) VALUES (?, ?)",
                        (nutritionist["id"], cursor.lastrowid),
                    )
                _audit_identity(db, cursor.lastrowid, "identity.account_created", role)
                db.commit()
                user = db.execute(
                    "SELECT * FROM users WHERE id = ?", (cursor.lastrowid,)
                ).fetchone()
                sent = _send_verification(user)
                if sent:
                    flash(
                        "Conta criada com sucesso. Enviamos um link para confirmar seu e-mail.",
                        "success",
                    )
                else:
                    flash(
                        "Conta criada, mas o e-mail de confirmação não pôde ser enviado. Solicite um novo link.",
                        "info",
                    )
                return redirect(url_for("auth.login"))
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
        db = get_db()
        user = db.execute(
            "SELECT * FROM users WHERE email = ? AND active = 1", (email,)
        ).fetchone()
        now = datetime.now()
        locked_until = (
            datetime.fromisoformat(user["locked_until"])
            if user and user["locked_until"]
            else None
        )
        if locked_until and locked_until > now:
            flash("Acesso temporariamente bloqueado. Tente novamente em alguns minutos.", "error")
            return render_template("login.html"), 429
        if user and check_password_hash(user["password_hash"], password):
            db.execute(
                "UPDATE users SET failed_login_attempts = 0, locked_until = NULL WHERE id = ?",
                (user["id"],),
            )
            db.commit()
            if (
                current_app.config["REQUIRE_EMAIL_VERIFICATION"]
                and not user["email_verified_at"]
            ):
                flash("Confirme seu e-mail antes de entrar.", "info")
                return redirect(url_for("auth.resend_verification", email=email))
            session.clear()
            session.permanent = True
            session["user_id"] = user["id"]
            session["session_version"] = user["session_version"]
            session["csrf_token"] = secrets.token_urlsafe(32)
            return redirect(_safe_next(request.args.get("next")) or url_for("main.dashboard"))
        if user:
            attempts = user["failed_login_attempts"] + 1
            lock_value = (
                (now + timedelta(minutes=15)).isoformat(timespec="seconds")
                if attempts >= 5
                else None
            )
            db.execute(
                "UPDATE users SET failed_login_attempts = ?, locked_until = ? WHERE id = ?",
                (attempts, lock_value, user["id"]),
            )
            db.commit()
        flash("E-mail ou senha incorretos.", "error")
    return render_template("login.html")


@bp.post("/logout")
def logout():
    if g.user is None:
        return redirect(url_for("auth.login"))
    session.clear()
    flash("Sessão encerrada com segurança.", "success")
    return redirect(url_for("main.index"))


@bp.route("/reenviar-verificacao", methods=["GET", "POST"])
def resend_verification():
    initial_email = request.args.get("email", "").strip().lower()
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        db = get_db()
        user = db.execute(
            "SELECT * FROM users WHERE email = ? AND active = 1", (email,)
        ).fetchone()
        if user and not user["email_verified_at"]:
            _send_verification(user)
        flash(
            "Se a conta estiver pendente, um novo link de confirmação será enviado.",
            "success",
        )
        return redirect(url_for("auth.login"))
    return render_template(
        "identity_request.html",
        mode="verification",
        initial_email=initial_email,
    )


@bp.get("/verificar-email/<token>")
def verify_email(token: str):
    record = _active_token(token, "verify_email")
    if not record:
        return render_template("identity_invalid.html", mode="verification"), 400
    db = get_db()
    db.execute(
        "UPDATE users SET email_verified_at = CURRENT_TIMESTAMP WHERE id = ?",
        (record["user_id"],),
    )
    db.execute(
        """UPDATE identity_tokens SET used_at = CURRENT_TIMESTAMP
           WHERE user_id = ? AND purpose = 'verify_email' AND used_at IS NULL""",
        (record["user_id"],),
    )
    _audit_identity(db, record["user_id"], "identity.email_verified")
    db.commit()
    flash("E-mail confirmado. Sua conta está pronta para uso.", "success")
    return redirect(url_for("auth.login"))


@bp.route("/recuperar-senha", methods=["GET", "POST"])
def request_password_reset():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        db = get_db()
        user = db.execute(
            "SELECT * FROM users WHERE email = ? AND active = 1", (email,)
        ).fetchone()
        if user and _within_request_limit(db, user["id"], "reset_password"):
            token = _issue_token(
                db, user["id"], "reset_password", timedelta(minutes=30)
            )
            _audit_identity(db, user["id"], "identity.password_reset_requested")
            db.commit()
            link = _public_link("auth.reset_password", token)
            send_email(
                user["email"],
                "Redefina sua senha — Nexus Nutra",
                (
                    f"Olá, {user['name']}.\n\n"
                    "Use o link abaixo para redefinir sua senha:\n"
                    f"{link}\n\n"
                    "O link expira em 30 minutos e pode ser usado apenas uma vez. "
                    "Se você não solicitou a alteração, ignore esta mensagem."
                ),
            )
        flash(
            "Se houver uma conta ativa com esse e-mail, enviaremos as instruções de recuperação.",
            "success",
        )
        return redirect(url_for("auth.login"))
    return render_template("identity_request.html", mode="reset", initial_email="")


@bp.route("/redefinir-senha/<token>", methods=["GET", "POST"])
def reset_password(token: str):
    record = _active_token(token, "reset_password")
    if not record:
        return render_template("identity_invalid.html", mode="reset"), 400
    if request.method == "POST":
        password = request.form.get("password", "")
        confirmation = request.form.get("password_confirmation", "")
        if not password_is_valid(password):
            flash("A nova senha precisa ter entre 12 e 128 caracteres.", "error")
        elif password != confirmation:
            flash("A confirmação da senha não corresponde.", "error")
        else:
            db = get_db()
            db.execute(
                """UPDATE users
                   SET password_hash = ?, session_version = session_version + 1,
                       failed_login_attempts = 0, locked_until = NULL
                   WHERE id = ?""",
                (generate_password_hash(password), record["user_id"]),
            )
            db.execute(
                """UPDATE identity_tokens SET used_at = CURRENT_TIMESTAMP
                   WHERE user_id = ? AND purpose = 'reset_password' AND used_at IS NULL""",
                (record["user_id"],),
            )
            _audit_identity(db, record["user_id"], "identity.password_reset_completed")
            db.commit()
            session.clear()
            flash("Senha redefinida. Entre novamente com sua nova senha.", "success")
            return redirect(url_for("auth.login"))
    return render_template("reset_password.html", token=token)
