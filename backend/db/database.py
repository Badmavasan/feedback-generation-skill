"""SQLAlchemy async engine + session factory (PostgreSQL via asyncpg)."""
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from core.config import get_settings


def _make_url() -> str:
    settings = get_settings()
    return settings.database_url


engine = create_async_engine(
    _make_url(),
    echo=False,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
)

AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


class Base(DeclarativeBase):
    pass


async def init_db() -> None:
    """Create all tables on startup (idempotent)."""
    from db import models  # noqa: F401 — ensure models are registered before create_all
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(
            __import__("sqlalchemy").text(
                "ALTER TABLE feedback_records "
                "ADD COLUMN IF NOT EXISTS validation_status VARCHAR NOT NULL DEFAULT 'generated'"
            )
        )


async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
