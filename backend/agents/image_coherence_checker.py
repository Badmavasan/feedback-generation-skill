"""Image coherence checker — analyzes annotated exercise images region by region."""
from __future__ import annotations

import asyncio
import base64
import io
import json
import re


def _parse_json(raw: str) -> dict:
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
    return {}


def _b64(image_bytes: bytes) -> str:
    return base64.standard_b64encode(image_bytes).decode("utf-8")


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
        self._model = None

    def _get_client(self):
        if self._client is None:
            import anthropic
            from core.config import get_settings
            settings = get_settings()
            self._client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
            self._model = settings.orchestrator_model
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
        from prompts.image import build_coherence_region_prompt

        client = self._get_client()
        prompt = build_coherence_region_prompt(region_name, decomposition_summary)

        response = await client.messages.create(
            model=self._model,
            max_tokens=512,
            temperature=0.0,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": _b64(region_bytes),
                        },
                    },
                    {"type": "text", "text": prompt},
                ],
            }],
        )
        text = response.content[0].text
        result = _parse_json(text)
        if not result:
            return {"has_relevant_annotation": False, "is_readable": False, "issues": [text[:200]]}
        return result

    async def _analyse_overall(
        self,
        annotated_bytes: bytes,
        decomposition_summary: str,
        loops: list[dict],
        reference_images: list[bytes] | None = None,
    ) -> dict:
        from prompts.image import build_coherence_overall_prompt

        client = self._get_client()
        prompt = build_coherence_overall_prompt(decomposition_summary, loops)

        content: list = []
        if reference_images:
            content.append({
                "type": "text",
                "text": (
                    "Reference annotation examples — use these to judge visual style, "
                    "decomposition clarity, and readability:"
                ),
            })
            for ref in reference_images:
                content.append({
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": _b64(ref),
                    },
                })
            content.append({"type": "text", "text": "Now evaluate this annotated image:"})

        content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/png",
                "data": _b64(annotated_bytes),
            },
        })
        content.append({"type": "text", "text": prompt})

        response = await client.messages.create(
            model=self._model,
            max_tokens=1024,
            temperature=0.0,
            messages=[{"role": "user", "content": content}],
        )
        text = response.content[0].text
        result = _parse_json(text)
        if not result:
            approved = '"approved": true' in text.lower()
            return {
                "approved": approved,
                "overall_score": 0.7 if approved else 0.4,
                "issues": [],
            }
        return result

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
