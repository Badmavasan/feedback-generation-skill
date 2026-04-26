"""Gemini 2.5 Pro image analysis + PIL annotation rendering."""
from __future__ import annotations

import asyncio
import io
import json
import math

from agents.base import BaseAgent
from core.config import get_settings


# ── Color palette ──────────────────────────────────────────────────────────────

_COLORS: dict[str, tuple[int, int, int]] = {
    "blue":   (59, 130, 246),
    "pink":   (236, 72, 153),
    "orange": (249, 115, 22),
    "white":  (255, 255, 255),
    "yellow": (250, 204, 21),
    "red":    (239, 68, 68),
    "green":  (34, 197, 94),
    "purple": (168, 85, 247),
    "teal":   (20, 184, 166),
    "rose":   (244, 63, 94),
}


def _color(name: str) -> tuple[int, int, int]:
    return _COLORS.get((name or "blue").lower(), (59, 130, 246))


# ── PIL drawing primitives ─────────────────────────────────────────────────────

def _arrowhead(draw, x1: float, y1: float, x2: float, y2: float,
               color: tuple, stroke: int) -> None:
    """Filled triangle arrowhead at (x2, y2) pointing from (x1, y1)."""
    head_len = max(stroke * 5, 14)
    head_w   = max(int(stroke * 2.2), 7)
    angle = math.atan2(y2 - y1, x2 - x1)
    perp  = angle + math.pi / 2
    bx = x2 - math.cos(angle) * head_len
    by = y2 - math.sin(angle) * head_len
    tip  = (int(x2), int(y2))
    left = (int(bx + math.cos(perp) * head_w), int(by + math.sin(perp) * head_w))
    rght = (int(bx - math.cos(perp) * head_w), int(by - math.sin(perp) * head_w))
    # White outline for visibility on any background
    draw.polygon([tip, left, rght], outline=(255, 255, 255, 220), fill=(*color, 240))


def _hq_arrow(draw, x1: float, y1: float, x2: float, y2: float,
              color: tuple, stroke: int) -> None:
    """Solid arrow with dark drop shadow + filled triangle arrowhead."""
    head_len = max(stroke * 5, 14)
    angle = math.atan2(y2 - y1, x2 - x1)
    # Stop the line body just before the arrowhead base
    lx2 = int(x2 - math.cos(angle) * (head_len - 2))
    ly2 = int(y2 - math.sin(angle) * (head_len - 2))
    # Dark drop shadow (preserves color vibrancy)
    draw.line([(x1 + 2, y1 + 2), (lx2 + 2, ly2 + 2)], fill=(0, 0, 0, 70), width=stroke + 2)
    # Colored line — full opacity for vivid colors
    draw.line([(x1, y1), (lx2, ly2)], fill=(*color, 248), width=stroke)
    _arrowhead(draw, x1, y1, x2, y2, color, stroke)


def _hq_dashed_arrow(draw, x1: float, y1: float, x2: float, y2: float,
                     color: tuple, stroke: int) -> None:
    """Dashed arrow (transitions / approach paths)."""
    dx, dy = x2 - x1, y2 - y1
    length = math.sqrt(dx * dx + dy * dy)
    if length < 1:
        return
    ux, uy = dx / length, dy / length
    dash = max(10, stroke * 4)
    gap  = max(5,  stroke * 2)
    pos, on = 0.0, True
    while pos < length:
        end = min(pos + (dash if on else gap), length)
        if on:
            sx, sy = x1 + ux * pos,  y1 + uy * pos
            ex, ey = x1 + ux * end,  y1 + uy * end
            draw.line([(sx + 2, sy + 2), (ex + 2, ey + 2)], fill=(0, 0, 0, 55), width=stroke)
            draw.line([(sx, sy), (ex, ey)], fill=(*color, 245), width=stroke)
        pos = end
        on = not on
    _arrowhead(draw, x1, y1, x2, y2, color, stroke)


def _hq_turn(draw, cx: float, cy: float, from_dir: str, to_dir: str,
             color: tuple, size: int) -> None:
    """L-shaped elbow arrow for a 90° direction change."""
    vecs = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}
    d1 = vecs.get(from_dir, (0, -1))
    d2 = vecs.get(to_dir, (1, 0))
    arm = size
    p_in  = (cx - d1[0] * arm, cy - d1[1] * arm)
    p_out = (cx + d2[0] * arm, cy + d2[1] * arm)
    w = max(2, size // 5)
    # White halo
    draw.line([p_in, (cx, cy), p_out], fill=(255, 255, 255, 150), width=w + 4)
    # Colored elbow
    draw.line([p_in, (cx, cy), p_out], fill=(*color, 230), width=w)
    _arrowhead(draw, cx, cy, p_out[0], p_out[1], color, w)


def _hq_marker(draw, cx: float, cy: float, direction: str,
               color: tuple, size: int) -> None:
    """Filled chevron marking the robot start position."""
    dir_angles = {"right": 0, "down": 90, "left": 180, "up": 270}
    a = math.radians(dir_angles.get(direction, 0))
    spread = math.pi * 0.45
    tip = (cx + math.cos(a) * size,          cy + math.sin(a) * size)
    b1  = (cx + math.cos(a + math.pi - spread) * size * 0.65,
           cy + math.sin(a + math.pi - spread) * size * 0.65)
    b2  = (cx + math.cos(a + math.pi + spread) * size * 0.65,
           cy + math.sin(a + math.pi + spread) * size * 0.65)
    pts = [(int(p[0]), int(p[1])) for p in (tip, b1, b2)]
    draw.polygon(pts, outline=(255, 255, 255, 220), fill=(*color, 225))


def _hq_badge_circle(draw, cx: float, cy: float, text: str,
                     color: tuple, radius: int, font) -> None:
    """Circular badge: white fill with colored outline."""
    r = radius
    draw.ellipse(
        [(int(cx - r), int(cy - r)), (int(cx + r), int(cy + r))],
        outline=(*color, 255), fill=(255, 255, 255, 245),
        width=max(2, radius // 7),
    )
    if text:
        draw.text((int(cx), int(cy)), str(text), font=font,
                  fill=(25, 25, 25, 255), anchor="mm")


def _hq_badge(draw, cx: float, cy: float, text: str,
              color: tuple, radius: int, font) -> None:
    """Small hexagonal badge: white fill with colored outline for maximum text contrast."""
    pts = [
        (int(cx + radius * math.cos(math.radians(60 * i - 30))),
         int(cy + radius * math.sin(math.radians(60 * i - 30))))
        for i in range(6)
    ]
    # White fill + 2px colored outline → dark text is always readable
    draw.polygon(pts, outline=(*color, 255), fill=(255, 255, 255, 245))
    # Draw colored outline a second time with width to make it thicker
    for i in range(6):
        p1 = pts[i]
        p2 = pts[(i + 1) % 6]
        draw.line([p1, p2], fill=(*color, 255), width=max(2, radius // 7))
    if text:
        draw.text((int(cx), int(cy)), str(text), font=font,
                  fill=(25, 25, 25, 255), anchor="mm")


# ── Main drawing function ──────────────────────────────────────────────────────

def images_visually_identical(img1_bytes: bytes, img2_bytes: bytes) -> bool:
    """Return True when two PNG images are pixel-for-pixel identical after RGB conversion.

    Used to detect when draw_annotations produced no visible change (empty drawings,
    zero-length arrows, or any other failure that leaves the image unchanged).
    Uses PIL ImageChops.difference — no numpy dependency required.
    """
    import PIL.Image
    import PIL.ImageChops
    img1 = PIL.Image.open(io.BytesIO(img1_bytes)).convert("RGB")
    img2 = PIL.Image.open(io.BytesIO(img2_bytes)).convert("RGB")
    if img1.size != img2.size:
        return False
    diff = PIL.ImageChops.difference(img1, img2)
    return diff.getbbox() is None   # None → no differing pixel found


def draw_annotations(image_bytes: bytes, drawings: list[dict]) -> bytes:
    """
    Render annotation drawings onto an image using high-quality PIL primitives.

    Supported drawing types (all coordinates are fractions 0.0–1.0):
      arrow  : {type, x1, y1, x2, y2, color, dashed=False}
      marker : {type, x, y, direction, color}
      badge  : {type, x, y, text, color, large=False}

    Colors: "blue" | "pink" | "orange" | "yellow"
    Note: "turn" type is silently ignored — direction changes are shown by arrow direction.
    """
    import PIL.Image
    import PIL.ImageDraw
    import PIL.ImageFont

    img = PIL.Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    W, H = img.size
    overlay = PIL.Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = PIL.ImageDraw.Draw(overlay)

    font_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
    ]

    def _load_font(size: int):
        f = PIL.ImageFont.load_default()
        for fp in font_paths:
            try:
                f = PIL.ImageFont.truetype(fp, size)
                break
            except (IOError, OSError):
                continue
        return f

    stroke = max(3, W // 120)

    _width_factors = {"thin": 0.6, "normal": 1.0, "thick": 1.6}

    for d in drawings:
        dtype = (d.get("type") or "").lower()
        c     = _color(d.get("color", "blue"))

        if dtype == "arrow":
            x1 = int(d.get("x1", 0.1) * W)
            y1 = int(d.get("y1", 0.1) * H)
            x2 = int(d.get("x2", 0.5) * W)
            y2 = int(d.get("y2", 0.5) * H)
            w_factor = _width_factors.get((d.get("width") or "normal").lower(), 1.0)
            s = max(2, int(stroke * w_factor))
            if d.get("dashed", False):
                _hq_dashed_arrow(draw, x1, y1, x2, y2, c, s)
            else:
                _hq_arrow(draw, x1, y1, x2, y2, c, s)

        elif dtype == "marker":
            x    = int(d.get("x", 0.5) * W)
            y    = int(d.get("y", 0.5) * H)
            size = max(12, min(W // 28, H // 10))
            _hq_marker(draw, x, y, d.get("direction", "right"), c, size)

        elif dtype == "badge":
            x     = int(d.get("x", 0.5) * W)
            y     = int(d.get("y", 0.5) * H)
            large = d.get("large", False)
            shape = (d.get("shape") or "hex").lower()
            # Large badges (for-loop iteration counters) must be clearly legible
            r = max(18, min(W // 28, H // 10)) if large else max(7, min(W // 72, H // 26))
            f = _load_font(max(10, int(r * 0.90)))
            if shape == "circle":
                _hq_badge_circle(draw, x, y, d.get("text", ""), c, r, f)
            else:
                _hq_badge(draw, x, y, d.get("text", ""), c, r, f)

        elif dtype == "dot":
            x = int(d.get("x", 0.5) * W)
            y = int(d.get("y", 0.5) * H)
            r = max(5, W // 90)
            draw.ellipse([(x - r, y - r), (x + r, y + r)],
                         fill=(*c, 220), outline=(255, 255, 255, 180), width=2)

    out = PIL.Image.alpha_composite(img, overlay).convert("RGB")
    buf = io.BytesIO()
    out.save(buf, format="PNG")
    return buf.getvalue()


# Backwards-compatibility alias (old code used render_annotations)
render_annotations = draw_annotations


# ── Response text extractor (handles thinking-model None text) ─────────────────

def _extract_text(response) -> str:
    """Return the text from a Gemini response, handling thinking-model responses
    where response.text may be None (thinking tokens don't count as text parts)."""
    if response.text is not None:
        return response.text
    # Fallback: walk candidates → content → parts, skipping thought parts
    try:
        for candidate in (response.candidates or []):
            texts = []
            for part in (candidate.content.parts or []):
                if getattr(part, "thought", False):
                    continue
                text = getattr(part, "text", None)
                if text:
                    texts.append(text)
            if texts:
                return "".join(texts)
    except Exception:
        pass
    return ""


# ── Agent ──────────────────────────────────────────────────────────────────────

class GeminiImageAgent(BaseAgent):
    """Gemini 2.5 Pro for image analysis + quality evaluation. PIL for rendering."""

    def __init__(self) -> None:
        self._client = None

    def _get_client(self):
        if self._client is None:
            from google import genai
            self._client = genai.Client(api_key=get_settings().google_api_key)
        return self._client

    def _json_call(self, image_bytes: bytes, prompt: str, thinking_budget: int = 2048,
                   reference_images: list[bytes] | None = None) -> str:
        """Synchronous Gemini call returning JSON text.

        When reference_images are provided they are prepended to the contents so
        Gemini can cross-reference visual style when evaluating.
        """
        from google.genai import types
        client   = self._get_client()
        settings = get_settings()

        contents: list = []
        if reference_images:
            contents.append("Reference annotation examples — use these to judge visual style and clarity:")
            for ref in reference_images:
                contents.append(types.Part.from_bytes(data=ref, mime_type="image/png"))
            contents.append("Now evaluate the following annotated image:")
        contents.append(types.Part.from_bytes(data=image_bytes, mime_type="image/png"))
        contents.append(prompt)

        response = client.models.generate_content(
            model=settings.gemini_model,
            contents=contents,
            config=types.GenerateContentConfig(
                temperature=0.0,
                max_output_tokens=512 + thinking_budget,
                response_mime_type="application/json",
                thinking_config=types.ThinkingConfig(thinking_budget=thinking_budget),
            ),
        )
        return _extract_text(response).strip()

    async def analyze_image(self, image_bytes: bytes, prompt: str) -> dict:
        """Ask Gemini to analyze the exercise image and return structured JSON.

        Returns dict with at minimum:
          grid_x1, grid_y1, grid_x2, grid_y2  (grid bounds as image fractions)
          observations                          (text description of what Gemini sees)
        """
        loop = asyncio.get_event_loop()
        text = await loop.run_in_executor(None, lambda: self._json_call(image_bytes, prompt, thinking_budget=2048))
        try:
            return json.loads(text)
        except (json.JSONDecodeError, ValueError):
            return {}

    async def evaluate_annotation(self, image_bytes: bytes, eval_prompt: str,
                                   reference_images: list[bytes] | None = None) -> dict:
        """Evaluate whether the annotated image satisfies the user's request.

        reference_images: optional list of gold-standard PNGs shown to Gemini for
          style cross-referencing before the annotated image.

        Returns {"satisfied": bool, "score": float, "issues": list[str]}.
        """
        loop = asyncio.get_event_loop()
        refs = reference_images if reference_images else None
        text = await loop.run_in_executor(
            None,
            lambda: self._json_call(image_bytes, eval_prompt, thinking_budget=4096,
                                    reference_images=refs),
        )
        try:
            result = json.loads(text)
        except (json.JSONDecodeError, ValueError):
            result = {}
        # path_coherent defaults to True when not returned (old eval prompts without grid info)
        path_coherent = result.get("path_coherent")
        return {
            "satisfied":     bool(result.get("satisfied", False)),
            "score":         float(result.get("score", 0.5)),
            "path_coherent": bool(path_coherent) if path_coherent is not None else True,
            "issues":        list(result.get("issues", [])),
        }

    # ── Kept for backwards compatibility ──────────────────────────────────────

    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.4,
        max_tokens: int = 1024,
        reference_images: list[bytes] | None = None,
        user_image: bytes | None = None,
        **kwargs,
    ) -> str:
        from google.genai import types
        client   = self._get_client()
        settings = get_settings()
        parts: list = []
        if reference_images:
            parts.append("Style reference images:")
            for rb in reference_images:
                parts.append(types.Part.from_bytes(data=rb, mime_type="image/png"))
        if user_image:
            parts.append(types.Part.from_bytes(data=user_image, mime_type="image/png"))
        parts.append(user_prompt)
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: client.models.generate_content(
                model=settings.gemini_model,
                contents=parts,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    temperature=temperature,
                    max_output_tokens=max_tokens + 8192,
                    response_mime_type="application/json",
                    thinking_config=types.ThinkingConfig(thinking_budget=8192),
                ),
            ),
        )
        return _extract_text(response).strip()

    async def annotate_image(self, image_bytes: bytes, annotation_prompt: str = "",
                             annotations: list[dict] | None = None, caption: str = "", **kwargs) -> bytes:
        return draw_annotations(image_bytes, annotations or [])

    async def detect_grid(self, image_bytes: bytes, detection_prompt: str) -> dict:
        """Backwards-compatible wrapper — use analyze_image for new code."""
        return await self.analyze_image(image_bytes, detection_prompt)

    async def verify_image(self, image_bytes: bytes, verification_prompt: str, **kwargs) -> dict:
        from google.genai import types
        client   = self._get_client()
        settings = get_settings()
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: client.models.generate_content(
                model=settings.gemini_model,
                contents=[verification_prompt,
                          types.Part.from_bytes(data=image_bytes, mime_type="image/png")],
                config=types.GenerateContentConfig(
                    temperature=0.1,
                    max_output_tokens=512 + 2048,
                    response_mime_type="application/json",
                    thinking_config=types.ThinkingConfig(thinking_budget=2048),
                ),
            ),
        )
        text = _extract_text(response)
        try:
            return json.loads(text)
        except (json.JSONDecodeError, ValueError):
            approved = '"approved": true' in text.lower()
            return {"approved": approved, "issues": [], "quality_score": 0.7 if approved else 0.4}
