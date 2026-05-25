"""PR-Phase-11: Citation Verification Layer

답변 본문의 사규 인용 (📎) 과 실제 컨텍스트 chunks 의 doc_title 매칭 검증.
100% 무결성 아키텍처 비전의 Phase 1 — Verification Layer.
"""
from __future__ import annotations
import re
import sys

# 실제 답변 인용 형식 (prompts.py): 「📎 **((분류) 사규명)**」 또는
# 「📎 **((분류) 사규명 제N조)**」. doc_title 이 (분류) prefix 의 괄호를
# 포함하므로 outer paren 안의 「(분류) ...」 구조를 직접 캡처한다.
# 볼드(**)는 spec 상 필수이나 누락 대비 optional 로 둔다.
_CITATION_RE = re.compile(
    r"📎\s*\*{0,2}\s*\(\s*(\([^)]+\)[^)]*?)\s*\)\s*\*{0,2}"
)


def extract_citations_from_answer(answer_text: str) -> list[str]:
    """답변 본문의 「📎 ((xxx) doc_title)」 인용 doc_title 추출."""
    if not answer_text:
        return []
    return [m.group(1).strip() for m in _CITATION_RE.finditer(answer_text)]


def verify_citations(
    answer_text: str, contexts: list[dict]
) -> tuple[list[str], list[str], list[str]]:
    """답변 본문 인용 ↔ 컨텍스트 chunks 의 doc_title 1:1 매칭 검증.

    Returns:
        (matched, unmatched, context_unused) —
        matched: 답변에 인용 + 컨텍스트에 존재
        unmatched: 답변에 인용 but 컨텍스트에 부재 (잠재 hallucination)
        context_unused: 컨텍스트에 존재 but 답변 미인용
    """
    cited_titles = set(extract_citations_from_answer(answer_text))
    context_titles = {
        str(c.get("doc_title") or "").strip()
        for c in contexts if c.get("doc_title")
    }

    matched = sorted(cited_titles & context_titles)
    unmatched_raw = sorted(cited_titles - context_titles)
    context_unused = sorted(context_titles - cited_titles)

    # 정규화 — 「(인사)」 와 「(인사) 」 등 사소한 차이 해소
    if unmatched_raw:
        ctx_normalized = {t.replace(" ", "").lower() for t in context_titles}
        unmatched = [
            t for t in unmatched_raw
            if t.replace(" ", "").lower() not in ctx_normalized
        ]
    else:
        unmatched = []

    return matched, unmatched, context_unused


def log_verification_result(
    answer_text: str, contexts: list[dict],
) -> dict:
    """답변 인용 검증 + 로깅 + 결과 dict 반환.

    UI 표시 또는 답변 metadata 에 활용. Phase 12 의 Closed-loop generation
    base 데이터.
    """
    matched, unmatched, context_unused = verify_citations(
        answer_text, contexts
    )
    result = {
        "citations_matched": matched,
        "citations_unmatched": unmatched,  # 잠재 hallucination
        "context_unused": context_unused,  # 정보 누락
        "match_rate": (
            len(matched) / (len(matched) + len(unmatched))
            if (matched or unmatched) else 1.0
        ),
        "has_hallucination": len(unmatched) > 0,
    }
    print(
        f"[citation_verifier] match_rate={result['match_rate']:.2%} "
        f"matched={len(matched)} unmatched={len(unmatched)} "
        f"context_unused={len(context_unused)}",
        file=sys.stderr, flush=True,
    )
    if unmatched:
        print(
            f"[citation_verifier] ⚠️ HALLUCINATION CANDIDATES: {unmatched}",
            file=sys.stderr, flush=True,
        )
    return result
