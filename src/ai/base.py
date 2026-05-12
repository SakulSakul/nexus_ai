"""LLM 추상 base."""
from __future__ import annotations

from abc import ABC, abstractmethod


class LLMClient(ABC):
    @abstractmethod
    def classify(self, system_prompt: str, user_prompt: str) -> dict: ...

    @abstractmethod
    def synthesize(self, system_prompt: str, user_prompt: str) -> str: ...

    @abstractmethod
    def embed(self, text: str, task_type: str = "RETRIEVAL_QUERY") -> list[float]: ...
