"""Application factory do Nexus Nutra."""

from __future__ import annotations

import os
import secrets
from datetime import timedelta
from pathlib import Path

from flask import Flask, render_template

from .auth import bp as auth_bp
from .db import close_db, init_db
from .routes import bp


def create_app(test_config: dict | None = None) -> Flask:
    app = Flask(
        __name__,
        instance_relative_config=True,
        template_folder="../templates",
        static_folder="../static",
        static_url_path="/static",
    )
    is_production = os.getenv("FLASK_ENV") == "production"
    smtp_host = os.getenv("SMTP_HOST", "")
    app.config.from_mapping(
        SECRET_KEY=os.getenv("SECRET_KEY") or secrets.token_hex(32),
        DATABASE=os.getenv(
            "DATABASE_PATH", str(Path(app.instance_path) / "nexus_nutra.db")
        ),
        MAX_CONTENT_LENGTH=5 * 1024 * 1024,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=is_production,
        PERMANENT_SESSION_LIFETIME=timedelta(hours=12),
        PUBLIC_BASE_URL=os.getenv("PUBLIC_BASE_URL", "http://127.0.0.1:5000"),
        REQUIRE_EMAIL_VERIFICATION=os.getenv("REQUIRE_EMAIL_VERIFICATION", "1") == "1",
        SMTP_HOST=smtp_host,
        SMTP_PORT=int(os.getenv("SMTP_PORT", "587")),
        SMTP_USERNAME=os.getenv("SMTP_USERNAME", ""),
        SMTP_PASSWORD=os.getenv("SMTP_PASSWORD", ""),
        SMTP_USE_TLS=os.getenv("SMTP_USE_TLS", "1") == "1",
        SMTP_USE_SSL=os.getenv("SMTP_USE_SSL", "0") == "1",
        SMTP_TIMEOUT=float(os.getenv("SMTP_TIMEOUT", "10")),
        MAIL_FROM=os.getenv("MAIL_FROM", "Nexus Nutra <noreply@example.com>"),
        MAIL_SUPPRESS_SEND=os.getenv(
            "MAIL_SUPPRESS_SEND", "0" if smtp_host else "1"
        )
        == "1",
        DEBUG=os.getenv("FLASK_DEBUG", "0") == "1",
    )

    if test_config:
        app.config.update(test_config)

    if is_production:
        missing = []
        if not os.getenv("SECRET_KEY"):
            missing.append("SECRET_KEY")
        if app.config["REQUIRE_EMAIL_VERIFICATION"] and not app.config["SMTP_HOST"]:
            missing.append("SMTP_HOST")
        if app.config["REQUIRE_EMAIL_VERIFICATION"] and app.config["MAIL_SUPPRESS_SEND"]:
            missing.append("MAIL_SUPPRESS_SEND=0")
        if not app.config["PUBLIC_BASE_URL"].startswith("https://"):
            missing.append("PUBLIC_BASE_URL com HTTPS")
        if missing:
            raise RuntimeError(
                "Configuração de produção incompleta: " + ", ".join(missing)
            )

    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    app.teardown_appcontext(close_db)
    app.register_blueprint(bp)
    app.register_blueprint(auth_bp)

    with app.app_context():
        init_db()

    @app.after_request
    def security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), geolocation=(), microphone=()"
        return response

    @app.errorhandler(403)
    def forbidden(_error):
        return render_template("error.html", code=403, message="Acesso não autorizado."), 403

    @app.errorhandler(404)
    def not_found(_error):
        return render_template("error.html", code=404, message="Página não encontrada."), 404

    @app.errorhandler(413)
    def too_large(_error):
        return render_template(
            "error.html", code=413, message="O arquivo enviado ultrapassa 5 MB."
        ), 413

    return app
