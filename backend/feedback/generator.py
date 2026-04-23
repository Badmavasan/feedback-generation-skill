"""Main entry point for feedback generation — delegates to the orchestrator."""
import base64
import uuid

from agents.orchestrator import ClaudeOrchestrator
from feedback.characteristics import validate_characteristics
from db.trace import TraceCollector
from rag.retriever import format_db_exercise_context, retrieve_full_platform_context


async def generate_feedback(
    platform_id: str,
    mode: str,
    language: str,
    characteristics: list[str],
    kc_name: str,
    kc_description: str | None = None,
    level: str = "task_type",
    exercise: dict | None = None,
    error: dict | None = None,
    live_context: dict | None = None,
    base_image_b64: str | None = None,
    exercise_id: str | None = None,
    db=None,              # optional AsyncSession — local feedback DB (records + catalog)
    algopython_db=None,   # optional AsyncSession — AlgoPython source DB (read-only)
) -> str:
    """
    Orchestrate feedback generation and return XML string.
    If db is provided:
      - KC / exercise / error data is resolved from the DB when not explicitly given
      - a FeedbackRecord and AgentLogs are persisted in PostgreSQL
    """
    # ── 0. Resolve KC description from DB when not provided ───────────────────
    if (not kc_description or not kc_description.strip()) and db is not None:
        from db.crud import get_kc_by_name
        db_kc = await get_kc_by_name(db, platform_id, kc_name)
        if db_kc is not None:
            kc_description = db_kc.description

    # Fall back to empty string so downstream code never receives None
    kc_description = kc_description or ""

    # ── 1. Resolve exercise from AlgoPython source DB (primary) or local DB ───
    # Priority: explicit body > AlgoPython DB > local DB > RAG
    exercise_context_override: str | None = None

    if exercise is None and exercise_id is not None and algopython_db is not None:
        from db.algopython_crud import (
            get_algo_exercise_by_platform_id,
            get_exercise_task_types,
        )
        algo_ex = await get_algo_exercise_by_platform_id(algopython_db, exercise_id)
        if algo_ex is not None:
            from db.algopython_crud import parse_correct_codes
            task_types = await get_exercise_task_types(algopython_db, algo_ex.id)
            solutions = parse_correct_codes(algo_ex.correct_codes)
            exercise = {
                "description": algo_ex.description or "",
                "possible_solutions": solutions,
                "exercise_type": algo_ex.exercise_type or "",
                "task_types": [
                    {"task_code": tt.task_code, "task_name": tt.task_name}
                    for tt in task_types
                ],
            }
            exercise_context_override = format_db_exercise_context({
                "exercise_id": str(algo_ex.platform_exercise_id),
                "title": algo_ex.title,
                "exercise_type": algo_ex.exercise_type or "unknown",
                "description": algo_ex.description or "",
                "possible_solutions": solutions,
                "robot_map": None,
                "kc_names": [],
                "task_types": [
                    {"task_code": tt.task_code, "task_name": tt.task_name}
                    for tt in task_types
                ],
            })

    if exercise is None and exercise_id is not None and db is not None:
        from db.crud import get_exercise_by_exercise_id
        db_ex = await get_exercise_by_exercise_id(db, exercise_id)
        if db_ex is not None:
            exercise = {
                "description": db_ex.description,
                "possible_solutions": db_ex.possible_solutions or [],
                "robot_map": db_ex.robot_map,
                "exercise_type": db_ex.exercise_type,
                "kc_names": db_ex.kc_names or [],
                "task_types": [],
            }
            exercise_context_override = format_db_exercise_context({
                "exercise_id": db_ex.exercise_id,
                "title": db_ex.title,
                "exercise_type": db_ex.exercise_type,
                "description": db_ex.description,
                "possible_solutions": db_ex.possible_solutions or [],
                "robot_map": db_ex.robot_map,
                "kc_names": db_ex.kc_names or [],
            })

    # ── 2. Enrich error from AlgoPython source DB (primary) or local DB ───────
    if error is not None and error.get("tag"):
        tag = error["tag"]
        if algopython_db is not None and not (error.get("description") or "").strip():
            from db.algopython_crud import get_algo_error_by_tag
            algo_err = await get_algo_error_by_tag(algopython_db, tag)
            if algo_err is not None:
                error = {**error, "description": algo_err.description}

        if db is not None and not (error.get("description") or "").strip():
            from db.crud import get_error_by_tag
            db_err = await get_error_by_tag(db, platform_id, tag)
            if db_err is not None:
                overrides: dict = {}
                overrides["description"] = db_err.description
                if db_err.related_kc_names:
                    overrides["related_kc_names"] = db_err.related_kc_names
                error = {**error, **overrides}
        elif db is not None:
            from db.crud import get_error_by_tag
            db_err = await get_error_by_tag(db, platform_id, tag)
            if db_err is not None and db_err.related_kc_names:
                error = {**error, "related_kc_names": db_err.related_kc_names}

    # ── 2b. Fetch platform config + general config from DB ────────────────────
    platform_context_override: str | None = None
    general_feedback_instructions: str = ""

    platform_config: dict | None = None

    if db is not None:
        from db.crud import get_general_config, get_active_platform_config
        from platforms.manager import get_platform_context
        cfg = await get_general_config(db)
        general_feedback_instructions = cfg.general_feedback_instructions or ""

        # Load active platform configuration
        active_cfg = await get_active_platform_config(db, platform_id)
        if active_cfg:
            platform_config = {
                "name": active_cfg.name,
                "vocabulary_to_use": active_cfg.vocabulary_to_use,
                "vocabulary_to_avoid": active_cfg.vocabulary_to_avoid,
                "teacher_comments": active_cfg.teacher_comments,
            }

        # Build combined platform context: DB text + Chroma chunks
        db_platform_context = await get_platform_context(db, platform_id)
        rag_context = retrieve_full_platform_context(
            platform_id,
            {"kc_name": kc_name, "exercise_id": exercise_id},
            exercise_context_override=exercise_context_override,
        )
        parts = []
        if db_platform_context and db_platform_context.strip():
            parts.append(f"## Platform guidelines\n{db_platform_context.strip()}")
        if rag_context and rag_context.strip():
            parts.append(rag_context)
        if parts:
            platform_context_override = "\n\n".join(parts)

    # ── 3. Validate characteristics ────────────────────────────────────────────
    has_exercise = exercise is not None or exercise_id is not None
    has_error = error is not None

    characteristics = validate_characteristics(
        characteristics=characteristics,
        level=level,
        has_exercise=has_exercise,
        has_error=has_error,
    )

    # ── 4. Decode base image ───────────────────────────────────────────────────
    base_image: bytes | None = None
    if base_image_b64:
        base_image = base64.b64decode(base_image_b64)

    # ── 5. Create trace collector ──────────────────────────────────────────────
    trace = TraceCollector()

    # ── 6. Pre-create DB record ────────────────────────────────────────────────
    record_id: str | None = None
    if db is not None:
        from db.crud import create_feedback_record
        record_id = str(uuid.uuid4())
        await create_feedback_record(db, {
            "id": record_id,
            "platform_id": platform_id,
            "exercise_id": exercise_id,
            "kc_name": kc_name,
            "kc_description": kc_description,
            "mode": mode,
            "level": level,
            "language": language,
            "characteristics": characteristics,
            "request_payload": {
                "exercise": exercise,
                "error": error,
                "live_context": live_context,
            },
            "status": "pending",
        })

    # ── 7. Run generation ──────────────────────────────────────────────────────
    result_xml: str | None = None
    status = "completed"
    error_message: str | None = None

    try:
        orchestrator = ClaudeOrchestrator()
        result_xml = await orchestrator.run(
            platform_id=platform_id,
            mode=mode,
            level=level,
            language=language,
            characteristics=characteristics,
            kc_name=kc_name,
            kc_description=kc_description,
            exercise=exercise,
            error=error,
            live_context=live_context,
            base_image=base_image,
            exercise_id=exercise_id,
            exercise_context_override=exercise_context_override,
            platform_context_override=platform_context_override,
            general_feedback_instructions=general_feedback_instructions,
            platform_config=platform_config,
            run_id=record_id,
            trace=trace,
        )
    except Exception as exc:
        status = "failed"
        error_message = str(exc)
        raise
    finally:
        if db is not None and record_id is not None:
            from db.crud import save_feedback_result
            await save_feedback_result(
                db=db,
                record_id=record_id,
                result_xml=result_xml,
                status=status,
                error_message=error_message,
                trace=trace,
            )

    return result_xml
