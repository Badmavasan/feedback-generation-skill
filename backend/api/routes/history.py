"""Feedback generation history + full agent trace."""
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_current_admin
from db.database import get_db
from db import crud

router = APIRouter(prefix="/history", tags=["history"])


@router.get("")
async def list_history(
    platform_id: str = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    records = await crud.list_feedback_records(db, platform_id=platform_id, limit=limit, offset=offset)
    return [_record_summary(r) for r in records]


@router.get("/export")
async def export_validated(
    platform_id: str = Query(None),
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    records = await crud.list_validated_records(db, platform_id=platform_id)
    if not records:
        raise HTTPException(status_code=404, detail="Aucun feedback validé à exporter")
    combined = "\n".join(r.result_xml for r in records if r.result_xml)
    return Response(
        content=combined,
        media_type="application/xml",
        headers={"Content-Disposition": 'attachment; filename="feedbacks_valides.xml"'},
    )


@router.patch("/{record_id}/validate")
async def validate_record(
    record_id: str,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    record = await crud.update_validation_status(db, record_id, "validé")
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")
    await db.commit()
    return _record_summary(record)


@router.patch("/{record_id}/unvalidate")
async def unvalidate_record(
    record_id: str,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    record = await crud.update_validation_status(db, record_id, "generated")
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")
    await db.commit()
    return _record_summary(record)


@router.delete("/{record_id}", status_code=204)
async def delete_record(
    record_id: str,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    deleted = await crud.delete_feedback_record(db, record_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Record not found")
    await db.commit()


@router.get("/{record_id}")
async def get_record(
    record_id: str,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    record = await crud.get_feedback_record(db, record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")
    return {
        **_record_summary(record),
        "result_xml": record.result_xml,
        "request_payload": record.request_payload,
        "logs": [_log_out(log) for log in record.logs],
    }


def _record_summary(r) -> dict:
    return {
        "id": r.id,
        "platform_id": r.platform_id,
        "exercise_id": r.exercise_id,
        "kc_name": r.kc_name,
        "kc_description": r.kc_description,
        "mode": r.mode,
        "level": r.level,
        "language": r.language,
        "characteristics": r.characteristics,
        "status": r.status,
        "validation_status": r.validation_status,
        "error_message": r.error_message,
        "total_iterations": r.total_iterations,
        "created_at": r.created_at.isoformat() if r.created_at else "",
    }


def _log_out(log) -> dict:
    return {
        "id": log.id,
        "step_number": log.step_number,
        "agent": log.agent,
        "role": log.role,
        "tool_name": log.tool_name,
        "characteristic": log.characteristic,
        "attempt": log.attempt,
        "verdict": log.verdict,
        "notes": log.notes,
        "input_data": log.input_data,
        "output_data": log.output_data,
        "duration_ms": log.duration_ms,
        "created_at": log.created_at.isoformat() if log.created_at else "",
    }
