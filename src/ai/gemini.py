"""Gemini API client — classifier + synthesizer + embedder."""
from __future__ import annotations

import json
import re

from google import genai
from google.genai import types

from src.ai.base import LLMClient
from src.ai.cache import LRUCache
from src.config.settings import Settings


_CLASSIFY_CONFIG = {
    "temperature": 0.0,
    "max_output_tokens": 2048,
    "response_mime_type": "application/json",
}

# Gemini 2.5 Pro: thinking tokens 가 max_output_tokens 에 포함됨.
# 1200 으로는 thinking 만으로 다 소진 → response.text 빈 값 → RuntimeError.
# 8192 = thinking 충분 + 답변 본문 (~1500 tokens) 여유.
_SYNTHESIS_CONFIG = {
    "temperature": 0.0,
    "top_p": 0.95,
    "max_output_tokens": 8192,
}

_EMBED_TASK_TYPES = {
    "RETRIEVAL_QUERY",
    "RETRIEVAL_DOCUMENT",
    "SEMANTIC_SIMILARITY",
    "CLASSIFICATION",
}


class GeminiClient(LLMClient):
    def __init__(self, settings: Settings, cache: LRUCache | None = None):
        self._settings = settings
        self._client = genai.Client(api_key=settings.gemini_api_key)
        self._cache = cache or LRUCache(capacity=256)

    def classify(self, system_prompt: str, user_prompt: str) -> dict:
        cached = self._cache.get("classify", system_prompt, user_prompt)
        if cached is not None:
            try:
                return json.loads(cached)
            except json.JSONDecodeError:
                pass

        try:
            response = self._client.models.generate_content(
                model=self._settings.gemini_classify_model,
                contents=user_prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    **_CLASSIFY_CONFIG,
                ),
            )
            text = response.text or ""
            text = self._strip_json_fences(text)
            parsed = json.loads(text)
            self._cache.set(text, "classify", system_prompt, user_prompt)
            return parsed if isinstance(parsed, dict) else {}
        except (json.JSONDecodeError, Exception):
            return {}

    def synthesize(self, system_prompt: str, user_prompt: str) -> str:
        response = self._client.models.generate_content(
            model=self._settings.gemini_synth_model,
            contents=user_prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                **_SYNTHESIS_CONFIG,
            ),
        )
        text = (response.text or "").strip()
        if not text:
            # finish_reason 노출 — 디버그용 (MAX_TOKENS / SAFETY / etc.)
            finish_reason = "unknown"
            try:
                if response.candidates:
                    finish_reason = str(response.candidates[0].finish_reason)
            except Exception:
                pass
            raise RuntimeError(
                f"Gemini returned empty response (finish_reason={finish_reason})"
            )
        return text

    def embed(self, text: str, task_type: str = "RETRIEVAL_QUERY") -> list[float]:
        if task_type not in _EMBED_TASK_TYPES:
            task_type = "RETRIEVAL_QUERY"
        response = self._client.models.embed_content(
            model=self._settings.gemini_embed_model,
            contents=text,
            config=types.EmbedContentConfig(
                task_type=task_type,
                output_dimensionality=768,
            ),
        )
        if not response.embeddings:
            raise RuntimeError("Gemini returned no embedding")
        return list(response.embeddings[0].values)

    @staticmethod
    def _strip_json_fences(text: str) -> str:
        text = text.strip()
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
        return text.strip()
