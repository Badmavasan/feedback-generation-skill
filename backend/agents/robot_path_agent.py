"""Standalone agent for finding and validating the complete robot path.

Strategy
--------
1. Try every solution string in *all* possible_solutions (not just the first one).
   Pick the first that passes goal_reached().
2. If no stored solution reaches the goal — or the solution list is empty — fall back
   to Claude with extended thinking to reconstruct the path from the grid description
   and a partial trace.

The agent is intentionally decoupled from the orchestrator so it has its own model
call budget and can reason independently without polluting the orchestrator context.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

import anthropic

from core.config import get_settings
from robot.path_computer import (
    _DIRECT_PRIMITIVES,
    compute_drawings,
    goal_reached,
    steps_to_drawings,
    trace_path,
)

logger = logging.getLogger(__name__)

# Extended thinking budget — more than enough for a full grid traversal plan.
# max_tokens must exceed budget_tokens; we allow 4 k for the JSON output itself.
_THINKING_BUDGET = 10_000
_MAX_TOKENS      = _THINKING_BUDGET + 4_000

_CLAUDE_SYSTEM = """\
You are a robot path planner for AlgoPython exercises.

Given a grid map and the primitive movement functions available (droite, gauche, bas, haut),
produce the **complete** list of unit-cell steps that takes the robot from its start cell (I)
to the goal cell (G), avoiding all obstacle cells (X).

Return ONLY valid JSON — no prose, no markdown fences:
{
  "steps": [
    {"from_row": int, "from_col": int, "to_row": int, "to_col": int,
     "direction": "right"|"left"|"up"|"down", "instruction": str, "step_num": int},
    ...
  ],
  "explanation": "one-sentence summary"
}

Rules:
- direction is the movement direction ("right"=col+1, "left"=col-1, "down"=row+1, "up"=row-1).
- instruction is the primitive name ("droite", "gauche", "bas", "haut").
- step_num starts at 1 and increments for every unit step.
- The path must not cross an X cell.
- The last step must land exactly on the G cell.
"""


def _grid_text(grid: list[list[str]]) -> str:
    return "\n".join(
        f"  row {r}: " + "  ".join(str(cell) for cell in row)
        for r, row in enumerate(grid)
    )


class RobotPathAgent:
    """Finds the complete robot path for a given exercise.

    Usage::

        agent = RobotPathAgent()
        path, drawings, xml_desc, summary = await agent.compute(exercise, grid_bounds)
    """

    def __init__(self) -> None:
        self._settings = get_settings()
        self._client = anthropic.AsyncAnthropic(api_key=self._settings.anthropic_api_key)

    # ── Public entry point ─────────────────────────────────────────────────────

    async def compute(
        self,
        exercise: dict,
        grid_bounds: dict,
        language: str = "fr",
    ) -> tuple[list[dict], list[dict], str, str]:
        """Find the path, then convert to drawing commands.

        Returns (path_steps, drawings, xml_description, decomposition_summary).
        """
        robot_map = exercise.get("robot_map") or {}
        path = await self.find_path(exercise, robot_map)
        drawings, color_map = steps_to_drawings(path, grid_bounds, robot_map)
        _, xml_desc, summary = compute_drawings(
            exercise, grid_bounds, path=path, language=language
        )
        return path, drawings, xml_desc, summary

    async def find_path(self, exercise: dict, robot_map: dict) -> list[dict]:
        """Return a complete path (reaching G) or the best partial path available.

        1. Tries every solution with the deterministic AST tracer.
        2. If none reach the goal, falls back to Claude with extended thinking.
        3. If Claude also fails, returns the longest partial path from step 1.
        """
        solutions = exercise.get("possible_solutions") or []
        logger.info(
            "[robot_path_agent] find_path: %d solution(s) to try, grid=%d×%d",
            len(solutions),
            robot_map.get("rows", 0),
            robot_map.get("cols", 0),
        )

        best_partial: list[dict] = []
        for idx, sol in enumerate(solutions):
            path = trace_path(sol, robot_map)
            if goal_reached(path, robot_map):
                logger.info(
                    "[robot_path_agent] solution %d/%d reaches the goal (%d steps)",
                    idx + 1, len(solutions), len(path),
                )
                return path
            if len(path) > len(best_partial):
                best_partial = path
                logger.debug(
                    "[robot_path_agent] solution %d/%d: partial path (%d steps)",
                    idx + 1, len(solutions), len(path),
                )

        # None of the stored solutions reaches G — fall back to Claude
        logger.warning(
            "[robot_path_agent] no stored solution reaches G — calling Claude with "
            "extended thinking (budget=%d tokens)", _THINKING_BUDGET,
        )
        claude_path = await self._claude_complete_path(best_partial, exercise, robot_map)
        if claude_path and goal_reached(claude_path, robot_map):
            logger.info(
                "[robot_path_agent] Claude completed the path (%d steps)", len(claude_path)
            )
            return claude_path

        # Last resort — return whatever we have (even if incomplete)
        fallback = claude_path if claude_path else best_partial
        logger.error(
            "[robot_path_agent] could not find a complete path; returning %d-step partial",
            len(fallback),
        )
        return fallback

    # ── Claude fallback ────────────────────────────────────────────────────────

    async def _claude_complete_path(
        self,
        partial: list[dict],
        exercise: dict,
        robot_map: dict,
    ) -> list[dict]:
        """Ask Claude (with extended thinking) to produce the full step list."""
        grid = robot_map.get("grid", [])
        rows = robot_map.get("rows", len(grid))
        cols = robot_map.get("cols", len(grid[0]) if grid else 0)

        start_row = start_col = goal_row = goal_col = 0
        for r, row in enumerate(grid):
            for c, cell in enumerate(row):
                if cell == "I":
                    start_row, start_col = r, c
                elif cell == "G":
                    goal_row, goal_col = r, c

        partial_summary = ""
        if partial:
            last = partial[-1]
            partial_summary = (
                f"A partial trace of {len(partial)} step(s) exists, ending at "
                f"row {last['to_row']}, col {last['to_col']}. "
                "You may extend or replace it entirely."
            )

        user_prompt = (
            f"Grid: {rows} rows × {cols} cols\n"
            f"Legend: O=free, X=obstacle, I=robot start, G=goal\n\n"
            f"{_grid_text(grid)}\n\n"
            f"Robot start: row {start_row}, col {start_col}\n"
            f"Goal:        row {goal_row},  col {goal_col}\n\n"
            + (partial_summary + "\n\n" if partial_summary else "")
            + "Produce the complete step list from (I) to (G), avoiding all X cells."
        )

        try:
            response = await self._client.messages.create(
                model=self._settings.orchestrator_model,
                max_tokens=_MAX_TOKENS,
                thinking={"type": "enabled", "budget_tokens": _THINKING_BUDGET},
                system=_CLAUDE_SYSTEM,
                messages=[{"role": "user", "content": user_prompt}],
            )
        except Exception as exc:
            logger.error("[robot_path_agent] Claude call failed: %s", exc)
            return []

        text = ""
        for block in response.content:
            if hasattr(block, "text") and block.text:
                text = block.text
                break

        return self._parse_steps(text, robot_map)

    # ── JSON parsing ───────────────────────────────────────────────────────────

    def _parse_steps(self, text: str, robot_map: dict) -> list[dict]:
        """Extract and validate the steps array from Claude's JSON response."""
        text = text.strip()

        # Try direct parse
        try:
            data = json.loads(text)
        except (json.JSONDecodeError, ValueError):
            m = re.search(r'\{.*\}', text, re.DOTALL)
            if m:
                try:
                    data = json.loads(m.group())
                except (json.JSONDecodeError, ValueError):
                    data = {}
            else:
                data = {}

        raw_steps = data.get("steps", [])
        if not raw_steps:
            logger.warning("[robot_path_agent] Claude returned no steps in: %.300s", text)
            return []

        # Validate and normalise each step
        grid = robot_map.get("grid", [])
        rows = robot_map.get("rows", len(grid))
        cols = robot_map.get("cols", len(grid[0]) if grid else 0)
        valid_dirs = {"right", "left", "up", "down"}

        steps: list[dict] = []
        for i, s in enumerate(raw_steps, 1):
            try:
                fr, fc = int(s["from_row"]), int(s["from_col"])
                tr, tc = int(s["to_row"]),   int(s["to_col"])
                direction = str(s.get("direction", "right")).lower()
                if direction not in valid_dirs:
                    direction = "right"
                instr = str(s.get("instruction", direction))

                # Boundary check
                if not (0 <= tr < rows and 0 <= tc < cols):
                    logger.warning("[robot_path_agent] step %d out of bounds (%d,%d) — skipping", i, tr, tc)
                    continue
                # Obstacle check
                if grid and grid[tr][tc] == "X":
                    logger.warning("[robot_path_agent] step %d hits obstacle (%d,%d) — skipping", i, tr, tc)
                    continue

                steps.append({
                    "from_row":    fr,
                    "from_col":    fc,
                    "to_row":      tr,
                    "to_col":      tc,
                    "direction":   direction,
                    "instruction": instr,
                    "step_num":    int(s.get("step_num", i)),
                })
            except (KeyError, TypeError, ValueError) as exc:
                logger.warning("[robot_path_agent] malformed step %d: %s — skipping", i, exc)

        logger.info("[robot_path_agent] parsed %d valid step(s) from Claude response", len(steps))
        return steps
