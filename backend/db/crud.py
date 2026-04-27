"""CRUD helpers for all catalog and history tables."""
from __future__ import annotations

from typing import Any

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from db.models import AgentLog, ErrorEntry, Exercise, FeedbackRecord, GeneralConfig, KnowledgeComponent, PlatformConfig, PlatformRecord
from db.trace import TraceCollector


# ── Platforms ──────────────────────────────────────────────────────────────────

async def list_platforms_db(db: AsyncSession) -> list[PlatformRecord]:
    result = await db.execute(select(PlatformRecord).order_by(PlatformRecord.name))
    return list(result.scalars().all())


async def get_platform_db(db: AsyncSession, platform_id: str) -> PlatformRecord | None:
    result = await db.execute(select(PlatformRecord).where(PlatformRecord.id == platform_id))
    return result.scalar_one_or_none()


async def create_platform_db(db: AsyncSession, data: dict) -> PlatformRecord:
    p = PlatformRecord(**data)
    db.add(p)
    await db.flush()
    await db.refresh(p)
    return p


async def update_platform_db(db: AsyncSession, platform_id: str, data: dict) -> PlatformRecord | None:
    p = await get_platform_db(db, platform_id)
    if not p:
        return None
    for k, v in data.items():
        setattr(p, k, v)
    await db.flush()
    await db.refresh(p)
    return p


async def delete_platform_db(db: AsyncSession, platform_id: str) -> bool:
    result = await db.execute(delete(PlatformRecord).where(PlatformRecord.id == platform_id))
    return result.rowcount > 0


# ── General config (singleton row id=1) ──────────────────────────────────────

async def get_general_config(db: AsyncSession) -> GeneralConfig:
    result = await db.execute(select(GeneralConfig).where(GeneralConfig.id == 1))
    cfg = result.scalar_one_or_none()
    if cfg is None:
        cfg = GeneralConfig(id=1, general_feedback_instructions="")
        db.add(cfg)
        await db.flush()
        await db.refresh(cfg)
    return cfg


async def upsert_general_config(db: AsyncSession, instructions: str) -> GeneralConfig:
    cfg = await get_general_config(db)
    cfg.general_feedback_instructions = instructions
    await db.flush()
    await db.refresh(cfg)
    return cfg


# ── Platform configs ──────────────────────────────────────────────────────────

async def list_platform_configs(db: AsyncSession, platform_id: str) -> list[PlatformConfig]:
    result = await db.execute(
        select(PlatformConfig)
        .where(PlatformConfig.platform_id == platform_id)
        .order_by(PlatformConfig.created_at)
    )
    return list(result.scalars().all())


async def get_platform_config(db: AsyncSession, config_id: int) -> PlatformConfig | None:
    result = await db.execute(select(PlatformConfig).where(PlatformConfig.id == config_id))
    return result.scalar_one_or_none()


async def get_active_platform_config(db: AsyncSession, platform_id: str) -> PlatformConfig | None:
    result = await db.execute(
        select(PlatformConfig).where(
            PlatformConfig.platform_id == platform_id,
            PlatformConfig.is_active == True,  # noqa: E712
        )
    )
    return result.scalar_one_or_none()


async def create_platform_config(db: AsyncSession, data: dict) -> PlatformConfig:
    cfg = PlatformConfig(**data)
    db.add(cfg)
    await db.flush()
    await db.refresh(cfg)
    return cfg


async def update_platform_config(db: AsyncSession, config_id: int, data: dict) -> PlatformConfig | None:
    cfg = await get_platform_config(db, config_id)
    if not cfg:
        return None
    for k, v in data.items():
        setattr(cfg, k, v)
    await db.flush()
    await db.refresh(cfg)
    return cfg


async def activate_platform_config(db: AsyncSession, platform_id: str, config_id: int) -> PlatformConfig | None:
    from sqlalchemy import update as sql_update
    await db.execute(
        sql_update(PlatformConfig)
        .where(PlatformConfig.platform_id == platform_id)
        .values(is_active=False)
    )
    cfg = await get_platform_config(db, config_id)
    if not cfg or cfg.platform_id != platform_id:
        return None
    cfg.is_active = True
    await db.flush()
    await db.refresh(cfg)
    return cfg


async def delete_platform_config(db: AsyncSession, config_id: int) -> bool:
    result = await db.execute(delete(PlatformConfig).where(PlatformConfig.id == config_id))
    return result.rowcount > 0


# ── Exercises ──────────────────────────────────────────────────────────────────

async def list_exercises(db: AsyncSession, platform_id: str) -> list[Exercise]:
    result = await db.execute(
        select(Exercise).where(Exercise.platform_id == platform_id).order_by(Exercise.exercise_id)
    )
    return list(result.scalars().all())


async def get_exercise(db: AsyncSession, pk: int) -> Exercise | None:
    """Fetch by primary key (integer id)."""
    result = await db.execute(select(Exercise).where(Exercise.id == pk))
    return result.scalar_one_or_none()


async def get_exercise_by_exercise_id(db: AsyncSession, exercise_id: str) -> Exercise | None:
    """Fetch by the platform exercise_id string (e.g. '116')."""
    result = await db.execute(select(Exercise).where(Exercise.exercise_id == exercise_id))
    return result.scalar_one_or_none()


async def create_exercise(db: AsyncSession, data: dict) -> Exercise:
    ex = Exercise(**data)
    db.add(ex)
    await db.flush()
    await db.refresh(ex)
    return ex


async def update_exercise(db: AsyncSession, exercise_id: str, data: dict) -> Exercise | None:
    ex = await get_exercise_by_exercise_id(db, exercise_id)
    if not ex:
        return None
    for k, v in data.items():
        setattr(ex, k, v)
    await db.flush()
    await db.refresh(ex)
    return ex


async def delete_exercise(db: AsyncSession, exercise_id: str) -> bool:
    result = await db.execute(delete(Exercise).where(Exercise.exercise_id == exercise_id))
    return result.rowcount > 0


# ── KC lookups ─────────────────────────────────────────────────────────────────

async def get_kc_by_name(
    db: AsyncSession, platform_id: str, name: str
) -> KnowledgeComponent | None:
    result = await db.execute(
        select(KnowledgeComponent).where(
            KnowledgeComponent.platform_id == platform_id,
            KnowledgeComponent.name == name,
        )
    )
    return result.scalar_one_or_none()


# ── Error lookups ──────────────────────────────────────────────────────────────

async def get_error_by_tag(
    db: AsyncSession, platform_id: str, tag: str
) -> ErrorEntry | None:
    result = await db.execute(
        select(ErrorEntry).where(
            ErrorEntry.platform_id == platform_id,
            ErrorEntry.tag == tag,
        )
    )
    return result.scalar_one_or_none()


# ── Knowledge Components ───────────────────────────────────────────────────────

async def list_kcs(db: AsyncSession, platform_id: str) -> list[KnowledgeComponent]:
    result = await db.execute(
        select(KnowledgeComponent)
        .where(KnowledgeComponent.platform_id == platform_id)
        .order_by(KnowledgeComponent.name)
    )
    return list(result.scalars().all())


async def get_kc(db: AsyncSession, kc_id: int) -> KnowledgeComponent | None:
    result = await db.execute(select(KnowledgeComponent).where(KnowledgeComponent.id == kc_id))
    return result.scalar_one_or_none()


async def create_kc(db: AsyncSession, data: dict) -> KnowledgeComponent:
    kc = KnowledgeComponent(**data)
    db.add(kc)
    await db.flush()
    await db.refresh(kc)
    return kc


async def update_kc(db: AsyncSession, kc_id: int, data: dict) -> KnowledgeComponent | None:
    kc = await get_kc(db, kc_id)
    if not kc:
        return None
    for k, v in data.items():
        setattr(kc, k, v)
    await db.flush()
    await db.refresh(kc)
    return kc


async def delete_kc(db: AsyncSession, kc_id: int) -> bool:
    result = await db.execute(delete(KnowledgeComponent).where(KnowledgeComponent.id == kc_id))
    return result.rowcount > 0


# ── Error catalog ──────────────────────────────────────────────────────────────

async def list_errors(db: AsyncSession, platform_id: str) -> list[ErrorEntry]:
    result = await db.execute(
        select(ErrorEntry)
        .where(ErrorEntry.platform_id == platform_id)
        .order_by(ErrorEntry.tag)
    )
    return list(result.scalars().all())


async def get_error(db: AsyncSession, error_id: int) -> ErrorEntry | None:
    result = await db.execute(select(ErrorEntry).where(ErrorEntry.id == error_id))
    return result.scalar_one_or_none()


async def create_error(db: AsyncSession, data: dict) -> ErrorEntry:
    entry = ErrorEntry(**data)
    db.add(entry)
    await db.flush()
    await db.refresh(entry)
    return entry


async def update_error(db: AsyncSession, error_id: int, data: dict) -> ErrorEntry | None:
    entry = await get_error(db, error_id)
    if not entry:
        return None
    for k, v in data.items():
        setattr(entry, k, v)
    await db.flush()
    await db.refresh(entry)
    return entry


async def delete_error(db: AsyncSession, error_id: int) -> bool:
    result = await db.execute(delete(ErrorEntry).where(ErrorEntry.id == error_id))
    return result.rowcount > 0


# ── Feedback records ───────────────────────────────────────────────────────────

async def create_feedback_record(db: AsyncSession, data: dict) -> FeedbackRecord:
    record = FeedbackRecord(**data)
    db.add(record)
    await db.flush()
    await db.refresh(record)
    return record


async def save_feedback_result(
    db: AsyncSession,
    record_id: str,
    result_xml: str | None,
    status: str,
    error_message: str | None,
    trace: TraceCollector,
) -> None:
    result = await db.execute(
        select(FeedbackRecord).where(FeedbackRecord.id == record_id)
    )
    record = result.scalar_one_or_none()
    if not record:
        return

    record.result_xml = result_xml
    record.status = status
    record.error_message = error_message
    record.total_iterations = trace.total_iterations

    for event in trace.events:
        log = AgentLog(
            feedback_record_id=record_id,
            step_number=event.step_number,
            agent=event.agent,
            role=event.role,
            tool_name=event.tool_name,
            characteristic=event.characteristic,
            attempt=event.attempt,
            verdict=event.verdict,
            notes=event.notes,
            input_data=event.input_data,
            output_data=event.output_data,
            duration_ms=event.duration_ms,
        )
        db.add(log)

    await db.flush()


async def list_feedback_records(
    db: AsyncSession,
    platform_id: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[FeedbackRecord]:
    q = select(FeedbackRecord).order_by(FeedbackRecord.created_at.desc())
    if platform_id:
        q = q.where(FeedbackRecord.platform_id == platform_id)
    q = q.limit(limit).offset(offset)
    result = await db.execute(q)
    return list(result.scalars().all())


async def get_feedback_record(db: AsyncSession, record_id: str) -> FeedbackRecord | None:
    result = await db.execute(
        select(FeedbackRecord)
        .where(FeedbackRecord.id == record_id)
        .options(selectinload(FeedbackRecord.logs))
    )
    return result.scalar_one_or_none()


async def update_validation_status(
    db: AsyncSession, record_id: str, validation_status: str
) -> FeedbackRecord | None:
    record = await db.get(FeedbackRecord, record_id)
    if not record:
        return None
    record.validation_status = validation_status
    await db.flush()
    await db.refresh(record)
    return record


async def list_validated_records(
    db: AsyncSession, platform_id: str | None = None
) -> list[FeedbackRecord]:
    q = (
        select(FeedbackRecord)
        .where(FeedbackRecord.validation_status == "validé", FeedbackRecord.status == "completed")
        .order_by(FeedbackRecord.created_at.desc())
    )
    if platform_id:
        q = q.where(FeedbackRecord.platform_id == platform_id)
    result = await db.execute(q)
    return list(result.scalars().all())


async def delete_feedback_record(db: AsyncSession, record_id: str) -> bool:
    record = await db.get(FeedbackRecord, record_id)
    if record is None:
        return False
    await db.execute(delete(AgentLog).where(AgentLog.feedback_record_id == record_id))
    await db.delete(record)
    return True
