"""
Feedback generation endpoints.

Four semantic endpoints, each supporting offline and live modes:
  POST /feedback/kc       — KC / task_type level
  POST /feedback/exercise — Exercise level
  POST /feedback/error    — Error level
  POST /feedback/image    — Image-annotated feedback (Gemini)

Auth: admin JWT (Bearer) OR platform API key (X-API-Key header).
  - JWT admin  → platform_id must be supplied as a query param
  - API key    → platform_id is resolved from the key; query param ignored
"""
import logging
import traceback
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response

logger = logging.getLogger(__name__)
from pydantic import BaseModel, ConfigDict, Field
from typing import Literal, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_caller, CallerContext, get_current_admin
from core.config import get_settings
from db.database import get_db
from db.algopython_db import get_algopython_db
from feedback.generator import generate_feedback
from feedback.characteristics import (
    IMAGE_CAPABLE,
    EXERCISE_REQUIRED,
    OfflineLevel,
    validate_for_level,
)
from platforms import manager as platform_manager

router = APIRouter(prefix="/feedback", tags=["feedback"])

_XML_RESPONSE = {200: {"content": {"application/xml": {}}, "description": "Feedback XML"}}


# ── Shared sub-models ──────────────────────────────────────────────────────────

class KnowledgeComponent(BaseModel):
    name: str = Field(..., description="KC identifier, e.g. 'FO.4.2.1'", examples=["FO.4.2.1"])
    description: Optional[str] = Field(
        None,
        description=(
            "Full KC description in French. "
            "If omitted, the description is auto-resolved from the knowledge_components table."
        ),
        examples=["Choisir l'argument avec lequel appeler la fonction déclarée"],
    )


class ExerciseContext(BaseModel):
    description: str = Field(..., description="Exercise description shown to the student")
    possible_solutions: list[str] = Field(
        default=[],
        description="List of accepted correct solution strings",
    )
    exercise_type: Optional[str] = Field(
        None,
        description="'robot', 'design', or 'console'. Required for image feedback to select the right pipeline.",
    )
    robot_map: Optional[dict] = Field(
        None,
        description=(
            "Robot grid definition. Required for robot image feedback. "
            "Format: {grid: [[row0...], [row1...], ...], rows: N, cols: M}. "
            "Cell values: O (free), X (obstacle), I (robot start), G (goal)."
        ),
    )


class ErrorContext(BaseModel):
    tag: str = Field(
        ...,
        description=(
            "Error-group tag or raw AST library tag. "
            "Exercise-116 groups: decomposition_error | function_body_error | "
            "function_declaration_error | declared_function_call_error | native_function_call_error. "
            "Raw AST tags also accepted, e.g. FUNCTION_DEFINITION_NAME_ERROR."
        ),
        examples=["function_declaration_error"],
    )
    description: str = Field(
        ...,
        description="Human-readable description of the specific error",
        examples=["Le nom de la fonction déclarée est incorrect (ex: vroum2 au lieu de vroum)"],
    )


class LiveContext(BaseModel):
    student_attempt: str = Field(..., description="Student's current code submission")
    interaction_data: dict = Field(
        default={},
        description="Interaction telemetry (time_on_task_s, attempts, hints_used, …)",
    )


# ── Helpers ────────────────────────────────────────────────────────────────────

def _resolve_platform(caller: CallerContext, query_platform_id: Optional[str]) -> str:
    """Resolve platform_id from API key (platform client) or query param (admin)."""
    if not caller.is_admin:
        return caller.platform_id  # always set for API key callers
    if not query_platform_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Admin callers must supply platform_id as a query parameter.",
        )
    return query_platform_id


async def _resolve_language(platform_id: str, requested: Optional[str], db: AsyncSession) -> str:
    if requested and requested in ("fr", "en"):
        return requested
    return await platform_manager.get_platform_language(db, platform_id)


async def _run_generation(
    platform_id: str,
    mode: str,
    language: str,
    characteristics: list[str],
    kc: KnowledgeComponent,
    db: AsyncSession,
    algopython_db=None,
    level: str = "task_type",
    exercise_id: Optional[str] = None,
    exercise: Optional[ExerciseContext] = None,
    error: Optional[ErrorContext] = None,
    live_context: Optional[LiveContext] = None,
    base_image: Optional[str] = None,
    decomposition_hint: Optional[str] = None,
) -> str:
    try:
        return await generate_feedback(
            platform_id=platform_id,
            mode=mode,
            language=language,
            characteristics=characteristics,
            kc_name=kc.name,
            kc_description=kc.description,
            level=level,
            exercise_id=exercise_id,
            exercise=exercise.model_dump() if exercise else None,
            error=error.model_dump() if error else None,
            live_context=live_context.model_dump() if live_context else None,
            base_image_b64=base_image,
            db=db,
            algopython_db=algopython_db,
            decomposition_hint=decomposition_hint,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except Exception as e:
        logger.error("Generation failed:\n%s", traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Generation failed: {str(e)}",
        )


# ══════════════════════════════════════════════════════════════════════════════
# 1.  KC / task_type level
# ══════════════════════════════════════════════════════════════════════════════

class KCFeedbackRequest(BaseModel):
    model_config = ConfigDict(json_schema_extra={
        "example": {
            "mode": "offline",
            "language": "fr",
            "knowledge_component": {
                "name": "FO.4.2.1",
                "description": "Choisir l'argument avec lequel appeler la fonction déclarée",
            },
            "characteristics": ["logos", "technical"],
        }
    })

    mode: Literal["offline", "live"] = Field(
        "offline",
        description=(
            "`offline` — no student data, generates reusable feedback for any learner. "
            "`live` — student interaction data is available; pass `live_context`."
        ),
    )
    language: Optional[str] = Field(None, description="'fr' or 'en'. Defaults to platform language.")
    knowledge_component: KnowledgeComponent
    characteristics: list[str] = Field(
        ...,
        min_length=1,
        description=(
            "Allowed: `logos` | `technical` | `with_example_unrelated_to_exercise`. "
            "`error_pointed` and `with_example_related_to_exercise` are not valid at this level."
        ),
    )
    live_context: Optional[LiveContext] = Field(
        None,
        description="Required when mode='live'. Contains student attempt and interaction telemetry.",
    )


@router.post(
    "/kc",
    summary="KC-level feedback (task_type)",
    description=(
        "Generate feedback at **task_type** level using only the knowledge component.\n\n"
        "**Modes:**\n"
        "- `offline` — reusable feedback, no student context\n"
        "- `live` — personalised, include `live_context` with student attempt\n\n"
        "**Auth:** admin JWT (`Authorization: Bearer …`) or platform API key (`X-API-Key`).\n\n"
        "Compatible characteristics: `logos`, `technical`, `with_example_unrelated_to_exercise`."
    ),
    response_class=Response,
    responses=_XML_RESPONSE,
)
async def feedback_kc(
    body: KCFeedbackRequest,
    platform_id: Optional[str] = Query(None, description="Platform ID (required for admin JWT callers)"),
    caller: CallerContext = Depends(get_caller),
    db: AsyncSession = Depends(get_db),
    algopython_db=Depends(get_algopython_db),
) -> Response:
    pid = _resolve_platform(caller, platform_id)
    validate_for_level(body.characteristics, OfflineLevel.TASK_TYPE)
    if body.mode == "live" and body.live_context is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="live_context is required when mode='live'.",
        )
    language = await _resolve_language(pid, body.language, db)
    xml = await _run_generation(
        platform_id=pid,
        mode=body.mode,
        language=language,
        characteristics=body.characteristics,
        kc=body.knowledge_component,
        level=OfflineLevel.TASK_TYPE,
        live_context=body.live_context,
        db=db,
        algopython_db=algopython_db,
    )
    return Response(content=xml, media_type="application/xml")


# ══════════════════════════════════════════════════════════════════════════════
# 2.  Exercise level
# ══════════════════════════════════════════════════════════════════════════════

class ExerciseFeedbackRequest(BaseModel):
    model_config = ConfigDict(json_schema_extra={
        "example": {
            "mode": "offline",
            "language": "fr",
            "knowledge_component": {
                "name": "FO.4.2.1",
                "description": "Choisir l'argument avec lequel appeler la fonction déclarée",
            },
            "exercise_id": "116",
            "characteristics": ["logos", "technical", "with_example_related_to_exercise"],
        }
    })

    mode: Literal["offline", "live"] = "offline"
    language: Optional[str] = Field(None, description="'fr' or 'en'. Defaults to platform language.")
    knowledge_component: KnowledgeComponent
    exercise_id: Optional[str] = Field(
        None,
        description=(
            "Platform exercise ID (e.g. '116'). "
            "Retrieves map, description, solutions, and error taxonomy from the RAG store. "
            "Provide at least one of exercise_id or exercise."
        ),
    )
    exercise: Optional[ExerciseContext] = Field(
        None,
        description="Explicit exercise context. Complements or replaces exercise_id.",
    )
    characteristics: list[str] = Field(
        ...,
        min_length=1,
        description=(
            "Allowed: `logos` | `technical` | `with_example_unrelated_to_exercise` | "
            "`with_example_related_to_exercise`. "
            "`error_pointed` is not valid at this level — use `/feedback/error`."
        ),
    )
    live_context: Optional[LiveContext] = Field(
        None,
        description="Required when mode='live'.",
    )


@router.post(
    "/exercise",
    summary="Exercise-level feedback",
    description=(
        "Generate feedback anchored in a specific exercise.\n\n"
        "**Modes:** `offline` (reusable) or `live` (student-personalised, add `live_context`).\n\n"
        "**Auth:** admin JWT or platform API key.\n\n"
        "Pass `exercise_id` to auto-retrieve exercise context from RAG. "
        "Compatible characteristics: `logos`, `technical`, "
        "`with_example_unrelated_to_exercise`, `with_example_related_to_exercise`."
    ),
    response_class=Response,
    responses=_XML_RESPONSE,
)
async def feedback_exercise(
    body: ExerciseFeedbackRequest,
    platform_id: Optional[str] = Query(None, description="Platform ID (required for admin JWT callers)"),
    caller: CallerContext = Depends(get_caller),
    db: AsyncSession = Depends(get_db),
    algopython_db=Depends(get_algopython_db),
) -> Response:
    pid = _resolve_platform(caller, platform_id)
    if not body.exercise_id and not body.exercise:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Provide at least one of: exercise_id (RAG lookup) or exercise (explicit context).",
        )
    validate_for_level(body.characteristics, OfflineLevel.EXERCISE)
    if body.mode == "live" and body.live_context is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="live_context is required when mode='live'.",
        )
    language = await _resolve_language(pid, body.language, db)
    xml = await _run_generation(
        platform_id=pid,
        mode=body.mode,
        language=language,
        characteristics=body.characteristics,
        kc=body.knowledge_component,
        level=OfflineLevel.EXERCISE,
        exercise_id=body.exercise_id,
        exercise=body.exercise,
        live_context=body.live_context,
        db=db,
        algopython_db=algopython_db,
    )
    return Response(content=xml, media_type="application/xml")


# ══════════════════════════════════════════════════════════════════════════════
# 3.  Error level
# ══════════════════════════════════════════════════════════════════════════════

class ErrorFeedbackRequest(BaseModel):
    model_config = ConfigDict(json_schema_extra={
        "example": {
            "mode": "offline",
            "language": "fr",
            "knowledge_component": {
                "name": "FO.2.1",
                "description": "Identifier le nom d'une fonction",
            },
            "exercise_id": "116",
            "error": {
                "tag": "function_declaration_error",
                "description": "Le nom de la fonction déclarée est incorrect (ex: vroum2 au lieu de vroum)",
            },
            "characteristics": ["error_pointed", "logos"],
        }
    })

    mode: Literal["offline", "live"] = "offline"
    language: Optional[str] = Field(None, description="'fr' or 'en'. Defaults to platform language.")
    knowledge_component: KnowledgeComponent
    error: ErrorContext
    exercise_id: Optional[str] = Field(
        None,
        description=(
            "If provided, level is automatically upgraded to `error_exercise` — "
            "feedback is anchored in both the error and the exercise context from RAG. "
            "Also unlocks `with_example_related_to_exercise`."
        ),
    )
    exercise: Optional[ExerciseContext] = Field(
        None,
        description="Explicit exercise context. Also upgrades level to error_exercise.",
    )
    characteristics: list[str] = Field(
        ...,
        min_length=1,
        description=(
            "Allowed at error level: `logos` | `technical` | `error_pointed` | "
            "`with_example_unrelated_to_exercise`. "
            "Add exercise_id to also enable `with_example_related_to_exercise` (→ error_exercise)."
        ),
    )
    live_context: Optional[LiveContext] = Field(
        None,
        description="Required when mode='live'. Contains student attempt and interaction telemetry.",
    )


@router.post(
    "/error",
    summary="Error-level feedback",
    description=(
        "Generate feedback targeting a **specific student error**.\n\n"
        "**Modes:** `offline` or `live` (add `live_context` with the student's code).\n\n"
        "**Auth:** admin JWT or platform API key.\n\n"
        "**Exercise 116 error groups:**\n"
        "| Group tag | KC |\n"
        "|---|---|\n"
        "| `decomposition_error` | AL.1.1.1.2.3 |\n"
        "| `function_body_error` | FO.2.3 |\n"
        "| `function_declaration_error` | FO.2.1, FO.2.2 |\n"
        "| `declared_function_call_error` | FO.4.2, FO.4.2.1 |\n"
        "| `native_function_call_error` | FO.4.1, FO.4.1.1 |\n\n"
        "Adding `exercise_id` upgrades level to `error_exercise` and unlocks "
        "`with_example_related_to_exercise`."
    ),
    response_class=Response,
    responses=_XML_RESPONSE,
)
async def feedback_error(
    body: ErrorFeedbackRequest,
    platform_id: Optional[str] = Query(None, description="Platform ID (required for admin JWT callers)"),
    caller: CallerContext = Depends(get_caller),
    db: AsyncSession = Depends(get_db),
    algopython_db=Depends(get_algopython_db),
) -> Response:
    pid = _resolve_platform(caller, platform_id)
    has_exercise = bool(body.exercise_id or body.exercise)
    level = OfflineLevel.ERROR_EXERCISE if has_exercise else OfflineLevel.ERROR
    if level == OfflineLevel.ERROR:
        validate_for_level(body.characteristics, OfflineLevel.ERROR)
    if body.mode == "live" and body.live_context is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="live_context is required when mode='live'.",
        )
    language = await _resolve_language(pid, body.language, db)
    xml = await _run_generation(
        platform_id=pid,
        mode=body.mode,
        language=language,
        characteristics=body.characteristics,
        kc=body.knowledge_component,
        level=level,
        exercise_id=body.exercise_id,
        exercise=body.exercise,
        error=body.error,
        live_context=body.live_context,
        db=db,
        algopython_db=algopython_db,
    )
    return Response(content=xml, media_type="application/xml")


# ══════════════════════════════════════════════════════════════════════════════
# 4.  Image-annotated feedback
# ══════════════════════════════════════════════════════════════════════════════

class ImageFeedbackRequest(BaseModel):
    model_config = ConfigDict(json_schema_extra={
        "example": {
            "mode": "offline",
            "language": "fr",
            "knowledge_component": {
                "name": "FO.4.2.1",
                "description": "Choisir l'argument avec lequel appeler la fonction déclarée",
            },
            "exercise_id": "116",
            "base_image": "<base64-encoded PNG>",
        }
    })

    mode: Literal["offline", "live"] = "offline"
    language: Optional[str] = Field(None, description="'fr' or 'en'. Defaults to platform language.")
    knowledge_component: KnowledgeComponent
    exercise_id: Optional[str] = Field(
        None,
        description="Exercise ID for RAG retrieval. Provide at least one of exercise_id or exercise.",
    )
    exercise: Optional[ExerciseContext] = Field(
        None,
        description="Explicit exercise context (alternative or complement to exercise_id).",
    )
    error: Optional[ErrorContext] = Field(
        None,
        description="If provided, level becomes error_exercise.",
    )
    base_image: str = Field(
        ...,
        description=(
            "Base64-encoded PNG screenshot (e.g. code editor or robot grid). "
            "The Gemini agent plans and applies annotations illustrating the KC in context."
        ),
    )
    decomposition_hint: Optional[str] = Field(
        None,
        description=(
            "Optional free-text hint describing how to decompose the exercise. "
            "Use this to guide the annotation style, e.g. 'highlight the loop that repeats 3 times' "
            "or 'show how the parameter changes the path length'."
        ),
    )
    live_context: Optional[LiveContext] = Field(
        None,
        description="Required when mode='live'.",
    )


@router.post(
    "/image",
    summary="Image-annotated feedback (Gemini)",
    description=(
        "Generate a **visually annotated image** feedback. "
        "Always uses `with_example_related_to_exercise`.\n\n"
        "**Modes:** `offline` or `live` (add `live_context`).\n\n"
        "**Auth:** admin JWT or platform API key.\n\n"
        "The `base_image` (base64 PNG) is sent to the Gemini agent which annotates it "
        "to illustrate the KC in the exercise context. "
        "Requires `exercise_id` or explicit `exercise`. "
        "If `error` is also provided, level becomes `error_exercise`."
    ),
    response_class=Response,
    responses=_XML_RESPONSE,
)
async def feedback_image(
    body: ImageFeedbackRequest,
    platform_id: Optional[str] = Query(None, description="Platform ID (required for admin JWT callers)"),
    caller: CallerContext = Depends(get_caller),
    db: AsyncSession = Depends(get_db),
    algopython_db=Depends(get_algopython_db),
) -> Response:
    pid = _resolve_platform(caller, platform_id)
    if not body.exercise_id and not body.exercise:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Image feedback requires exercise context. "
                "Provide exercise_id or an explicit exercise body."
            ),
        )
    if (
        body.exercise
        and (body.exercise.exercise_type or "").lower() == "robot"
        and not body.exercise.robot_map
    ):
        from db.algopython_crud import parse_robot_map_from_description
        parsed = parse_robot_map_from_description(body.exercise.description)
        if parsed:
            # Inject the parsed map so the rest of the pipeline sees it
            body.exercise.robot_map = parsed
        else:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "robot_map is required for Robot exercises and could not be parsed "
                    "from the exercise description. Expected a <map>[[...]]</map> block "
                    "in the description, or supply robot_map explicitly: "
                    "{\"grid\": [[\"I\",\"O\",...], ...], \"rows\": N, \"cols\": M}"
                ),
            )
    if body.mode == "live" and body.live_context is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="live_context is required when mode='live'.",
        )
    has_error = body.error is not None
    level = OfflineLevel.ERROR_EXERCISE if has_error else OfflineLevel.EXERCISE
    language = await _resolve_language(pid, body.language, db)
    xml = await _run_generation(
        platform_id=pid,
        mode=body.mode,
        language=language,
        characteristics=["with_example_related_to_exercise"],
        kc=body.knowledge_component,
        level=level,
        exercise_id=body.exercise_id,
        exercise=body.exercise,
        error=body.error,
        base_image=body.base_image,
        live_context=body.live_context,
        decomposition_hint=body.decomposition_hint,
        db=db,
        algopython_db=algopython_db,
    )
    return Response(content=xml, media_type="application/xml")


# ══════════════════════════════════════════════════════════════════════════════
# 5.  Generated image serving
# ══════════════════════════════════════════════════════════════════════════════

@router.get(
    "/images/{image_id}",
    summary="Serve a generated annotation image",
    description="Returns the PNG file produced by the Gemini annotation agent.",
    response_class=Response,
    responses={200: {"content": {"image/png": {}}}},
)
async def serve_generated_image(image_id: str) -> Response:
    settings = get_settings()
    # Sanitise: image_id must be a plain UUID (no path traversal)
    if "/" in image_id or "\\" in image_id or ".." in image_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid image ID.")
    image_path = Path(settings.generated_images_dir) / f"{image_id}.png"
    if not image_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image not found.")
    return Response(content=image_path.read_bytes(), media_type="image/png")
