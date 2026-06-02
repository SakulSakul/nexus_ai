"""Structured JSON synthesis — Gemini Pro with response_schema constraint."""

from __future__ import annotations

import json
import sys
import time

from .structured_schema import StructuredAnswer, GEMINI_RESPONSE_SCHEMA
from .constitutional_prompt import CONSTITUTIONAL_SYSTEM_PROMPT, build_user_prompt


def ask_structured(query: str, chunks: list) -> tuple:
    """Gemini Pro structured JSON synthesis.

    Returns (StructuredAnswer, elapsed_ms).
    """
    t0 = time.time()
    try:
        from google import genai
        from google.genai import types
        from core.config import settings
    except Exception as e:
        return StructuredAnswer(
            unsupported_topics=[f"SDK import 실패: {e}"],
            raw_json={"error": str(e)},
        ), int((time.time() - t0) * 1000)

    s = settings()
    api_key = s.gemini_api_key
    if not api_key:
        return StructuredAnswer(
            unsupported_topics=["GEMINI_API_KEY 미설정"],
            raw_json={"error": "no api key"},
        ), int((time.time() - t0) * 1000)

    user_text = build_user_prompt(query, chunks)
    try:
        cli = genai.Client(api_key=api_key)
        cfg = types.GenerateContentConfig(
            system_instruction=CONSTITUTIONAL_SYSTEM_PROMPT,
            response_mime_type="application/json",
            response_schema=GEMINI_RESPONSE_SCHEMA,
            temperature=0.0,
            max_output_tokens=8192,
        )
        res = cli.models.generate_content(
            model="gemini-3.5-flash",
            contents=user_text,
            config=cfg,
        )
        raw_text = getattr(res, "text", None) or ""
        if not raw_text:
            cands = getattr(res, "candidates", None) or []
            if cands:
                parts = getattr(getattr(cands[0], "content", None), "parts", None) or []
                raw_text = "".join(getattr(p, "text", "") or "" for p in parts)
        raw_json = json.loads(raw_text)
    except Exception as e:
        print(
            f"[structured_synth] failed: {type(e).__name__}: {e}",
            file=sys.stderr, flush=True,
        )
        return StructuredAnswer(
            unsupported_topics=[f"Gemini 오류: {type(e).__name__}: {e}"],
            raw_json={"error": str(e)},
        ), int((time.time() - t0) * 1000)

    elapsed = int((time.time() - t0) * 1000)
    try:
        return StructuredAnswer.from_json(raw_json), elapsed
    except Exception as e:
        return StructuredAnswer(
            unsupported_topics=[f"JSON 파싱 오류: {e}"],
            raw_json=raw_json,
        ), elapsed
