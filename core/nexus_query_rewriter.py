"""Tier 1 — Gemini 기반 쿼리 재작성 (사규 용어 확장).

사용자 자연어 질문이 사규 본문의 한자어·법률 용어와 어휘적으로 불일치할 때
검색 recall 이 떨어지는 문제를 보정한다. 검색 직전에 호출되어 원문 의도를
유지한 채 동의어·상위 개념을 1~3개 덧붙인 키워드 나열형 문자열을 만든다.

설계 원칙:
- 기존 Gemini 클라이언트(core.embedder._client) 재사용. 신규 client 금지.
- 가벼운 모델(gemini-2.5-flash 권장)·max_output_tokens 64 — 검색 추가 지연 최소화.
- 실패는 절대 raise 하지 않는다. 호출자(retriever)는 항상 결과 텍스트를 받는다.
- 동일 질문 반복(예: 디버그 패널, eval 회차)에 대비해 lru_cache 적용.
"""

from __future__ import annotations

import functools

from .config import get_secret


_REWRITE_MODEL = get_secret("NEXUS_QUERY_REWRITE_MODEL", "gemini-2.5-flash")
_MAX_OUTPUT_TOKENS = 64
_MAX_LEN = 60


_PROMPT_TEMPLATE = """당신은 사규 검색을 돕는 쿼리 재작성 보조입니다.
사용자의 자연어 질문을 사규 문서에서 사용될 법한 정식 용어·동의어로 확장하세요.

원칙:
- 원문 의도 유지
- 사규에서 쓰이는 한자어·법률 용어 우선 포함
- 동의어·상위 개념 1~3개 추가
- 출력은 검색용 키워드 나열형 단일 문장, 60자 이내
- 답변·설명·문장부호 없이 키워드만

예시:
질문: 고객이 매장에 두고 간 물건은 어떻게 처리하나요?
답: 고객 습득물 유실물 분실물 매장 처리 보관 인계 절차

질문: 거래처가 명절에 선물을 보내왔는데 어떻게 하나요?
답: 이해관계자 금품 수수 명절 선물 클린뱅크 윤리 신고

질문: 사내 자료를 외부 메일로 보낼 때 주의할 점이 있나요?
답: 회사 정보 자료 외부 반출 메일 송신 정보보안 통제 절차

질문: {user_question}
답:"""


def _call_gemini_for_rewrite(user_question: str) -> str:
    """Gemini 호출 — raw 응답 텍스트 반환. 실패 시 빈 문자열."""
    try:
        # 신규 클라이언트 금지 — 기존 embedder 의 _client 재사용.
        from .embedder import _client
        cli = _client()
        prompt = _PROMPT_TEMPLATE.format(user_question=user_question)
        res = cli.models.generate_content(
            model=_REWRITE_MODEL,
            contents=prompt,
            config={
                "max_output_tokens": _MAX_OUTPUT_TOKENS,
                "temperature": 0.0,
            },
        )
        text = getattr(res, "text", None)
        if not text:
            cands = getattr(res, "candidates", None) or []
            if cands:
                parts = getattr(getattr(cands[0], "content", None), "parts", None) or []
                text = "".join(getattr(p, "text", "") or "" for p in parts)
        return text or ""
    except Exception:
        return ""


def _postprocess_rewritten(raw: str, fallback: str) -> str:
    """
    Gemini 원문 응답 -> 검색용 키워드 문자열로 정규화.
    실패 시 원문 user_question(fallback) 반환.
    """
    if not raw:
        return fallback
    try:
        text = raw.strip()
        # 접두 라벨 제거 (모델이 가끔 붙임)
        for prefix in ("답:", "답 :", "답변:", "Answer:", "A:"):
            if text.startswith(prefix):
                text = text[len(prefix):].strip()
                break
        # 첫 줄만 사용 (모델이 가끔 여러 줄을 출력)
        text = text.splitlines()[0] if text else ""
        # 양쪽 따옴표 제거
        text = text.strip().strip('"').strip("'").strip("「").strip("」").strip()
        # 글자 단위 60자 컷 (바이트 아님)
        if len(text) > 60:
            text = text[:60]
        # 빈 문자열이면 원문 폴백
        if not text or len(text) < 2:
            return fallback
        return text
    except Exception:
        return fallback


@functools.lru_cache(maxsize=512)
def rewrite_query_for_retrieval(user_question: str, return_debug: bool = False):
    """사규 검색용 키워드 확장 문자열 반환.

    실패 시 원문 user_question 을 그대로 반환 (절대 raise 하지 않음).
    동일 질문은 캐시 적중. retriever 가 매 검색 호출 직전에 사용.

    return_debug=True 면 (cleaned, raw_response) 튜플 반환 — admin 디버그 패널
    전용. 라이브 검색 경로(core/retriever.py)는 절대 본 인자를 넘기지 말 것.
    """
    if not user_question or not user_question.strip():
        result = user_question or ""
        return (result, "") if return_debug else result
    try:
        raw = _call_gemini_for_rewrite(user_question)
    except Exception:
        raw = ""
    cleaned = _postprocess_rewritten(raw, fallback=user_question)
    return (cleaned, raw) if return_debug else cleaned
