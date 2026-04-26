"""Claude-powered image analysis and annotation evaluation for robot exercises.

Replaces Gemini for:
  1. Grid bound detection — Claude reads the exercise screenshot and locates the grid area.
  2. Annotation evaluation — Claude checks whether the rendered arrows correctly
     represent the robot path.

Using Claude instead of Gemini gives more accurate spatial reasoning for grid calibration
and consistent eval verdicts across different exercise maps.
"""
from __future__ import annotations

import base64
import json
import logging
import re

import anthropic

from core.config import get_settings

logger = logging.getLogger(__name__)


# ── Grid detection prompts ─────────────────────────────────────────────────────

_ANALYSIS_SYSTEM = """\
You are a precise image analyst for AlgoPython robot exercise screenshots.

Your only job: locate the exact boundaries of the grid area within the screenshot.

The grid is a bordered rectangular region of equal-sized cells (typically green/grass tiles).
It does NOT include surrounding UI: toolbars, buttons, score panels, labels, or padding
outside the grid border.

Return ONLY valid JSON — no prose, no markdown fences:
{
  "grid_x1": float,      // left edge as fraction of image width   [0.0–1.0]
  "grid_y1": float,      // top edge as fraction of image height   [0.0–1.0]
  "grid_x2": float,      // right edge as fraction of image width  [0.0–1.0]
  "grid_y2": float,      // bottom edge as fraction of image height [0.0–1.0]
  "observations": string // one sentence describing what you see
}
"""

_ANALYSIS_PROMPT = """\
This is a screenshot of an AlgoPython robot exercise.

The logical grid is {rows} rows × {cols} cols.
Grid contents (O=free cell, X=obstacle, I=robot start, G=goal):

{grid_text}

Task: identify the exact pixel boundaries of the GRID AREA only (not the full screenshot).

Verification hints:
- The grid should contain exactly {rows} rows and {cols} equally-sized columns.
- Robot start cell (I) is at row {start_row}, col {start_col}.
- Goal cell (G) is at row {goal_row}, col {goal_col}.
- After you determine the bounds, check: does cell (I) visually fall inside
  the rectangle [grid_x1, grid_y1, grid_x2, grid_y2]?

Return ONLY the JSON object.
"""


# ── Evaluation prompts ─────────────────────────────────────────────────────────

_EVAL_SYSTEM = """\
You are evaluating an annotated AlgoPython robot exercise image.

The image shows the exercise grid with colored arrows drawn on top representing a robot path.

Return ONLY valid JSON — no prose, no markdown fences:
{
  "satisfied":      bool,
  "path_correct":   bool,
  "uniform_size":   bool,
  "readability":    bool,
  "path_coherent":  bool,
  "score":          float,   // 0.0–1.0
  "issues":         [string] // empty list when satisfied=true
}

Rules:
- satisfied=true only when ALL of: path_correct, uniform_size, readability, path_coherent.
- score: 1.0=all pass, 0.7=minor issue, 0.4=one clear failure, 0.0=path wrong or missing.
- issues: each entry is a concrete, actionable instruction for the next attempt.
"""

_EVAL_PROMPT = """\
Robot path information:
- Start: row {start_row}, col {start_col}  →  image fraction ≈ ({start_x:.3f}, {start_y:.3f})
- Goal:  row {goal_row},  col {goal_col}   →  image fraction ≈ ({goal_x:.3f},  {goal_y:.3f})
- Total move steps: {n_steps}
- Loop structure: {loop_summary}

Evaluate the annotated image on these four criteria:

1. PATH_CORRECT
   Do the arrows form a continuous path from start to goal?
   - The FIRST arrow must originate near ({start_x:.3f}, {start_y:.3f}).
   - The LAST arrow must end near ({goal_x:.3f}, {goal_y:.3f}).
   - Arrows must connect end-to-start with no gaps.

2. UNIFORM_SIZE
   Do all arrows of the same direction look the same length?
   (They should, since every cell has the same pixel size.)

3. READABILITY
   Are arrows clearly visible, non-overlapping, and easy to follow?

4. PATH_COHERENT
   Does the path make geometric sense on the grid?
   (No teleportation, no arrows pointing into walls, no backward jumps.)

Return the JSON.
"""


# ── Agent ──────────────────────────────────────────────────────────────────────

class ClaudeImageAnalyzer:
    """Uses Claude vision to analyze exercise screenshots and evaluate annotated images."""

    def __init__(self) -> None:
        self._settings = get_settings()
        self._client = anthropic.AsyncAnthropic(api_key=self._settings.anthropic_api_key)

    def _parse_json(self, text: str) -> dict:
        """Parse JSON from Claude response, with fallback extraction."""
        text = text.strip()
        try:
            return json.loads(text)
        except (json.JSONDecodeError, ValueError):
            pass
        # Try to extract the first {...} block
        m = re.search(r'\{.*\}', text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group())
            except (json.JSONDecodeError, ValueError):
                pass
        logger.warning("[claude_analyzer] could not parse JSON from: %.200s", text)
        return {}

    async def analyze_image(self, image_bytes: bytes, exercise: dict) -> dict:
        """Detect grid bounds from the exercise screenshot using Claude vision.

        Returns dict with: grid_x1, grid_y1, grid_x2, grid_y2, observations.
        Falls back to sensible defaults if parsing fails.
        """
        robot_map = (exercise or {}).get("robot_map") or {}
        grid      = robot_map.get("grid", [])
        rows      = robot_map.get("rows", len(grid))
        cols      = robot_map.get("cols", len(grid[0]) if grid else 0)

        start_row = start_col = goal_row = goal_col = 0
        for r, row in enumerate(grid):
            for c, cell in enumerate(row):
                if cell == "I":
                    start_row, start_col = r, c
                elif cell == "G":
                    goal_row, goal_col = r, c

        grid_text = "\n".join(
            f"  row {r}: " + "  ".join(str(cell) for cell in row)
            for r, row in enumerate(grid)
        )

        user_prompt = _ANALYSIS_PROMPT.format(
            rows=rows, cols=cols,
            grid_text=grid_text,
            start_row=start_row, start_col=start_col,
            goal_row=goal_row,   goal_col=goal_col,
        )

        b64 = base64.standard_b64encode(image_bytes).decode()
        try:
            response = await self._client.messages.create(
                model=self._settings.orchestrator_model,
                max_tokens=512,
                system=_ANALYSIS_SYSTEM,
                messages=[{
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type":       "base64",
                                "media_type": "image/png",
                                "data":       b64,
                            },
                        },
                        {"type": "text", "text": user_prompt},
                    ],
                }],
            )
            text = response.content[0].text if response.content else "{}"
        except Exception as exc:
            logger.error("[claude_analyzer] analyze_image failed: %s", exc)
            text = "{}"

        result = self._parse_json(text)

        # Clamp to valid fractional range
        gx1 = max(0.0, min(0.49, float(result.get("grid_x1", 0.05))))
        gy1 = max(0.0, min(0.49, float(result.get("grid_y1", 0.05))))
        gx2 = max(gx1 + 0.1, min(1.0, float(result.get("grid_x2", 0.95))))
        gy2 = max(gy1 + 0.1, min(1.0, float(result.get("grid_y2", 0.95))))

        out = {
            "grid_x1":      gx1,
            "grid_y1":      gy1,
            "grid_x2":      gx2,
            "grid_y2":      gy2,
            "observations": result.get("observations", ""),
        }
        logger.info("[claude_analyzer] grid bounds: %s", out)
        return out

    async def evaluate_annotation(
        self,
        annotated_bytes: bytes,
        exercise: dict,
        path_steps: list[dict],
        grid_bounds: dict,
    ) -> dict:
        """Evaluate whether the annotated image correctly represents the robot path.

        Returns {"satisfied": bool, "score": float, "path_coherent": bool, "issues": list}.
        """
        robot_map = (exercise or {}).get("robot_map") or {}
        grid      = robot_map.get("grid", [])
        rows      = robot_map.get("rows", len(grid))
        cols      = robot_map.get("cols", len(grid[0]) if grid else 0)

        start_row = start_col = goal_row = goal_col = 0
        for r, row in enumerate(grid):
            for c, cell in enumerate(row):
                if cell == "I":
                    start_row, start_col = r, c
                elif cell == "G":
                    goal_row, goal_col = r, c

        gx1 = float(grid_bounds.get("grid_x1", 0.05))
        gy1 = float(grid_bounds.get("grid_y1", 0.05))
        gx2 = float(grid_bounds.get("grid_x2", 0.95))
        gy2 = float(grid_bounds.get("grid_y2", 0.95))
        cw  = (gx2 - gx1) / cols if cols else 0.1
        ch  = (gy2 - gy1) / rows if rows else 0.1

        start_x = gx1 + (start_col + 0.5) * cw
        start_y = gy1 + (start_row + 0.5) * ch
        goal_x  = gx1 + (goal_col  + 0.5) * cw
        goal_y  = gy1 + (goal_row  + 0.5) * ch

        loop_indices = {s["loop_idx"] for s in path_steps if s.get("loop_idx") is not None}
        n_loops = len(loop_indices)
        loop_summary = (
            f"{n_loops} loop(s): first loop = blue arrows"
            + (", second loop = pink arrows" if n_loops > 1 else "")
            if n_loops else
            "no explicit loops — flat sequence, all blue arrows"
        )

        user_prompt = _EVAL_PROMPT.format(
            start_row=start_row, start_col=start_col,
            start_x=start_x,    start_y=start_y,
            goal_row=goal_row,   goal_col=goal_col,
            goal_x=goal_x,       goal_y=goal_y,
            n_steps=len(path_steps),
            loop_summary=loop_summary,
        )

        b64 = base64.standard_b64encode(annotated_bytes).decode()
        try:
            response = await self._client.messages.create(
                model=self._settings.orchestrator_model,
                max_tokens=512,
                system=_EVAL_SYSTEM,
                messages=[{
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type":       "base64",
                                "media_type": "image/png",
                                "data":       b64,
                            },
                        },
                        {"type": "text", "text": user_prompt},
                    ],
                }],
            )
            text = response.content[0].text if response.content else "{}"
        except Exception as exc:
            logger.error("[claude_analyzer] evaluate_annotation failed: %s", exc)
            text = "{}"

        result = self._parse_json(text)
        return {
            "satisfied":     bool(result.get("satisfied",    False)),
            "score":         float(result.get("score",       0.5)),
            "path_coherent": bool(result.get("path_coherent", True)),
            "issues":        list(result.get("issues",       [])),
        }
