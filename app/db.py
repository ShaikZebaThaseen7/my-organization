from __future__ import annotations

import os
from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker

from .models import Base


SessionLocal: scoped_session = None  # type: ignore[assignment]
engine = None  # type: ignore[assignment]


def init_engine(database_url: str, engine_options: dict | None = None) -> None:
    global SessionLocal, engine
    engine_options = engine_options or {}

    # Ensure parent directory exists for sqlite files
    if database_url.startswith("sqlite:///"):
        db_path = database_url.replace("sqlite:///", "", 1)
        os.makedirs(os.path.dirname(db_path), exist_ok=True)

    engine = create_engine(database_url, future=True, **engine_options)
    SessionLocal = scoped_session(sessionmaker(bind=engine, autoflush=False, autocommit=False))


def init_db(create_tables: bool = True) -> None:
    if engine is None:
        raise RuntimeError("Database engine is not initialized. Call init_engine() first.")
    if create_tables:
        Base.metadata.create_all(bind=engine)


def get_db():
    if SessionLocal is None:
        raise RuntimeError("Database session is not initialized. Call init_engine() first.")
    return SessionLocal

