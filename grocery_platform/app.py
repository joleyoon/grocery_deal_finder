from __future__ import annotations

from pathlib import Path

import click
from flask import Flask, jsonify, send_from_directory

try:
    from flask_cors import CORS
except ImportError:  # pragma: no cover - dependency may not be installed yet
    CORS = None

from .api import api
from .config import Config
from .db import Base, get_engine, init_db, get_session_factory
from .services.demo import seed_demo_data


def create_app(config_overrides: dict | None = None) -> Flask:
    app = Flask(__name__)
    app.config.from_object(Config)
    if config_overrides:
        app.config.update(config_overrides)

    init_db(app)
    if CORS is not None:
        CORS(app, resources={r"/api/*": {"origins": "*"}})
    app.register_blueprint(api)
    register_commands(app)
    register_frontend_routes(app)

    @app.get("/")
    def root():
        frontend_dist = Path(app.config["FRONTEND_DIST"])
        if frontend_dist.exists():
            return send_from_directory(frontend_dist, "index.html")
        return jsonify(
            {
                "name": "Grocery Price Comparison Platform",
                "api": "/api",
                "frontend_built": False,
            }
        )

    return app


def register_commands(app: Flask) -> None:
    @app.cli.command("init-db")
    def init_db_command() -> None:
        Base.metadata.create_all(get_engine(app))
        click.echo("Initialized database.")

    @app.cli.command("seed-demo")
    def seed_demo_command() -> None:
        Base.metadata.create_all(get_engine(app))
        session = get_session_factory(app)()
        try:
            seed_demo_data(session)
            session.commit()
        finally:
            session.close()
        click.echo("Seeded demo data.")


def register_frontend_routes(app: Flask) -> None:
    frontend_dist = Path(app.config["FRONTEND_DIST"])
    if not frontend_dist.exists():
        return

    @app.get("/assets/<path:filename>")
    def frontend_assets(filename: str):
        return send_from_directory(frontend_dist / "assets", filename)

    @app.get("/<path:filename>")
    def frontend_fallback(filename: str):
        file_path = frontend_dist / filename
        if file_path.exists():
            return send_from_directory(frontend_dist, filename)
        return send_from_directory(frontend_dist, "index.html")
