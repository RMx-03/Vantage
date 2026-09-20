import os
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.db.urls import normalize_database_url


def get_database_url() -> str:
    url = os.environ.get("DATABASE_URL") or settings.DATABASE_URL
    return normalize_database_url(url)


engine = create_engine(get_database_url(), pool_pre_ping=True)
SessionFactory = sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)


@contextmanager
def transaction() -> Iterator[Session]:
    with SessionFactory() as session:
        with session.begin():
            yield session
