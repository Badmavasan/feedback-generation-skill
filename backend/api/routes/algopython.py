"""Read-only endpoints serving data from the AlgoPython source database (MySQL)."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_current_admin
from db.algopython_db import get_algopython_db
from db import algopython_crud

router = APIRouter(prefix="/algopython", tags=["algopython"])


def _require_db(db: Optional[AsyncSession]) -> AsyncSession:
    if db is None:
        raise HTTPException(
            status_code=503,
            detail="AlgoPython source database is not configured (ALGOPYTHON_DATABASE_URL missing).",
        )
    return db


# ── Response models ────────────────────────────────────────────────────────────

class AlgoTaskTypeOut(BaseModel):
    id: int
    task_code: str
    task_name: str


class AlgoExerciseOut(BaseModel):
    id: int
    platform_exercise_id: str          # returned as string for the frontend
    title: str
    description: Optional[str]
    exercise_type: Optional[str]
    possible_solutions: list[str]
    task_types: list[AlgoTaskTypeOut]


class AlgoErrorOut(BaseModel):
    id: int
    tag: str                           # maps to error_tag column
    description: str


class ExerciseTaskTypePair(BaseModel):
    platform_exercise_id: str
    task_code: str


# ── Helpers ────────────────────────────────────────────────────────────────────

def _exercise_out(ex, task_types) -> AlgoExerciseOut:
    return AlgoExerciseOut(
        id=ex.id,
        platform_exercise_id=str(ex.platform_exercise_id),
        title=ex.title,
        description=ex.description,
        exercise_type=ex.exercise_type,
        possible_solutions=algopython_crud.parse_correct_codes(ex.correct_codes),
        task_types=[
            AlgoTaskTypeOut(id=tt.id, task_code=tt.task_code, task_name=tt.task_name)
            for tt in task_types
        ],
    )


# ── Exercises ──────────────────────────────────────────────────────────────────

@router.get("/exercises", response_model=list[AlgoExerciseOut])
async def list_exercises(
    db: Optional[AsyncSession] = Depends(get_algopython_db),
    _admin=Depends(get_current_admin),
):
    """List all approved exercises with their task types."""
    session = _require_db(db)
    exercises = await algopython_crud.list_algo_exercises(session)
    result = []
    for ex in exercises:
        task_types = await algopython_crud.get_exercise_task_types(session, ex.id)
        result.append(_exercise_out(ex, task_types))
    return result


@router.get("/exercises/{platform_exercise_id}", response_model=AlgoExerciseOut)
async def get_exercise(
    platform_exercise_id: str,
    db: Optional[AsyncSession] = Depends(get_algopython_db),
    _admin=Depends(get_current_admin),
):
    """Fetch one exercise (with task types) by platform_exercise_id."""
    session = _require_db(db)
    ex = await algopython_crud.get_algo_exercise_by_platform_id(session, platform_exercise_id)
    if not ex:
        raise HTTPException(status_code=404, detail="Exercise not found")
    task_types = await algopython_crud.get_exercise_task_types(session, ex.id)
    return _exercise_out(ex, task_types)


# ── Errors ─────────────────────────────────────────────────────────────────────

@router.get("/errors", response_model=list[AlgoErrorOut])
async def list_errors(
    db: Optional[AsyncSession] = Depends(get_algopython_db),
    _admin=Depends(get_current_admin),
):
    """List all approved errors."""
    session = _require_db(db)
    errors = await algopython_crud.list_algo_errors(session)
    return [AlgoErrorOut(id=e.id, tag=e.error_tag, description=e.description) for e in errors]


# ── Task Types ─────────────────────────────────────────────────────────────────

@router.get("/task-types", response_model=list[AlgoTaskTypeOut])
async def list_task_types(
    db: Optional[AsyncSession] = Depends(get_algopython_db),
    _admin=Depends(get_current_admin),
):
    """List all approved task types."""
    session = _require_db(db)
    task_types = await algopython_crud.list_algo_task_types(session)
    return [
        AlgoTaskTypeOut(id=tt.id, task_code=tt.task_code, task_name=tt.task_name)
        for tt in task_types
    ]


# ── Exercise ↔ TaskType pairs ──────────────────────────────────────────────────

@router.get("/exercise-task-types", response_model=list[ExerciseTaskTypePair])
async def list_exercise_task_type_pairs(
    db: Optional[AsyncSession] = Depends(get_algopython_db),
    _admin=Depends(get_current_admin),
):
    """All approved (platform_exercise_id, task_code) pairs."""
    session = _require_db(db)
    return await algopython_crud.list_exercise_task_type_pairs(session)
