import os
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.db.urls import normalize_database_url

# Essential-0 allows 20 connections. One web process with POOL_SIZE=5 plus
# MAX_OVERFLOW=2 uses at most 7 connections (1 process x 7 = 7). This leaves
# ample headroom under the 20-connection ceiling for the release-phase
# migration, a Heroku Scheduler one-off job, and an interactive `heroku pg:psql`.
POOL_SIZE = 5
MAX_OVERFLOW = 2
POOL_RECYCLE_SECONDS = 280  # Recycle below Heroku Postgres idle timeout (300s)


def get_database_url() -> str:
    url = os.environ.get("DATABASE_URL") or settings.DATABASE_URL
    return normalize_database_url(url)


engine = create_engine(
    get_database_url(),
    pool_pre_ping=True,
    pool_size=POOL_SIZE,
    max_overflow=MAX_OVERFLOW,
    pool_recycle=POOL_RECYCLE_SECONDS,
)
SessionFactory = sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)


@contextmanager
def transaction() -> Iterator[Session]:
    with SessionFactory() as session:
        with session.begin():
            yield session
