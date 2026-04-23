"""Knowledge component catalog CRUD."""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_current_admin
from db.database import get_db
from db import crud

router = APIRouter(prefix="/kcs", tags=["kcs"])


class KCIn(BaseModel):
    platform_id: str = "algopython"
    name: str
    description: str
    series: Optional[str] = None


class KCOut(BaseModel):
    id: int
    platform_id: str
    name: str
    description: str
    series: Optional[str]
    created_at: str

    class Config:
        from_attributes = True


@router.get("", response_model=list[KCOut])
async def list_kcs(
    platform_id: str = Query("algopython"),
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    rows = await crud.list_kcs(db, platform_id)
    return [_to_out(r) for r in rows]


@router.get("/{kc_id}", response_model=KCOut)
async def get_kc(
    kc_id: int,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    row = await crud.get_kc(db, kc_id)
    if not row:
        raise HTTPException(status_code=404, detail="KC not found")
    return _to_out(row)


@router.post("", response_model=KCOut, status_code=status.HTTP_201_CREATED)
async def create_kc(
    body: KCIn,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    row = await crud.create_kc(db, body.model_dump())
    return _to_out(row)


@router.patch("/{kc_id}", response_model=KCOut)
async def update_kc(
    kc_id: int,
    body: KCIn,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    data = {k: v for k, v in body.model_dump().items() if v is not None}
    row = await crud.update_kc(db, kc_id, data)
    if not row:
        raise HTTPException(status_code=404, detail="KC not found")
    return _to_out(row)


@router.delete("/{kc_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_kc(
    kc_id: int,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    deleted = await crud.delete_kc(db, kc_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="KC not found")


def _to_out(row) -> dict:
    return {
        "id": row.id,
        "platform_id": row.platform_id,
        "name": row.name,
        "description": row.description,
        "series": row.series,
        "created_at": row.created_at.isoformat() if row.created_at else "",
    }
