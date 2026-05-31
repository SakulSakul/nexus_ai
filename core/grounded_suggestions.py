"""PR-UI1: 후속질문 카드 출처를 LLM 생성 → 검색 문서 grounded 전환.

기존 ans.suggestions 는 LLM 이 답변 끝 [SUGGESTIONS] 마커로 출력 (ungrounded —
클릭 시 답변 보장 없음). 본 모듈은 검색된 최상위 기여 문서의 auto_query_examples
(문서 내용으로 사전 생성된 예시질문) 를 후속질문으로 사용한다. grounded by
construction → 클릭하면 그 문서가 반드시 재검색되어 답변 가능. OOS 게이트가 추가 백업.

ENABLE_GROUNDED_SUGGESTIONS 플래그로 게이트 (기본 OFF — dark 배포). Streamlit
secrets 에 ENABLE_GROUNDED_SUGGESTIONS="true" 설정 시 활성.
"""
from __future__ import annotations

import os
from typing import Any

ENABLE_GROUNDED_SUGGESTIONS: bool = os.getenv(
    "ENABLE_GROUNDED_SUGGESTIONS", "false"
).strip().lower() in ("1", "true", "yes", "on")

_MAX_SUGGESTIONS = 3


def _norm(text: str) -> str:
    """공백 제거 + 소문자 — 중복 판정용."""
    return "".join(ch for ch in (text or "").lower() if not ch.isspace())


def grounded_suggestions(
    supabase: Any, contexts: list[dict], question: str
) -> list[str]:
    """최상위 기여 문서의 auto_query_examples 에서 후속질문 최대 3개.

    - contexts 는 RRF score 순. document_id 가 있는 첫 청크의 문서를 사용.
    - 사용자 질문과 사실상 동일한 예시는 제외 (중복 회피).
    - 실패/빈 결과는 [] 반환 → 호출 측이 기존 LLM suggestions 유지 (회귀 안전).
    """
    if not contexts:
        return []
    doc_id = None
    for c in contexts:
        did = c.get("document_id")
        if did is not None:
            doc_id = did
            break
    if doc_id is None:
        return []
    try:
        res = (
            supabase.table("nexus_documents")
            .select("auto_query_examples")
            .eq("id", doc_id)
            .limit(1)
            .execute()
        )
    except Exception:
        return []
    rows = getattr(res, "data", None) or []
    if not rows:
        return []
    examples = rows[0].get("auto_query_examples") or []
    if not isinstance(examples, list):
        return []
    q_norm = _norm(question)
    out: list[str] = []
    for ex in examples:
        if not isinstance(ex, str) or not ex.strip():
            continue
        ex_norm = _norm(ex)
        if not ex_norm:
            continue
        if ex_norm == q_norm or (q_norm and q_norm in ex_norm):
            continue
        out.append(ex.strip())
        if len(out) >= _MAX_SUGGESTIONS:
            break
    return out
