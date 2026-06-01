"""다중 맥락(multi-facet) 질의 감지 — 결정론적 게이트.

"발주"/"협력사 발주" 같은 짧고 다의적 질의가 단일 도메인으로 강제되어 곁가지
(키워드-밀집) 문서가 핵심 문서를 누르고 합성기가 거짓 '없음' 헤지를 내는 클래스.
카테고리는 답변 인용을 충실히 따르므로(category_visual -1 규칙) 근본은 '단일
도메인 강제'. 해법: rerank 후 contexts 의 카테고리 분산을 측정해 다중 도메인에
고르게 걸치면 multi-facet 판정 + 도메인별 대표 사규 추출 → 합성 분기 신호.
LLM 자기-판단 미의존.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

_CAT_PREFIX_RE = re.compile(r"^\(([^)]+)\)")
_CROSS_CUTTING = {"공통"}


@dataclass
class Facet:
    category: str
    doc_title: str
    score: float


@dataclass
class MultiFacetResult:
    is_multi_facet: bool
    facets: list = field(default_factory=list)
    dominant_category: str | None = None
    distinct_domains: int = 0


def _category_of(doc_title: str | None) -> str | None:
    if not doc_title:
        return None
    m = _CAT_PREFIX_RE.match(doc_title.strip())
    return m.group(1).strip() if m else None


def detect_multi_facet(
    contexts: list,
    *,
    top_k: int = 8,
    min_domains: int = 2,
    dominance_ratio: float = 0.6,
) -> MultiFacetResult:
    """score-내림차순 contexts 에서 다중 맥락 판정.

    상위 top_k 의 비-공통 도메인이 min_domains 종 이상 + 최상위 도메인 점수
    점유율이 dominance_ratio 미만(지배자 없음)이면 multi-facet.
    """
    if not contexts:
        return MultiFacetResult(is_multi_facet=False)
    top = contexts[:top_k]
    by_cat_score: dict = {}
    by_cat_top: dict = {}
    for c in top:
        cat = _category_of(c.get("doc_title") or c.get("title"))
        if not cat or cat in _CROSS_CUTTING:
            continue
        sc = float(c.get("score") or 0.0)
        by_cat_score[cat] = by_cat_score.get(cat, 0.0) + sc
        title = c.get("doc_title") or c.get("title") or ""
        if cat not in by_cat_top or sc > by_cat_top[cat].score:
            by_cat_top[cat] = Facet(category=cat, doc_title=title, score=sc)
    distinct = len(by_cat_score)
    if distinct == 0:
        return MultiFacetResult(is_multi_facet=False, distinct_domains=0)
    total = sum(by_cat_score.values()) or 1.0
    ranked = sorted(by_cat_score.items(), key=lambda kv: -kv[1])
    dominant_cat, dominant_score = ranked[0]
    share = dominant_score / total
    is_mf = distinct >= min_domains and share < dominance_ratio
    return MultiFacetResult(
        is_multi_facet=is_mf,
        facets=[by_cat_top[cat] for cat, _ in ranked],
        dominant_category=dominant_cat if share >= dominance_ratio else None,
        distinct_domains=distinct,
    )
