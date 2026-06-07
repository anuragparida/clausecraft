"""SQLAlchemy 2.x async engine + session factory.

Phase 0 wires the engine up so healthchecks + future migrations work,
but no ORM models are defined yet (the audit-log table lands in
Phase 3). Importing this module does NOT trigger a connection — the
engine is created lazily on first use.
"""

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import settings


class Base(DeclarativeBase):
    """Single declarative base for all ORM models (added in later phases)."""


_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    """Return a process-wide async engine, building it on first call."""
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            settings.database_url,
            echo=False,
            pool_pre_ping=True,
        )
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return a process-wide session factory."""
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            bind=get_engine(),
            expire_on_commit=False,
            class_=AsyncSession,
        )
    return _session_factory


async def get_db_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency that yields an async session and closes it after.

    Usage::

        @app.get("/foo")
        async def foo(session: AsyncSession = Depends(get_db_session)):
            ...
    """
    factory = get_session_factory()
    async with factory() as session:
        yield session


async def db_ping() -> bool:
    """Cheap connectivity check used by ``/healthz``.

    Opens one short-lived connection and runs ``SELECT 1``. Returns
    True on success, False on any error. Never raises — the health
    endpoint needs to return a 503, not 500.
    """
    try:
        engine = get_engine()
        async with engine.connect() as conn:
            await conn.exec_driver_sql("SELECT 1")
        return True
    except Exception:  # noqa: BLE001 — healthcheck must be defensive
        return False
