"""Auto-classifier — Gemini Flash 기반 query → incident_nodes."""

from __future__ import annotations

import json
import sys

from .cache import classification_cache_get, classification_cache_set


AVAILABLE_INCIDENT_NODES: list = [
    "사건사고보고", "인사사고", "고객상해", "성희롱", "괴롭힘",
    "정보유출", "근로자안전", "직원상해", "매장사고", "응급대응",
    "윤리보고", "횡령", "배임", "금전사고", "절도", "비위행위",
    "윤리위반", "안전관리", "시설안전",
]


CLASSIFIER_SYSTEM_PROMPT = """\
사규 질문 분류기. 다음 incident_nodes 중 적합한 것들로 분류.
사용 가능: {nodes}

규칙:
1. 직접 관련된 nodes 만 (오버 매핑 금지)
2. 보통 2~6개
3. strict JSON: {{"incident_nodes": ["...", "..."]}}
"""


def auto_classify(query: str, *, use_cache: bool = True) -> tuple:
    """query → (nodes, source) — source: 'cache' | 'llm' | 'fallback' | 'error'."""
    if use_cache:
        cached = classification_cache_get(query)
        if cached is not None:
            return cached, "cache"

    try:
        from google import genai
        from google.genai import types
        from core.config import settings
    except Exception as e:
        print(f"[auto_classifier] SDK import 실패: {e}", file=sys.stderr, flush=True)
        return _rule_based_fallback(query)

    s = settings()
    if not s.gemini_api_key:
        return _rule_based_fallback(query)

    prompt = CLASSIFIER_SYSTEM_PROMPT.format(nodes=", ".join(AVAILABLE_INCIDENT_NODES))
    try:
        cli = genai.Client(api_key=s.gemini_api_key)
        cfg = types.GenerateContentConfig(
            system_instruction=prompt,
            response_mime_type="application/json",
            temperature=0.0,
            max_output_tokens=256,
        )
        res = cli.models.generate_content(
            model="gemini-2.5-flash-lite",
            contents=f"질문: {query}\n\nstrict JSON 출력.",
            config=cfg,
        )
        raw_text = getattr(res, "text", "") or ""
        raw = json.loads(raw_text)
        nodes = [n for n in raw.get("incident_nodes", []) if n in AVAILABLE_INCIDENT_NODES]
        if use_cache and nodes:
            classification_cache_set(query, nodes, "gemini-2.5-flash-lite")
        return nodes, "llm"
    except Exception as e:
        print(
            f"[auto_classifier] LLM 실패, fallback: {type(e).__name__}: {e}",
            file=sys.stderr, flush=True,
        )
        return _rule_based_fallback(query)


def _rule_based_fallback(query: str) -> tuple:
    try:
        from core.nexus_query_rewriter import nexus_classify_to_incident_nodes
        return sorted(set(nexus_classify_to_incident_nodes(query) or [])), "fallback"
    except Exception:
        return [], "error"
