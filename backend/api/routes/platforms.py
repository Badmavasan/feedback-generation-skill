from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_current_admin
from db.database import get_db
from db.crud import (
    get_general_config, upsert_general_config,
    list_platform_configs, get_platform_config, create_platform_config,
    update_platform_config, delete_platform_config, activate_platform_config,
)
from platforms.models import (
    PlatformCreate, PlatformContextUpload, PlatformOut, PlatformUpdate,
    GeneralConfigOut, GeneralConfigUpdate,
    PlatformConfigCreate, PlatformConfigUpdate, PlatformConfigOut,
)
from platforms import manager

router = APIRouter(prefix="/platforms", tags=["platforms"])


# ── General config (must be before /{platform_id} routes) ─────────────────────

@router.get("/config/general", response_model=GeneralConfigOut)
async def get_general_config_route(
    _admin=Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> GeneralConfigOut:
    cfg = await get_general_config(db)
    return GeneralConfigOut(
        general_feedback_instructions=cfg.general_feedback_instructions or "",
        updated_at=cfg.updated_at.isoformat() if cfg.updated_at else None,
    )


@router.patch("/config/general", response_model=GeneralConfigOut)
async def update_general_config_route(
    body: GeneralConfigUpdate,
    _admin=Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> GeneralConfigOut:
    cfg = await upsert_general_config(db, body.general_feedback_instructions)
    return GeneralConfigOut(
        general_feedback_instructions=cfg.general_feedback_instructions or "",
        updated_at=cfg.updated_at.isoformat() if cfg.updated_at else None,
    )


# ── Platform CRUD ──────────────────────────────────────────────────────────────

@router.get("", response_model=list[PlatformOut])
async def list_platforms(_admin=Depends(get_current_admin), db: AsyncSession = Depends(get_db)):
    return await manager.list_platforms(db)


@router.post("", response_model=PlatformOut, status_code=status.HTTP_201_CREATED)
async def create_platform(
    body: PlatformCreate,
    _admin=Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> PlatformOut:
    try:
        return await manager.create_platform(db, body)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@router.get("/{platform_id}", response_model=PlatformOut)
async def get_platform(
    platform_id: str,
    _admin=Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> PlatformOut:
    platform = await manager.get_platform(db, platform_id)
    if not platform:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Platform not found")
    return platform


@router.patch("/{platform_id}", response_model=PlatformOut)
async def update_platform(
    platform_id: str,
    body: PlatformUpdate,
    _admin=Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> PlatformOut:
    try:
        return await manager.update_platform(db, platform_id, body)
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Platform not found")


@router.delete("/{platform_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_platform(
    platform_id: str,
    _admin=Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> None:
    try:
        await manager.delete_platform(db, platform_id)
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Platform not found")


# ── Platform configurations ────────────────────────────────────────────────────

def _cfg_out(cfg) -> PlatformConfigOut:
    return PlatformConfigOut(
        id=cfg.id,
        platform_id=cfg.platform_id,
        name=cfg.name,
        is_active=cfg.is_active,
        vocabulary_to_use=cfg.vocabulary_to_use,
        vocabulary_to_avoid=cfg.vocabulary_to_avoid,
        teacher_comments=cfg.teacher_comments,
        created_at=cfg.created_at.isoformat() if cfg.created_at else "",
        updated_at=cfg.updated_at.isoformat() if cfg.updated_at else "",
    )


@router.get("/{platform_id}/configs", response_model=list[PlatformConfigOut])
async def list_configs(
    platform_id: str,
    _admin=Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    return [_cfg_out(c) for c in await list_platform_configs(db, platform_id)]


@router.post("/{platform_id}/configs", response_model=PlatformConfigOut, status_code=status.HTTP_201_CREATED)
async def create_config(
    platform_id: str,
    body: PlatformConfigCreate,
    _admin=Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    cfg = await create_platform_config(db, {
        "platform_id": platform_id,
        "name": body.name,
        "is_active": False,
        "vocabulary_to_use": body.vocabulary_to_use,
        "vocabulary_to_avoid": body.vocabulary_to_avoid,
        "teacher_comments": body.teacher_comments,
    })
    await db.commit()
    return _cfg_out(cfg)


@router.patch("/{platform_id}/configs/{config_id}", response_model=PlatformConfigOut)
async def update_config(
    platform_id: str,
    config_id: int,
    body: PlatformConfigUpdate,
    _admin=Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    data = {k: v for k, v in body.model_dump().items() if v is not None}
    cfg = await update_platform_config(db, config_id, data)
    if not cfg or cfg.platform_id != platform_id:
        raise HTTPException(status_code=404, detail="Config not found")
    await db.commit()
    return _cfg_out(cfg)


@router.delete("/{platform_id}/configs/{config_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_config(
    platform_id: str,
    config_id: int,
    _admin=Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    cfg = await get_platform_config(db, config_id)
    if not cfg or cfg.platform_id != platform_id:
        raise HTTPException(status_code=404, detail="Config not found")
    await delete_platform_config(db, config_id)
    await db.commit()


@router.post("/{platform_id}/configs/{config_id}/activate", response_model=PlatformConfigOut)
async def activate_config(
    platform_id: str,
    config_id: int,
    _admin=Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    cfg = await activate_platform_config(db, platform_id, config_id)
    if not cfg:
        raise HTTPException(status_code=404, detail="Config not found")
    await db.commit()
    return _cfg_out(cfg)


@router.get("/{platform_id}/context", status_code=status.HTTP_200_OK)
async def get_context_chunks(
    platform_id: str,
    _admin=Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Return all stored context chunks grouped by section."""
    p = await manager.get_platform(db, platform_id)
    if not p:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Platform not found")
    return {"platform_id": platform_id, "chunks": manager.list_context_chunks(platform_id)}


@router.post("/{platform_id}/context", status_code=status.HTTP_200_OK)
async def upsert_context(
    platform_id: str,
    body: PlatformContextUpload,
    _admin=Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Upload or replace context chunks for a platform (triggers re-embedding)."""
    p = await manager.get_platform(db, platform_id)
    if not p:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Platform not found")
    total = manager.upsert_context_chunks(platform_id, body)
    return {"platform_id": platform_id, "total_chunks": total}
