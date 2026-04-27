"""Image coherence checker — analyzes annotated exercise images region by region."""
from __future__ import annotations

import asyncio
import io
import json


def _extract_text(response) -> str:
    if response.text is not None:
        return response.text
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


_REGIONS = {
    "top-left":     (0.0, 0.0, 0.5, 0.5),
    "top-right":    (0.5, 0.0, 1.0, 0.5),
    "bottom-left":  (0.0, 0.5, 0.5, 1.0),
    "bottom-right": (0.5, 0.5, 1.0, 1.0),
}


class ImageCoherenceChecker:
    """
    Analyses an annotated image by:
    1. Cropping it into 4 quadrant regions and checking each one individually.
    2. Running a final overall-image check.

    Returns a verdict compatible with the iteration loop in _run_image_generation.
    """

    def __init__(self) -> None:
        self._client = None

    def _get_client(self):
        if self._client is None:
            from google import genai
            from core.config import get_settings
            self._client = genai.Client(api_key=get_settings().google_api_key)
        return self._client

    def _crop_region(self, pil_image, bbox: tuple[float, float, float, float]):
        w, h = pil_image.size
        return pil_image.crop((
            int(bbox[0] * w), int(bbox[1] * h),
            int(bbox[2] * w), int(bbox[3] * h),
        ))

    def _bytes_to_pil(self, image_bytes: bytes):
        import PIL.Image
        return PIL.Image.open(io.BytesIO(image_bytes))

    def _pil_to_bytes(self, pil_image) -> bytes:
        buf = io.BytesIO()
        pil_image.save(buf, format="PNG")
        return buf.getvalue()

    async def _analyse_region(
        self,
        region_name: str,
        region_bytes: bytes,
        decomposition_summary: str,
    ) -> dict:
        from google.genai import types
        from core.config import get_settings
        from prompts.image import build_coherence_region_prompt

        client = self._get_client()
        settings = get_settings()
        prompt = build_coherence_region_prompt(region_name, decomposition_summary)

        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: client.models.generate_content(
                model=settings.gemini_model,
                contents=[
                    prompt,
                    types.Part.from_bytes(data=region_bytes, mime_type="image/png"),
                ],
                config=types.GenerateContentConfig(
                    temperature=0.0,
                    max_output_tokens=256 + 2048,
                    response_mime_type="application/json",
                    thinking_config=types.ThinkingConfig(thinking_budget=2048),
                ),
            ),
        )
        text = _extract_text(response)
        try:
            return json.loads(text)
        except (json.JSONDecodeError, ValueError):
            return {"has_relevant_annotation": False, "is_readable": False, "issues": [text[:200]]}

    async def _analyse_overall(
        self,
        annotated_bytes: bytes,
        decomposition_summary: str,
        loops: list[dict],
        reference_images: list[bytes] | None = None,
    ) -> dict:
        from google.genai import types
        from core.config import get_settings
        from prompts.image import build_coherence_overall_prompt

        client = self._get_client()
        settings = get_settings()
        prompt = build_coherence_overall_prompt(decomposition_summary, loops)

        contents: list = []
        if reference_images:
            contents.append(
                "Reference annotation examples — use these to judge visual style, "
                "decomposition clarity, and readability:"
            )
            for ref in reference_images:
                contents.append(types.Part.from_bytes(data=ref, mime_type="image/png"))
            contents.append("Now evaluate this annotated image:")
        contents.append(types.Part.from_bytes(data=annotated_bytes, mime_type="image/png"))
        contents.append(prompt)

        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: client.models.generate_content(
                model=settings.gemini_model,
                contents=contents,
                config=types.GenerateContentConfig(
                    temperature=0.0,
                    max_output_tokens=512 + 4096,
                    response_mime_type="application/json",
                    thinking_config=types.ThinkingConfig(thinking_budget=4096),
                ),
            ),
        )
        text = _extract_text(response)
        try:
            return json.loads(text)
        except (json.JSONDecodeError, ValueError):
            approved = '"approved": true' in text.lower()
            return {
                "approved": approved,
                "overall_score": 0.7 if approved else 0.4,
                "issues": [],
            }

    async def check(
        self,
        annotated_bytes: bytes,
        decomposition_summary: str,
        loops: list[dict],
        reference_images: list[bytes] | None = None,
    ) -> dict:
        """
        Crop the annotated image into 4 regions, analyse each, then run an overall check.

        Returns:
            {
              approved: bool,
              overall_score: float,
              region_scores: {region_name: {has_annotation, is_readable, issues}},
              issues: [str],
            }
        """
        pil = self._bytes_to_pil(annotated_bytes)

        region_tasks = {
            name: asyncio.create_task(
                self._analyse_region(
                    name,
                    self._pil_to_bytes(self._crop_region(pil, bbox)),
                    decomposition_summary,
                )
            )
            for name, bbox in _REGIONS.items()
        }
        region_results = {name: await task for name, task in region_tasks.items()}

        overall = await self._analyse_overall(
            annotated_bytes, decomposition_summary, loops,
            reference_images=reference_images,
        )

        all_issues: list[str] = list(overall.get("issues", []))
        for rname, rdata in region_results.items():
            for issue in rdata.get("issues", []):
                all_issues.append(f"[{rname}] {issue}")

        readable_regions = sum(
            1 for r in region_results.values() if r.get("is_readable", True)
        )
        region_score = readable_regions / len(_REGIONS)
        overall_score = overall.get("overall_score", 0.5)
        combined_score = 0.6 * overall_score + 0.4 * region_score

        return {
            "approved": overall.get("approved", False),
            "overall_score": round(combined_score, 3),
            "quality_score": round(combined_score, 3),
            "region_scores": region_results,
            "issues": all_issues,
        }
