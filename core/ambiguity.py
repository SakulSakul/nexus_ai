"""PR-Ambiguity-Askback: 모호한 bare 토큰 의도 명확화 역질문 (Live RAG 라우터).

내용 없는 단일 키워드("발주", "감사")는 *어느 규정도 소유하지 않는 교차
sub-topic* 이라 검색만으로는 의도를 못 가린다 (auto_keywords 노이즈 +
동의어 라우팅으로 엉뚱한 도메인 hijack). FAQ(정적 답변)와 달리, 합성 전에
short-circuit 하여 "어느 쪽?" 역질문을 반환하고, 사용자가 선택한 구체
sub-intent 로 재질의하면 *이미 정상 작동하는 맥락 경로* 로 흐른다.

큐레이션 맵은 도메인 전문가가 관리 (동의어 사전과 동일 성격 — LLM 이 사내
구분을 자율 도출 못 하고, 코퍼스에 compound 구조도 없음이 SQL 로 확인됨).
sub-intent query 는 정상 라우팅됨이 검증된 문구만 사용한다.
"""
from __future__ import annotations

import re

from .config import get_secret


# ── Feature flag (기본 OFF — 활성 시 Streamlit secret ENABLE_AMBIGUITY_ASKBACK=true) ──
ENABLE_AMBIGUITY_ASKBACK: bool = (
    get_secret("ENABLE_AMBIGUITY_ASKBACK", "false").lower() == "true"
)


# token → {"prompt": 역질문 본문, "choices": [{"label": 친화 라벨, "query": 재질의 문구}]}
# label = 사용자에게 보이는 버튼 텍스트, query = 클릭 시 재질의되는 구체 문구.
AMBIGUOUS_BARE_TOKENS: dict[str, dict] = {
    "발주": {
        "prompt": "'발주'는 맥락에 따라 적용 사규가 다릅니다. 어느 발주를 찾으시나요?",
        "choices": [
            {"label": "상품 발주 (입고·반출입)", "query": "상품 반출입 발주 등록 절차", "cat": "재무"},
            {"label": "구매 발주 품의·결재", "query": "구매 발주 품의 결재 절차", "cat": "총무"},
            {"label": "협력사 발주 (입점·거래)", "query": "협력사 발주 처리 절차", "cat": "공정거래"},
        ],
    },
    "감사": {
        "prompt": "'감사'는 종류에 따라 적용 사규가 다릅니다. 어느 감사를 찾으시나요?",
        "choices": [
            {"label": "내부회계 감사", "query": "내부회계관리제도 감사 절차", "cat": "재무"},
            {"label": "정보보호·보안 감사", "query": "정보보호 보안 감사 절차", "cat": "정보보안"},
            # AEO 내부심사 = (영업) AEO 내부통제활동평가규정. "내부심사" 문구가
            # corpus doc 명칭과 불일치해 synthesizer "확인 안됨" 처리되던 것 →
            # 실재 doc 주제어("내부통제활동 평가")로 query 정렬.
            {"label": "AEO 감사", "query": "AEO 내부통제활동 평가 절차", "cat": "영업"},
            # 감사위원회 선택지 제거: 독립 "감사위원회 운영규정" 사규가 corpus 에
            # 부재(내부회계관리제도상 보고대상으로만 언급). 막다른 버튼 = false-
            # negative 약속이므로 미제공. 직접 "감사위원회 운영" 질의 시 full RAG 가
            # 정직하게 "독립 규정 없음" 안내함.
        ],
    },
}


# 정규화: 공백·종결부호 제거 → bare 토큰 + 단순 조사/의문어만 매칭 (내용 토큰 0개).
_PUNCT_RE = re.compile(r"[?!.,;:'\"\s]+")

# 토큰 뒤에 붙어도 "내용 없음" 으로 간주하는 조사/의문어 (예: "발주는", "발주뭐야").
_TRAILING_FILLERS = (
    "은", "는", "이", "가", "을", "를", "의", "에", "에서", "이란", "란",
    "이라는", "라는", "란게", "이란게", "뭐", "뭐야", "이뭐야", "가뭐야",
    "은뭐", "는뭐",
)


def _normalize(q: str) -> str:
    return _PUNCT_RE.sub("", (q or "")).strip()


def detect_bare_ambiguity(question: str) -> dict | None:
    """질의가 *내용 없는* 모호 bare 토큰과 일치하면 역질문 정보 반환, 아니면 None.

    "발주" / "발주는" / "발주?" → 매칭.
    "상품 발주 절차" / "발주 방법" / "감사합니다" → None (내용 토큰 존재).

    Returns: {"token": str, "prompt": str, "choices": list[dict]} | None
    """
    norm = _normalize(question)
    if not norm:
        return None
    # 1) 정확 일치
    if norm in AMBIGUOUS_BARE_TOKENS:
        e = AMBIGUOUS_BARE_TOKENS[norm]
        return {"token": norm, "prompt": e["prompt"], "choices": list(e["choices"])}
    # 2) 토큰 + 단순 조사/의문어 (그 외 내용어가 붙으면 통과 — 정상 RAG)
    for tok, e in AMBIGUOUS_BARE_TOKENS.items():
        if norm.startswith(tok):
            tail = norm[len(tok):]
            if tail in _TRAILING_FILLERS:
                return {"token": tok, "prompt": e["prompt"], "choices": list(e["choices"])}
    return None


def _assert_no_loops() -> None:
    """무한 루프 방어 (Rule 1): 어떤 선택지 query 도 다시 bare 모호 토큰으로
    감지되면 안 된다 (클릭 → 재질의 → 또 역질문 → 무한 루프). import 시 1회 검증.
    """
    for _tok, _e in AMBIGUOUS_BARE_TOKENS.items():
        for _ch in _e["choices"]:
            assert detect_bare_ambiguity(_ch["query"]) is None, (
                f"선택지 query {_ch['query']!r} 가 역질문을 재트리거 → 무한 루프 위험"
            )


_assert_no_loops()
