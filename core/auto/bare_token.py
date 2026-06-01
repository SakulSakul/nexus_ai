"""결정론적 bare 도메인 토큰 분해.

Opus 키워드 추출은 합성어 안의 2글자 도메인 토큰(발주/계약/구매 등)을 bare 로
분리하는 데 신뢰성이 없음(실측: 재태깅 후 bare "계약" 0건). → 추출된 키워드
리스트에서 큐레이션 토큰이 *기존 합성어 안에* substring 으로 있으나 bare 로
없으면 결정론적으로 bare 토큰 추가. force-include(doc 2 + chunk 3 = 5) 2글자
질의 매칭 보장. 원칙: LLM 이 이미 합성어로 키워드화한 토큰만 분해 → 노이즈 최소.
"""
from __future__ import annotations

DETERMINISTIC_BARE_TOKENS: tuple[str, ...] = (
    "발주", "택시", "식대", "출장", "구매", "감사", "반품", "폐기",
    "계약", "입찰", "견적", "정산", "경비", "징계", "횡령", "접대",
    "납품", "검수", "하자", "환불", "멸각",
)

# 글자 경계를 가로지르는 substring 오탐 가드:
# 토큰 → 이 substring 을 포함한 합성어는 해당 토큰의 근거로 불인정
_FP_GUARDS: dict[str, tuple[str, ...]] = {
    "감사": ("인감사용", "인감 사용"),  # 인감(seal)+사용 ≠ audit
    "경비": ("무인경비", "경비시스템", "경비실", "경비원", "경비업"),  # 보안 ≠ 비용
}


def inject_bare_domain_tokens(keywords: list[str]) -> list[str]:
    """keywords 에 결정론적 bare 토큰 추가 (additive·idempotent·순서보존).

    원본 키워드는 절대 제거하지 않음.
    """
    if not keywords:
        return keywords
    out = list(keywords)
    present = {k for k in keywords if isinstance(k, str)}
    for tok in DETERMINISTIC_BARE_TOKENS:
        if tok in present:
            continue
        guards = _FP_GUARDS.get(tok, ())
        for kw in keywords:
            if not isinstance(kw, str) or kw == tok or tok not in kw:
                continue
            if any(g in kw for g in guards):
                continue
            out.append(tok)
            present.add(tok)
            break
    return out
