"""PR-Phase-19.2.1 stub — 동의어 사전 기반 query 확장 (Flag 만 정의).

본격 retrieval 통합은 PR 19.2.2 에서 진행:
- nexus_synonym_dictionary (approved=true, rejected=false) lookup
- 사용자 query 의 명사 → primary_term 매핑 + append
- 18.6 _NEXUS_NL_TO_REGULATORY 하드코딩 dict 와 공존 (안전망 fallback)
- vector + keyword 측 모두 적용 (18.6 진단의 vector gap 해소)

본 모듈 (19.2.1) 의 역할:
- ENABLE_SYNONYM_EXPANSION flag 정의 (기본 OFF → 회귀 0)
- expand_query_with_synonyms() stub — flag OFF 시 input 그대로 반환
"""
from __future__ import annotations

from typing import Any

from .config import get_secret


# ── Feature flag (기본 OFF, 19.2.2 에서 활성화 가능) ─────────────
ENABLE_SYNONYM_EXPANSION: bool = (
    str(get_secret("ENABLE_SYNONYM_EXPANSION", "false")).lower() == "true"
)


def expand_query_with_synonyms(
    question: str, supabase: Any | None = None,
) -> tuple[str, list[tuple[str, str]]]:
    """사규 동의어 사전 기반 query 확장.

    Returns:
      expanded_query: 확장된 query (변환 X 시 원문 그대로)
      substitutions: [(original_token, primary_term)] — UI 안내용

    Stub (19.2.1): flag 체크 후 반환만. retrieval 실 적용은 19.2.2.
    """
    if not ENABLE_SYNONYM_EXPANSION:
        return question, []
    # 19.2.2 에서 구현:
    # 1) re.findall 로 토큰 추출
    # 2) supabase.table("nexus_synonym_dictionary")
    #      .select("primary_term,synonym_term")
    #      .eq("approved", True).eq("rejected", False)
    #      .in_("synonym_term", tokens).execute()
    # 3) substitutions 기록 + primary_term 들을 query 에 append
    # 4) hybrid_search L959 의 retrieval_query_text 에 주입
    return question, []
