"""Platform management — DB-backed (PostgreSQL)."""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from db.crud import (
    list_platforms_db,
    get_platform_db,
    create_platform_db,
    update_platform_db,
    delete_platform_db,
    get_general_config,
)
from db.models import PlatformRecord
from platforms.models import PlatformCreate, PlatformContextUpload, PlatformOut, PlatformUpdate
from rag.store import get_vector_store


def _to_out(p: PlatformRecord, chunk_count: int = 0) -> PlatformOut:
    return PlatformOut(
        id=p.id,
        name=p.name,
        language=p.language,
        description=p.description or "",
        feedback_mode=p.feedback_mode or "offline",
        platform_context=p.platform_context,
        live_student_prompt=p.live_student_prompt,
        created_at=p.created_at.isoformat() if p.created_at else "",
        context_chunk_count=chunk_count,
    )


async def list_platforms(db: AsyncSession) -> list[PlatformOut]:
    records = await list_platforms_db(db)
    store = get_vector_store()
    return [_to_out(p, store.count_chunks(p.id)) for p in records]


async def get_platform(db: AsyncSession, platform_id: str) -> PlatformOut | None:
    p = await get_platform_db(db, platform_id)
    if not p:
        return None
    store = get_vector_store()
    return _to_out(p, store.count_chunks(platform_id))


async def create_platform(db: AsyncSession, payload: PlatformCreate) -> PlatformOut:
    existing = await get_platform_db(db, payload.id)
    if existing:
        raise ValueError(f"Platform '{payload.id}' already exists")
    from datetime import datetime
    data = {
        "id": payload.id,
        "name": payload.name,
        "language": payload.language,
        "description": payload.description,
        "feedback_mode": payload.feedback_mode,
        "platform_context": payload.platform_context,
        "live_student_prompt": payload.live_student_prompt,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }
    p = await create_platform_db(db, data)
    return _to_out(p, 0)


async def update_platform(db: AsyncSession, platform_id: str, payload: PlatformUpdate) -> PlatformOut:
    updates: dict = {}
    if payload.name is not None:
        updates["name"] = payload.name
    if payload.language is not None:
        updates["language"] = payload.language
    if payload.description is not None:
        updates["description"] = payload.description
    if payload.feedback_mode is not None:
        updates["feedback_mode"] = payload.feedback_mode
    if payload.platform_context is not None:
        updates["platform_context"] = payload.platform_context
    if payload.live_student_prompt is not None:
        updates["live_student_prompt"] = payload.live_student_prompt

    p = await update_platform_db(db, platform_id, updates)
    if not p:
        raise KeyError(platform_id)
    store = get_vector_store()
    return _to_out(p, store.count_chunks(platform_id))


async def delete_platform(db: AsyncSession, platform_id: str) -> None:
    deleted = await delete_platform_db(db, platform_id)
    if not deleted:
        raise KeyError(platform_id)
    store = get_vector_store()
    store.delete_platform(platform_id)


async def get_platform_language(db: AsyncSession, platform_id: str) -> str:
    p = await get_platform_db(db, platform_id)
    return p.language if p else "fr"


async def get_platform_context(db: AsyncSession, platform_id: str) -> str | None:
    """Return the platform_context text from DB, or None."""
    p = await get_platform_db(db, platform_id)
    return p.platform_context if p else None


async def get_platform_mode(db: AsyncSession, platform_id: str) -> str:
    p = await get_platform_db(db, platform_id)
    return p.feedback_mode if p else "offline"


def list_context_chunks(platform_id: str) -> dict[str, list[str]]:
    """Return all stored context chunks grouped by section."""
    store = get_vector_store()
    return store.get_chunks_by_section(platform_id)


def upsert_context_chunks(platform_id: str, payload: PlatformContextUpload) -> int:
    """Embed and store context chunks in vector store. Returns total chunk count."""
    store = get_vector_store()
    if payload.replace_section:
        store.delete_section(platform_id, payload.replace_section)
    store.add_chunks(platform_id, payload.chunks)
    return store.count_chunks(platform_id)
