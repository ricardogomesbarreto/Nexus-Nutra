"""Adaptador mínimo de e-mail transacional via SMTP."""

from __future__ import annotations

import smtplib
import ssl
from email.message import EmailMessage

from flask import current_app


def send_email(recipient: str, subject: str, body: str) -> bool:
    """Envia uma mensagem ou a captura no outbox de testes/desenvolvimento."""
    if current_app.config["MAIL_SUPPRESS_SEND"]:
        current_app.extensions.setdefault("mail_outbox", []).append(
            {"to": recipient, "subject": subject, "body": body}
        )
        return True

    host = current_app.config.get("SMTP_HOST")
    if not host:
        current_app.logger.error("SMTP_HOST não configurado; mensagem não enviada.")
        return False

    message = EmailMessage()
    message["From"] = current_app.config["MAIL_FROM"]
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content(body)

    port = current_app.config["SMTP_PORT"]
    timeout = current_app.config["SMTP_TIMEOUT"]
    context = ssl.create_default_context()
    try:
        if current_app.config["SMTP_USE_SSL"]:
            server = smtplib.SMTP_SSL(host, port, timeout=timeout, context=context)
        else:
            server = smtplib.SMTP(host, port, timeout=timeout)
        with server:
            if current_app.config["SMTP_USE_TLS"] and not current_app.config["SMTP_USE_SSL"]:
                server.starttls(context=context)
            username = current_app.config.get("SMTP_USERNAME")
            password = current_app.config.get("SMTP_PASSWORD")
            if username and password:
                server.login(username, password)
            server.send_message(message)
        return True
    except (OSError, smtplib.SMTPException):
        current_app.logger.exception("Falha ao enviar e-mail transacional.")
        return False
