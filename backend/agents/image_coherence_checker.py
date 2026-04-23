"""Image coherence checker — analyzes annotated exercise images region by region."""
from __future__ import annotations

import asyncio
import io
import json


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
            import google.generativeai as genai
            from core.config import get_settings
            genai.configure(api_key=get_settings().google_api_key)
            self._client = genai
        return self._client

    def _crop_region(self, pil_image, bbox: tuple[float, float, float, float]):
        """Crop a PIL image to (x0_frac, y0_frac, x1_frac, y1_frac) fractions."""
        w, h = pil_image.size
        x0 = int(bbox[0] * w)
        y0 = int(bbox[1] * h)
        x1 = int(bbox[2] * w)
        y1 = int(bbox[3] * h)
        return pil_image.crop((x0, y0, x1, y1))

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
        import google.generativeai as genai
        from core.config import get_settings
        from prompts.image import build_coherence_region_prompt

        self._get_client()

        import PIL.Image
        pil = PIL.Image.open(io.BytesIO(region_bytes))
        model = genai.GenerativeModel(model_name=get_settings().gemini_model)
        prompt = build_coherence_region_prompt(region_name, decomposition_summary)

        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: model.generate_content(
                [prompt, pil],
                generation_config=genai.types.GenerationConfig(
                    temperature=0.0,
                    max_output_tokens=256,
                    response_mime_type="application/json",
                ),
            ),
        )
        try:
            return json.loads(response.text)
        except (json.JSONDecodeError, ValueError):
            return {"has_relevant_annotation": False, "is_readable": False, "issues": [response.text[:200]]}

    async def _analyse_overall(
        self,
        annotated_bytes: bytes,
        decomposition_summary: str,
        loops: list[dict],
    ) -> dict:
        import google.generativeai as genai
        from core.config import get_settings
        from prompts.image import build_coherence_overall_prompt

        self._get_client()

        import PIL.Image
        pil = PIL.Image.open(io.BytesIO(annotated_bytes))
        model = genai.GenerativeModel(model_name=get_settings().gemini_model)
        prompt = build_coherence_overall_prompt(decomposition_summary, loops)

        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: model.generate_content(
                [prompt, pil],
                generation_config=genai.types.GenerationConfig(
                    temperature=0.0,
                    max_output_tokens=512,
                    response_mime_type="application/json",
                ),
            ),
        )
        try:
            return json.loads(response.text)
        except (json.JSONDecodeError, ValueError):
            text = response.text
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
    ) -> dict:
        """
        Crop the annotated image into 4 regions, analyse each, then run an overall check.

        Returns:
            {
              approved: bool,
              overall_score: float,
              region_scores: {region_name: {has_annotation, is_readable, issues}},
              issues: [str],   # aggregated issues from all regions + overall
            }
        """
        pil = self._bytes_to_pil(annotated_bytes)

        # Region analysis (concurrent)
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

        # Overall analysis
        overall = await self._analyse_overall(annotated_bytes, decomposition_summary, loops)

        # Aggregate issues
        all_issues: list[str] = list(overall.get("issues", []))
        for rname, rdata in region_results.items():
            for issue in rdata.get("issues", []):
                all_issues.append(f"[{rname}] {issue}")

        # Score: weight overall 60%, region readability 40%
        readable_regions = sum(
            1 for r in region_results.values() if r.get("is_readable", True)
        )
        region_score = readable_regions / len(_REGIONS)
        overall_score = overall.get("overall_score", 0.5)
        combined_score = 0.6 * overall_score + 0.4 * region_score

        return {
            "approved": overall.get("approved", False),
            "overall_score": round(combined_score, 3),
            "quality_score": round(combined_score, 3),  # alias for existing callers
            "region_scores": region_results,
            "issues": all_issues,
        }
