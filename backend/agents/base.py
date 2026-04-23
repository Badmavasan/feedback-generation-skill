"""Abstract base agent — all agents implement this interface."""
from abc import ABC, abstractmethod
from typing import Any


class BaseAgent(ABC):
    """
    Minimal contract every agent must satisfy.
    Agents are stateless — one call per request.
    """

    @abstractmethod
    async def generate(self, system_prompt: str, user_prompt: str, **kwargs) -> str:
        """
        Send a text generation request.
        Returns the raw text response.
        """
        ...

    # Optional — only image agents need to implement this
    async def annotate_image(
        self,
        image_bytes: bytes,
        annotation_prompt: str,
        **kwargs,
    ) -> bytes:
        raise NotImplementedError(f"{self.__class__.__name__} does not support image annotation")

    async def verify_image(
        self,
        image_bytes: bytes,
        verification_prompt: str,
        **kwargs,
    ) -> dict:
        raise NotImplementedError(f"{self.__class__.__name__} does not support image verification")
