"""Query helpers for the AlgoPython source database (read-only, MySQL)."""
from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.algopython_models import (
    AlgoError,
    AlgoExercise,
    AlgoTaskType,
    AlgoTaskTypeExerciseAssociation,
)

_APPROVED = "approved"


# ── Exercises ──────────────────────────────────────────────────────────────────

async def list_algo_exercises(db: AsyncSession) -> list[AlgoExercise]:
    result = await db.execute(
        select(AlgoExercise)
        .where(
            AlgoExercise.status == _APPROVED,
            AlgoExercise.platform_exercise_id.isnot(None),
        )
        .order_by(AlgoExercise.platform_exercise_id)
    )
    return list(result.scalars().all())


async def get_algo_exercise_by_platform_id(
    db: AsyncSession, platform_exercise_id: str | int
) -> AlgoExercise | None:
    result = await db.execute(
        select(AlgoExercise).where(
            AlgoExercise.platform_exercise_id == int(platform_exercise_id),
            AlgoExercise.status == _APPROVED,
        )
    )
    return result.scalar_one_or_none()


def parse_correct_codes(raw: str | None) -> list[str]:
    """Decode the JSON array stored in correct_codes; return [] on failure."""
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return [str(s) for s in parsed if s]
    except (json.JSONDecodeError, TypeError):
        pass
    return []


# ── Errors ─────────────────────────────────────────────────────────────────────

async def list_algo_errors(db: AsyncSession) -> list[AlgoError]:
    result = await db.execute(
        select(AlgoError)
        .where(AlgoError.status == _APPROVED)
        .order_by(AlgoError.error_tag)
    )
    return list(result.scalars().all())


async def get_algo_error_by_tag(db: AsyncSession, tag: str) -> AlgoError | None:
    result = await db.execute(
        select(AlgoError).where(
            AlgoError.error_tag == tag,
            AlgoError.status == _APPROVED,
        )
    )
    return result.scalar_one_or_none()


# ── Task Types ─────────────────────────────────────────────────────────────────

async def list_algo_task_types(db: AsyncSession) -> list[AlgoTaskType]:
    result = await db.execute(
        select(AlgoTaskType)
        .where(AlgoTaskType.status == _APPROVED)
        .order_by(AlgoTaskType.task_code)
    )
    return list(result.scalars().all())


# ── Exercise ↔ TaskType relationship ──────────────────────────────────────────

async def get_exercise_task_types(
    db: AsyncSession, exercise_id: int
) -> list[AlgoTaskType]:
    """Return approved TaskTypes associated with an Exercise (by internal id)."""
    result = await db.execute(
        select(AlgoTaskType)
        .join(
            AlgoTaskTypeExerciseAssociation,
            AlgoTaskTypeExerciseAssociation.task_type_id == AlgoTaskType.id,
        )
        .where(
            AlgoTaskTypeExerciseAssociation.exercise_id == exercise_id,
            AlgoTaskType.status == _APPROVED,
        )
        .order_by(AlgoTaskType.task_code)
    )
    return list(result.scalars().all())


async def list_exercise_task_type_pairs(db: AsyncSession) -> list[dict]:
    """All approved (platform_exercise_id, task_code) pairs."""
    result = await db.execute(
        select(AlgoExercise.platform_exercise_id, AlgoTaskType.task_code)
        .join(
            AlgoTaskTypeExerciseAssociation,
            AlgoTaskTypeExerciseAssociation.exercise_id == AlgoExercise.id,
        )
        .join(
            AlgoTaskType,
            AlgoTaskTypeExerciseAssociation.task_type_id == AlgoTaskType.id,
        )
        .where(
            AlgoExercise.status == _APPROVED,
            AlgoTaskType.status == _APPROVED,
        )
        .order_by(AlgoExercise.platform_exercise_id, AlgoTaskType.task_code)
    )
    return [
        {"platform_exercise_id": str(row[0]), "task_code": row[1]}
        for row in result.all()
    ]
