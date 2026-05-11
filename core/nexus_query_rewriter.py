"""Tier 1 — Gemini 기반 쿼리 재작성 (사규 용어 확장) + 한국어 tsquery 빌더.

사용자 자연어 질문이 사규 본문의 한자어·법률 용어와 어휘적으로 불일치할 때
검색 recall 이 떨어지는 문제를 보정한다. 검색 직전에 호출되어 원문 의도를
유지한 채 동의어·상위 개념을 1~3개 덧붙인 키워드 나열형 문자열을 만든다.

설계 원칙:
- Gemini 호출은 core/chatbot.py:_gen_gemini 와 동일 패턴 (google-genai
  Client + types.GenerateContentConfig + res.candidates[0].content.parts).
- 가벼운 non-thinking 모델 (gemini-2.0-flash) · max_output_tokens 128.
  2.5-flash 는 thinking 토큰이 출력 예산을 잠식해 응답이 잘림 — 단순
  키워드 확장에는 thinking 불필요하므로 2.0-flash 로 고정.
- 실패는 절대 raise 하지 않는다. 호출자는 항상 결과 텍스트를 받는다.
- 동일 질문 반복(eval/디버그)에 대비해 lru_cache 적용.
"""

from __future__ import annotations

import functools
import re

from .config import get_secret, settings


_REWRITE_MODEL = get_secret("NEXUS_QUERY_REWRITE_MODEL", "gemini-2.0-flash")
_MAX_OUTPUT_TOKENS = 128
_REWRITE_TEMPERATURE = 0.2
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


# ── 메타 (admin 디버그 패널 표시용) ─────────────────────────
REWRITE_MODEL_INFO: dict = {
    "model": _REWRITE_MODEL,
    "max_output_tokens": _MAX_OUTPUT_TOKENS,
    "temperature": _REWRITE_TEMPERATURE,
}


def _call_gemini_for_rewrite(user_question: str) -> str:
    """core/chatbot.py:_gen_gemini 패턴을 그대로 따라간다.

    - google-genai Client + GenerateContentConfig
    - response 추출: res.candidates[0].content.parts 전체 text 이어붙임,
      fallback 으로 res.text. 어떤 경우에도 slicing 으로 1글자/1단어 자르지 않음.
    실패 시 빈 문자열 반환. (postprocess 가 원문 폴백 처리)
    """
    try:
        from google import genai
        from google.genai import types
    except Exception:
        return ""

    s = settings()
    if not s.gemini_api_key:
        return ""

    prompt = _PROMPT_TEMPLATE.format(user_question=user_question)

    try:
        cli = genai.Client(api_key=s.gemini_api_key)
        cfg = types.GenerateContentConfig(
            temperature=_REWRITE_TEMPERATURE,
            max_output_tokens=_MAX_OUTPUT_TOKENS,
        )
        res = cli.models.generate_content(
            model=_REWRITE_MODEL,
            contents=prompt,
            config=cfg,
        )
    except Exception:
        return ""

    # 응답 추출 — _gen_gemini 와 동일. 슬라이싱·split 으로 1글자/1단어 자르지 않는다.
    text_parts: list[str] = []
    try:
        for part in res.candidates[0].content.parts:
            if getattr(part, "thought", False):
                continue
            text_parts.append(getattr(part, "text", "") or "")
    except Exception:
        text_parts = [getattr(res, "text", "") or ""]

    text = "".join(text_parts).strip()
    if not text:
        text = (getattr(res, "text", "") or "").strip()
    return text


def _postprocess_rewritten(raw: str, fallback: str) -> str:
    """Gemini 원문 응답 -> 검색용 키워드 문자열로 정규화.
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
        if len(text) > _MAX_LEN:
            text = text[:_MAX_LEN]
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
    return_debug=True 면 (cleaned, raw_response) 튜플 반환 — admin 디버그
    패널 전용. 라이브 검색 경로(core/retriever.py)는 절대 본 인자를 넘기지 말 것.
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


# ── 한국어 prefix tsquery 빌더 ─────────────────────────────
# 배경: plainto_tsquery('simple', '고객이 매장에 처리하나요') 는 한국어 조사가
# 토큰에 붙은 채 들어가서 매칭률이 처참하다. 조사를 떼고 to_tsquery 용 prefix
# 형태 ("고객:* | 매장:* | 처리:*") 로 빌드하면 정확도 급상승.
_KOREAN_PARTICLES = (
    "으로부터", "에서부터", "에게서", "한테서", "이라고", "라고",
    "에서", "에게", "한테", "으로", "까지", "부터", "마다",
    "이라", "처럼", "보다", "조차", "마저",
    "이", "가", "을", "를", "은", "는", "도", "만",
    "와", "과", "의", "에", "로", "랑",
)


# 자연어 토큰 → 사규 용어. 점진적으로 추가 가능한 단순 dict.
# Gemini rewriter 가 흔들려도 작동하는 정적 안전망. compliance 도메인
# 어휘가 좁아 dict 만으로도 핵심 패턴 커버 가능.
_NEXUS_NL_TO_REGULATORY = {
    # 매장 습득물 / 유실물 도메인
    "두고": ("습득물", "유실물", "분실물", "인계", "보관"),
    "잊고": ("습득물", "유실물", "분실물"),
    "분실": ("습득물", "유실물"),
    "잃어": ("습득물", "유실물"),
    "잃어버": ("습득물", "유실물"),
    "놓고": ("습득물", "유실물"),
    # 금품 수수 / 윤리 도메인
    "선물": ("금품", "이해관계자", "클린뱅크"),
    "명절": ("금품", "이해관계자"),
    "거래처": ("이해관계자", "협력업체"),
    "접대": ("금품", "이해관계자"),
    "촌지": ("금품", "이해관계자"),
    # 정보보안 도메인
    "외부": ("반출", "송신", "정보보안"),
    "메일": ("송신", "외부반출"),
    "유출": ("정보유출", "정보보안"),
    "반출": ("정보보안", "외부반출"),
    # 안전 도메인
    "사고": ("안전사고", "재해"),
    "다친": ("산업재해", "안전"),
    "부상": ("산업재해", "안전"),
}


def _nexus_expand_with_synonyms(tokens: list) -> list:
    """자연어 토큰에 대응하는 사규 용어를 OR 후보에 추가."""
    expanded = list(tokens)
    seen = set(tokens)
    for tok in tokens:
        for key, synonyms in _NEXUS_NL_TO_REGULATORY.items():
            if key in tok:  # 부분 매칭으로 조사 잔재까지 잡음
                for syn in synonyms:
                    if syn not in seen:
                        expanded.append(syn)
                        seen.add(syn)
    return expanded


def nexus_build_keyword_tsquery(text: str) -> str:
    """자연어/재작성 쿼리를 prefix tsquery 문자열로 변환.

    예: '고객이 매장에 처리하나요' -> '고객:* | 매장:* | 처리:*'
    """
    if not text:
        return ""
    tokens = re.findall(r"[가-힣A-Za-z0-9]+", text)
    cleaned: list[str] = []
    for tok in tokens:
        for p in _KOREAN_PARTICLES:
            if tok.endswith(p) and len(tok) > len(p) + 1:
                tok = tok[: -len(p)]
                break
        if len(tok) >= 2:
            cleaned.append(tok)
    seen: set[str] = set()
    uniq: list[str] = []
    for t in cleaned:
        if t not in seen:
            seen.add(t)
            uniq.append(t)
    uniq = _nexus_expand_with_synonyms(uniq)
    return " | ".join(f"{t}:*" for t in uniq)
