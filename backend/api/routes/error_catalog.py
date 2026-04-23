"""Error catalog CRUD."""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_current_admin
from db.database import get_db
from db import crud

router = APIRouter(prefix="/error-catalog", tags=["error-catalog"])


class ErrorIn(BaseModel):
    platform_id: str = "algopython"
    tag: str
    description: str
    related_kc_names: list[str] = []


class ErrorOut(BaseModel):
    id: int
    platform_id: str
    tag: str
    description: str
    related_kc_names: list[str]
    created_at: str

    class Config:
        from_attributes = True


@router.get("", response_model=list[ErrorOut])
async def list_errors(
    platform_id: str = Query("algopython"),
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    rows = await crud.list_errors(db, platform_id)
    return [_to_out(r) for r in rows]


@router.get("/{error_id}", response_model=ErrorOut)
async def get_error(
    error_id: int,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    row = await crud.get_error(db, error_id)
    if not row:
        raise HTTPException(status_code=404, detail="Error not found")
    return _to_out(row)


@router.post("", response_model=ErrorOut, status_code=status.HTTP_201_CREATED)
async def create_error(
    body: ErrorIn,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    row = await crud.create_error(db, body.model_dump())
    return _to_out(row)


@router.patch("/{error_id}", response_model=ErrorOut)
async def update_error(
    error_id: int,
    body: ErrorIn,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    data = {k: v for k, v in body.model_dump().items() if v is not None}
    row = await crud.update_error(db, error_id, data)
    if not row:
        raise HTTPException(status_code=404, detail="Error not found")
    return _to_out(row)


@router.delete("/{error_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_error(
    error_id: int,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    deleted = await crud.delete_error(db, error_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Error not found")


def _to_out(row) -> dict:
    return {
        "id": row.id,
        "platform_id": row.platform_id,
        "tag": row.tag,
        "description": row.description,
        "related_kc_names": row.related_kc_names or [],
        "created_at": row.created_at.isoformat() if row.created_at else "",
    }
