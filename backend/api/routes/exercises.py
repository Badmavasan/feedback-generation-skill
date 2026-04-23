"""Exercise catalog CRUD — AlgoPython admin."""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_current_admin
from db.database import get_db
from db import crud

router = APIRouter(prefix="/exercises", tags=["exercises"])


class RobotMap(BaseModel):
    rows: int
    cols: int
    grid: list[list[str]]  # O=open, X=wall, I=start, G=goal


class ExerciseIn(BaseModel):
    platform_id: str = "algopython"
    exercise_id: str
    title: str
    description: str = ""
    exercise_type: str          # console | design | robot
    robot_map: Optional[RobotMap] = None
    possible_solutions: list[str] = []
    kc_names: list[str] = []


class ExerciseOut(BaseModel):
    id: int
    platform_id: str
    exercise_id: str
    title: str
    description: str
    exercise_type: str
    robot_map: Optional[dict]
    possible_solutions: list[str]
    kc_names: list[str]
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True


@router.get("", response_model=list[ExerciseOut])
async def list_exercises(
    platform_id: str = Query("algopython"),
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    rows = await crud.list_exercises(db, platform_id)
    return [_to_out(r) for r in rows]


@router.get("/{exercise_id}", response_model=ExerciseOut)
async def get_exercise(
    exercise_id: str,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    row = await crud.get_exercise_by_exercise_id(db, exercise_id)
    if not row:
        raise HTTPException(status_code=404, detail="Exercise not found")
    return _to_out(row)


@router.post("", response_model=ExerciseOut, status_code=status.HTTP_201_CREATED)
async def create_exercise(
    body: ExerciseIn,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    existing = await crud.get_exercise_by_exercise_id(db, body.exercise_id)
    if existing:
        raise HTTPException(status_code=409, detail="exercise_id already exists")
    data = body.model_dump()
    if data.get("robot_map"):
        data["robot_map"] = data["robot_map"]  # already a dict via pydantic
    row = await crud.create_exercise(db, data)
    return _to_out(row)


@router.patch("/{exercise_id}", response_model=ExerciseOut)
async def update_exercise(
    exercise_id: str,
    body: ExerciseIn,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    data = {k: v for k, v in body.model_dump().items() if v is not None}
    row = await crud.update_exercise(db, exercise_id, data)
    if not row:
        raise HTTPException(status_code=404, detail="Exercise not found")
    return _to_out(row)


@router.delete("/{exercise_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_exercise(
    exercise_id: str,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    deleted = await crud.delete_exercise(db, exercise_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Exercise not found")


def _to_out(row) -> dict:
    return {
        "id": row.id,
        "platform_id": row.platform_id,
        "exercise_id": row.exercise_id,
        "title": row.title,
        "description": row.description or "",
        "exercise_type": row.exercise_type,
        "robot_map": row.robot_map,
        "possible_solutions": row.possible_solutions or [],
        "kc_names": row.kc_names or [],
        "created_at": row.created_at.isoformat() if row.created_at else "",
        "updated_at": row.updated_at.isoformat() if row.updated_at else "",
    }
