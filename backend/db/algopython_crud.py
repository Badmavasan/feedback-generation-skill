"""Query helpers for the AlgoPython source database (read-only, MySQL)."""
from __future__ import annotations

import json
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

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


_VALID_CELLS = frozenset("OXIG")


def _rows_from_cell_lines(text: str) -> list[list[str]] | None:
    """Extract grid rows from any text containing bracket-enclosed cell sequences.

    Accepts formats:
      [[O,X,G],[I,O,O]]       compact single-line (unquoted)
      [O, X, G]  per line     one row per line, optional trailing comma
      O X I G    per line     space-separated, no brackets
      ["O","X","G"] per line  quoted variants
    Returns None when no valid grid rows are found.
    """
    import re

    rows: list[list[str]] = []

    # Strategy A: find every [...] group whose first token is a valid cell character.
    # This handles compact single-line [[O,X,G],[I,O,O]] as well as per-line rows.
    for m in re.finditer(r'\[([^\[\]]+)\]', text):
        inner = m.group(1)
        cells = [c.strip().strip('"\'') for c in re.split(r'[,\s]+', inner) if c.strip()]
        cells = [c for c in cells if c and c[0] in _VALID_CELLS]
        if len(cells) >= 1:
            rows.append(cells)

    if rows:
        return rows

    # Strategy B: space/comma-separated rows without any brackets
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        cells = [c.strip().strip('"\'') for c in re.split(r'[,\s]+', line) if c.strip()]
        cells = [c for c in cells if c and c[0] in _VALID_CELLS]
        if len(cells) >= 2 and all(c[0] in _VALID_CELLS for c in cells):
            rows.append(cells)

    return rows if rows else None


def parse_robot_map_from_description(description: str | None) -> dict | None:
    """Extract robot_map from an exercise description.

    Tries, in order:
      1. Content inside <map>…</map> tags (any case).
      2. Content inside <grid>…</grid> tags.
      3. The entire description (for exercises where the map IS the description).

    Within the extracted block, tries:
      a. Standard JSON parse ([[…],[…]]).
      b. Python-style unquoted grid (O/X/I/G tokens inside brackets).
      c. Bare rows of O/X/I/G separated by commas or whitespace.

    Returns {"grid": [[...], ...], "rows": N, "cols": M}
    or None if no parseable grid is found.
    Logs a detailed error with the raw description content when it fails.
    """
    import re

    if not description:
        logger.warning("[parse_robot_map] description is empty/None — no map to parse")
        return None

    # ── Locate the map block ──────────────────────────────────────────────────
    block: str | None = None
    for tag in ("map", "grid"):
        m = re.search(rf'<{tag}>(.*?)</{tag}>', description, re.DOTALL | re.IGNORECASE)
        if m:
            block = m.group(1).strip()
            logger.debug("[parse_robot_map] found <%s> block (%d chars)", tag, len(block))
            break

    if block is None:
        # No tag found — try the whole description as a last resort
        logger.warning(
            "[parse_robot_map] no <map>/<grid> tag found — scanning full description. "
            "First 400 chars: %r", description[:400]
        )
        block = description

    # ── Parse the block ───────────────────────────────────────────────────────
    def _build_result(rows: list[list[str]], strategy: str) -> dict:
        cols = max(len(r) for r in rows)
        logger.info(
            "[parse_robot_map] parsed via %s: %d×%d grid, "
            "I=%s G=%s",
            strategy, len(rows), cols,
            next(((r, c) for r, row in enumerate(rows) for c, cell in enumerate(row) if cell == "I"), "?"),
            next(((r, c) for r, row in enumerate(rows) for c, cell in enumerate(row) if cell == "G"), "?"),
        )
        return {"grid": rows, "rows": len(rows), "cols": cols}

    # Strategy 1: JSON parse (handles quoted or double-nested arrays)
    json_src = block if block.strip().startswith('[') else '[' + block + ']'
    try:
        parsed = json.loads(json_src)
        if isinstance(parsed, list) and parsed:
            if isinstance(parsed[0], list):
                rows = [[str(c).strip().strip('"\'') for c in row] for row in parsed]
                rows = [r for r in rows if r]
                if rows:
                    return _build_result(rows, "JSON")
            elif isinstance(parsed[0], str):
                # Single flat row
                rows = [[str(c).strip().strip('"\'') for c in parsed]]
                return _build_result(rows, "JSON-flat")
    except (json.JSONDecodeError, TypeError, ValueError):
        pass

    # Strategy 2 & 3: bracket or bare cell extraction
    rows = _rows_from_cell_lines(block)
    if rows:
        return _build_result(rows, "cell-scan")

    logger.error(
        "[parse_robot_map] FAILED — could not extract any grid rows.\n"
        "  description length: %d chars\n"
        "  first 600 chars: %r",
        len(description), description[:600],
    )
    return None


def parse_correct_codes(raw: str | None) -> list[str]:
    """Decode solution code(s) from the correct_codes field.

    Handles:
      • JSON array of strings:  ["def f(): ...", "droite(2)"]
      • JSON array with Python escaping
      • Python ast.literal_eval (single-quoted strings, etc.)
      • A plain string (treated as one solution)

    Returns [] only when raw is empty/None or genuinely undecodable.
    Raises ValueError with a clear message when raw is non-empty but cannot be decoded.
    """
    import ast as _ast

    if not raw or not raw.strip():
        return []

    # Strategy 1: standard JSON
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            solutions = [str(s) for s in parsed if s]
            if solutions:
                logger.info("[parse_correct_codes] decoded %d solution(s) via JSON", len(solutions))
                return solutions
        elif isinstance(parsed, str) and parsed.strip():
            logger.info("[parse_correct_codes] decoded 1 solution via JSON string")
            return [parsed]
    except (json.JSONDecodeError, TypeError):
        pass

    # Strategy 2: Python literal (handles single-quoted JSON-like arrays)
    try:
        parsed = _ast.literal_eval(raw.strip())
        if isinstance(parsed, (list, tuple)):
            solutions = [str(s) for s in parsed if s]
            if solutions:
                logger.info("[parse_correct_codes] decoded %d solution(s) via ast.literal_eval", len(solutions))
                return solutions
        elif isinstance(parsed, str) and parsed.strip():
            return [parsed]
    except (ValueError, SyntaxError):
        pass

    # Strategy 3: treat the whole field as a single solution (plain code string)
    stripped = raw.strip()
    if stripped:
        logger.warning(
            "[parse_correct_codes] could not JSON/AST decode correct_codes — "
            "treating entire field as one solution (%d chars)", len(stripped),
        )
        return [stripped]

    logger.error(
        "[parse_correct_codes] correct_codes field is non-empty but undecodable: %r",
        raw[:200],
    )
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
