"""Async engine + session factory for the AlgoPython source database (read-only)."""
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from core.config import get_settings

_engine = None
_session_factory = None


def _is_configured() -> bool:
    url = get_settings().algopython_database_url
    return bool(url and url.strip())


def get_algopython_engine():
    global _engine
    if _engine is None:
        url = get_settings().algopython_database_url
        _engine = create_async_engine(
            url,
            echo=False,
            pool_size=5,
            max_overflow=10,
            pool_pre_ping=True,
        )
    return _engine


def get_algopython_session_factory():
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            get_algopython_engine(),
            expire_on_commit=False,
            class_=AsyncSession,
        )
    return _session_factory


class AlgoPythonBase(DeclarativeBase):
    pass


async def get_algopython_db():
    """FastAPI dependency — yields None when AlgoPython DB is not configured."""
    if not _is_configured():
        yield None
        return
    async with get_algopython_session_factory()() as session:
        try:
            yield session
        except Exception:
            raise
