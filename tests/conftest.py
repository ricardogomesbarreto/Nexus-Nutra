from __future__ import annotations

import pytest

from nexus_nutra import create_app


@pytest.fixture()
def app(tmp_path):
    application = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "test-secret",
            "DATABASE": str(tmp_path / "test.db"),
            "MAIL_SUPPRESS_SEND": True,
            "PUBLIC_BASE_URL": "https://nutra.test",
            "REQUIRE_EMAIL_VERIFICATION": False,
        }
    )
    yield application


@pytest.fixture()
def client(app):
    return app.test_client()


def csrf(client):
    with client.session_transaction() as session:
        return session["csrf_token"]


@pytest.fixture()
def token(client):
    client.get("/cadastro")
    return csrf(client)
