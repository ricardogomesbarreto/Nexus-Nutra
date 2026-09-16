"""Ponto de entrada do Nexus Nutra."""

from nexus_nutra import create_app

app = create_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=app.config["DEBUG"])
