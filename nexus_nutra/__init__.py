"""Application factory do Nexus Nutra."""

from __future__ import annotations

import os
import secrets
from datetime import timedelta
from pathlib import Path

from flask import Flask, g, render_template
from werkzeug.middleware.proxy_fix import ProxyFix

from .auth import bp as auth_bp
from .clinical import bp as clinical_bp
from .db import close_db, init_db
from .nutrition import bp as nutrition_bp
from .routes import bp


def create_app(test_config: dict | None = None) -> Flask:
    app = Flask(
        __name__,
        instance_relative_config=True,
        template_folder="../templates",
        static_folder="../static",
        static_url_path="/static",
    )
    environment = os.getenv("APP_ENV", os.getenv("FLASK_ENV", "development"))
    is_production = environment == "production"
    smtp_host = os.getenv("SMTP_HOST", "")
    trusted_hosts = [
        host.strip()
        for host in os.getenv("TRUSTED_HOSTS", "").split(",")
        if host.strip()
    ]
    app.config.from_mapping(
        APP_ENV=environment,
        SECRET_KEY=os.getenv("SECRET_KEY") or secrets.token_hex(32),
        DATABASE=os.getenv(
            "DATABASE_PATH", str(Path(app.instance_path) / "nexus_nutra.db")
        ),
        CLINICAL_UPLOAD_FOLDER=os.getenv(
            "CLINICAL_UPLOAD_FOLDER", str(Path(app.instance_path) / "clinical_uploads")
        ),
        DIARY_UPLOAD_FOLDER=os.getenv(
            "DIARY_UPLOAD_FOLDER", str(Path(app.instance_path) / "diary_uploads")
        ),
        MAX_CONTENT_LENGTH=5 * 1024 * 1024,
        MAX_FORM_MEMORY_SIZE=2 * 1024 * 1024,
        MAX_FORM_PARTS=100,
        TRUSTED_HOSTS=trusted_hosts or None,
        SESSION_COOKIE_NAME="__Host-nexus_session" if is_production else "nexus_session",
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=is_production,
        SESSION_REFRESH_EACH_REQUEST=False,
        PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
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

    proxy_hops = int(os.getenv("TRUSTED_PROXY_HOPS", "0"))
    if proxy_hops:
        app.wsgi_app = ProxyFix(
            app.wsgi_app,
            x_for=proxy_hops,
            x_proto=proxy_hops,
            x_host=proxy_hops,
            x_port=proxy_hops,
        )

    if is_production:
        missing = []
        if not os.getenv("SECRET_KEY"):
            missing.append("SECRET_KEY")
        elif len(os.environ["SECRET_KEY"]) < 32:
            missing.append("SECRET_KEY com pelo menos 32 caracteres aleatórios")
        if not trusted_hosts:
            missing.append("TRUSTED_HOSTS")
        if proxy_hops != 1:
            missing.append("TRUSTED_PROXY_HOPS=1")
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
    Path(app.config["CLINICAL_UPLOAD_FOLDER"]).mkdir(parents=True, exist_ok=True)
    Path(app.config["DIARY_UPLOAD_FOLDER"]).mkdir(parents=True, exist_ok=True)
    app.teardown_appcontext(close_db)
    app.register_blueprint(bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(clinical_bp)
    app.register_blueprint(nutrition_bp)

    with app.app_context():
        init_db()

    @app.before_request
    def prepare_security_context():
        g.csp_nonce = secrets.token_urlsafe(24)

    @app.after_request
    def security_headers(response):
        nonce = getattr(g, "csp_nonce", "")
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), geolocation=(), microphone=()"
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
        response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
        response.headers["X-Permitted-Cross-Domain-Policies"] = "none"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            f"script-src 'self' 'nonce-{nonce}'; "
            "style-src 'self' https://fonts.googleapis.com; "
            "font-src https://fonts.gstatic.com; "
            "img-src 'self' data:; connect-src 'self'; "
            "frame-ancestors 'none'; base-uri 'self'; form-action 'self'; object-src 'none'"
        )
        if g.get("user"):
            response.headers["Cache-Control"] = "private, no-store, max-age=0"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        if is_production:
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains"
            )
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
