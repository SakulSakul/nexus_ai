"""PR-Phase-19.2.2 — 사규 동의어 사전 기반 query 확장 (retrieval 통합).

19.2.1 의 stub 을 본 구현으로 교체. ENABLE_SYNONYM_EXPANSION=true 시:
- nexus_synonym_dictionary (approved=true AND rejected=false) lookup
- 사용자 query 의 명사·약어 토큰 → primary_term append (원문 보존)
- 18.6 _NEXUS_NL_TO_REGULATORY 하드코딩 dict 와 공존 (안전망 fallback)
- vector(embed_one) + keyword(tsquery/pgroonga) 측 모두 적용

핵심 안전:
- flag OFF (기본) 시 input 그대로 반환 → 회귀 0
- approved=false / rejected=true 항목은 절대 사용하지 않음
- DB 조회 실패 시 silent fallback (원문 반환)
"""
from __future__ import annotations

import re
from typing import Any

from .config import get_secret


# ── Feature flag (기본 OFF) ──────────────────────────────────
ENABLE_SYNONYM_EXPANSION: bool = (
    str(get_secret("ENABLE_SYNONYM_EXPANSION", "false")).lower() == "true"
)


def expand_query_with_synonyms(
    question: str, supabase: Any | None = None,
) -> tuple[str, list[tuple[str, str]]]:
    """사규 동의어 사전 기반 query 확장.

    Returns:
      expanded_query: 확장된 query (원문 보존 + primary_term append, miss 시 원문)
      substitutions: [(synonym_term, primary_term)] — UI 안내용 (중복 제거)

    Args:
      question: 사용자 질문(or rewriter 통과 후 text)
      supabase: anon Client (서비스 응답 경로). None 이면 fallback.
    """
    if not ENABLE_SYNONYM_EXPANSION:
        return question, []
    if not supabase or not question:
        return question, []

    # 한글 / 영문 / 숫자 토큰 (2자 이상) — 사규 약어 / 한글 단어 캡처
    tokens = re.findall(r"[가-힣A-Za-z0-9]{2,}", question)
    if not tokens:
        return question, []
    # 중복 제거 (in_ 쿼리 파라미터 절약)
    uniq_tokens = list(dict.fromkeys(tokens))

    try:
        result = (
            supabase.table("nexus_synonym_dictionary")
            .select("primary_term,synonym_term")
            .eq("approved", True)
            .eq("rejected", False)
            .in_("synonym_term", uniq_tokens)
            .execute()
        )
        rows = result.data or []
    except Exception:
        # silent — retrieval 본 흐름 보호 (회귀 안전)
        return question, []

    if not rows:
        return question, []

    # 중복 제거 (같은 synonym_term 이 여러 row 인 경우 첫 매핑만)
    substitutions: list[tuple[str, str]] = []
    seen_syn: set[str] = set()
    for row in rows:
        syn = (row.get("synonym_term") or "").strip()
        pri = (row.get("primary_term") or "").strip()
        if not syn or not pri or syn in seen_syn:
            continue
        seen_syn.add(syn)
        substitutions.append((syn, pri))

    if not substitutions:
        return question, []

    # 원문 보존 + primary_term 들을 append (BM25 + vector 양측 반영)
    appended = " ".join(p for _, p in substitutions)
    expanded = f"{question} {appended}"
    return expanded, substitutions
