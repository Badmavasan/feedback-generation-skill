"""Claude-powered canvas detection for AlgoPython design (turtle graphics) exercises.

Design exercises have no grid — the student sees a split-screen view with:
  - A code editor on the left/top
  - A turtle graphics canvas on the right/bottom

This module asks Claude to locate the canvas boundaries so the deterministic
turtle path can be scaled and rendered onto the correct region of the image.
"""
from __future__ import annotations

import base64
import json
import logging
import re

import anthropic

from core.config import get_settings

logger = logging.getLogger(__name__)


_SYSTEM = """\
You are a precise image analyst for AlgoPython design exercise screenshots.

Your only job: locate the exact boundaries of the TURTLE GRAPHICS CANVAS within the screenshot.

The canvas is the rectangular drawing area where turtle graphics are rendered — typically
white or light-colored, bordered, and on the right or lower half of the screen.
It does NOT include: the code editor, toolbar, buttons, file tabs, or scrollbars.

Return ONLY valid JSON — no prose, no markdown fences:
{
  "canvas_x1": float,   // left edge as fraction of image width   [0.0–1.0]
  "canvas_y1": float,   // top edge as fraction of image height   [0.0–1.0]
  "canvas_x2": float,   // right edge as fraction of image width  [0.0–1.0]
  "canvas_y2": float,   // bottom edge as fraction of image height [0.0–1.0]
  "observations": string // one sentence describing what you see
}
"""

_PROMPT = """\
This is a screenshot of an AlgoPython design exercise (turtle graphics).

The screen typically shows a code editor alongside a drawing canvas where the turtle
produces geometric shapes.

Task: identify the exact pixel boundaries of the TURTLE GRAPHICS CANVAS only
(not the full screenshot, not the code editor).

Tips:
- The canvas is usually white or light grey, bordered by a thin frame.
- It is typically the larger panel (right half or lower half of the screen).
- The canvas does NOT include toolbars, score panels, or the code area.

Return ONLY the JSON object.
"""


class ClaudeDesignAnalyzer:
    """Uses Claude vision to locate the turtle canvas in a design exercise screenshot."""

    def __init__(self) -> None:
        self._settings = get_settings()
        self._client   = anthropic.AsyncAnthropic(api_key=self._settings.anthropic_api_key)

    def _parse_json(self, text: str) -> dict:
        text = text.strip()
        try:
            return json.loads(text)
        except (json.JSONDecodeError, ValueError):
            pass
        m = re.search(r'\{.*\}', text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group())
            except (json.JSONDecodeError, ValueError):
                pass
        logger.warning("[claude_design_analyzer] could not parse JSON from: %.200s", text)
        return {}

    async def analyze_image(self, image_bytes: bytes) -> dict:
        """Detect the turtle canvas bounds from the exercise screenshot.

        Returns dict with: canvas_x1, canvas_y1, canvas_x2, canvas_y2, observations.
        Falls back to sensible defaults (right 55% of image) if parsing fails.
        """
        b64 = base64.standard_b64encode(image_bytes).decode()
        try:
            response = await self._client.messages.create(
                model=self._settings.orchestrator_model,
                max_tokens=512,
                system=_SYSTEM,
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
                        {"type": "text", "text": _PROMPT},
                    ],
                }],
            )
            text = response.content[0].text if response.content else "{}"
        except Exception as exc:
            logger.error("[claude_design_analyzer] analyze_image failed: %s", exc)
            text = "{}"

        result = self._parse_json(text)

        # Clamp to valid fractional range; default to right ~55% of screen
        cx1 = max(0.0, min(0.49, float(result.get("canvas_x1", 0.42))))
        cy1 = max(0.0, min(0.49, float(result.get("canvas_y1", 0.05))))
        cx2 = max(cx1 + 0.1, min(1.0, float(result.get("canvas_x2", 0.98))))
        cy2 = max(cy1 + 0.1, min(1.0, float(result.get("canvas_y2", 0.95))))

        out = {
            "canvas_x1":   cx1,
            "canvas_y1":   cy1,
            "canvas_x2":   cx2,
            "canvas_y2":   cy2,
            "observations": result.get("observations", ""),
        }
        logger.info("[claude_design_analyzer] canvas bounds: %s", out)
        return out
