"""Mistral text feedback generation agent."""
from agents.base import BaseAgent
from core.config import get_settings
from core.agent_logger import log_prompt


class MistralFeedbackAgent(BaseAgent):
    """
    Calls the Mistral API to generate a single feedback component.
    Mistral Large is preferred for French-language quality.
    """

    def __init__(self) -> None:
        self._client = None  # lazy-init

    def _get_client(self):
        if self._client is None:
            from mistralai.client import Mistral
            settings = get_settings()
            self._client = Mistral(api_key=settings.mistral_api_key)
        return self._client

    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 512,
        run_id: str | None = None,
        agent_label: str = "mistral",
        **kwargs,
    ) -> str:
        log_prompt(run_id, agent_label, user=user_prompt, system=system_prompt)
        client = self._get_client()
        settings = get_settings()
        response = await client.chat.complete_async(
            model=settings.mistral_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content.strip()
