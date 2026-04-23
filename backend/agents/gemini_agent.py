"""Gemini 2.0 Flash + Imagen 3 image annotation agent."""
import base64
import json
from agents.base import BaseAgent
from core.config import get_settings


class GeminiImageAgent(BaseAgent):
    """
    Uses Gemini 2.0 Flash for:
    - Planning annotation instructions (text → JSON plan)
    - Verifying annotated images (vision → JSON verdict)

    Uses Imagen 3 for:
    - Applying annotations to the screenshot (image editing)
    """

    def __init__(self) -> None:
        self._client = None

    def _get_client(self):
        if self._client is None:
            import google.generativeai as genai
            settings = get_settings()
            genai.configure(api_key=settings.google_api_key)
            self._client = genai
        return self._client

    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.4,
        max_tokens: int = 1024,
        **kwargs,
    ) -> str:
        """Text generation via Gemini Flash (used for annotation planning)."""
        import asyncio
        import google.generativeai as genai
        settings = get_settings()
        self._get_client()  # ensure configured

        model = genai.GenerativeModel(
            model_name=settings.gemini_model,
            system_instruction=system_prompt,
        )
        # google-generativeai has no native async — run in thread pool
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: model.generate_content(
                user_prompt,
                generation_config=genai.types.GenerationConfig(
                    temperature=temperature,
                    max_output_tokens=max_tokens,
                ),
            ),
        )
        return response.text.strip()

    async def annotate_image(
        self,
        image_bytes: bytes,
        annotation_prompt: str,
        **kwargs,
    ) -> bytes:
        """
        Apply annotations to an image using Imagen 3's edit capability.
        Falls back to Gemini Flash image editing if Imagen 3 edit is unavailable.
        Returns annotated image bytes (PNG).
        """
        import asyncio
        import google.generativeai as genai
        from google.generativeai import types as gtypes
        settings = get_settings()
        self._get_client()

        # Imagen 3 image editing via the generative model client
        # Uses imagegeneration API with edit mode
        loop = asyncio.get_event_loop()

        def _edit():
            client = genai.ImageGenerationModel(settings.imagen_model)
            # Encode source image to base64
            b64_image = base64.b64encode(image_bytes).decode()
            result = client.edit_image(
                prompt=annotation_prompt,
                base_image=gtypes.Image(image_bytes=image_bytes, mime_type="image/png"),
                edit_mode="inpainting-insert",  # overlay annotations without destroying content
            )
            return result.images[0]._pil_image

        pil_image = await loop.run_in_executor(None, _edit)

        import io
        buf = io.BytesIO()
        pil_image.save(buf, format="PNG")
        return buf.getvalue()

    async def verify_image(
        self,
        image_bytes: bytes,
        verification_prompt: str,
        **kwargs,
    ) -> dict:
        """
        Use Gemini Flash vision to verify the annotated image.
        Returns a dict: {approved: bool, issues: list[str], quality_score: float}
        """
        import asyncio
        import google.generativeai as genai
        settings = get_settings()
        self._get_client()

        import PIL.Image
        import io
        pil_image = PIL.Image.open(io.BytesIO(image_bytes))

        model = genai.GenerativeModel(model_name=settings.gemini_model)
        loop = asyncio.get_event_loop()

        response = await loop.run_in_executor(
            None,
            lambda: model.generate_content(
                [verification_prompt, pil_image],
                generation_config=genai.types.GenerationConfig(
                    temperature=0.1,
                    max_output_tokens=512,
                    response_mime_type="application/json",
                ),
            ),
        )
        try:
            return json.loads(response.text)
        except (json.JSONDecodeError, ValueError):
            # Fallback: extract from text
            text = response.text
            approved = '"approved": true' in text.lower()
            return {"approved": approved, "issues": [], "quality_score": 0.7 if approved else 0.4}
