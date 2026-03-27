from __future__ import annotations

from typing import Any

from flask import Flask, g
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, scoped_session, sessionmaker


class Base(DeclarativeBase):
    pass


def _connect_args(database_url: str) -> dict[str, Any]:
    if database_url.startswith("sqlite"):
        return {"check_same_thread": False}
    return {}


def init_db(app: Flask) -> None:
    database_url = app.config["DATABASE_URL"]
    engine = create_engine(
        database_url,
        future=True,
        pool_pre_ping=True,
        connect_args=_connect_args(database_url),
    )
    session_factory = scoped_session(
        sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    )

    app.extensions["db_engine"] = engine
    app.extensions["db_session_factory"] = session_factory

    @app.before_request
    def open_session() -> None:
        g.db_session = session_factory()

    @app.teardown_request
    def close_session(exception: BaseException | None) -> None:
        session = g.pop("db_session", None)
        if session is None:
            return
        if exception is not None:
            session.rollback()
        session.close()


def get_engine(app: Flask):
    return app.extensions["db_engine"]


def get_session_factory(app: Flask):
    return app.extensions["db_session_factory"]


def get_session():
    return g.db_session
