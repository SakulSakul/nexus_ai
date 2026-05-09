"""DF COMPASS · 멀티 시그널 confidence 분류 (PR-Q1.4 / PR-C1 후속).

PR-C1 v1 의 RRF best_score 단일 threshold (NEXUS_CONFIDENCE_HIGH/
MEDIUM) 는 PR-Q1.3 진단으로 무용지물 확인 — kw search 가 사실상
죽어 있어 (pg_bigm 미설치 + tsvector 'simple' 한국어 미지원) 모든
query 의 best_score 가 1/61 ≈ 0.0164 로 고정된다. vec only 동작 중.

본 모듈은 best_score 의존을 끊고 다음 4개 시그널을 조합:
  1. hit_count        : len(contexts)
  2. doc_kind_diversity: distinct doc_kind 수 (rule/penalty/case)
  3. category_match   : top hit 의 doc_title prefix "(분류)" 가
                        infer_categories(question) 와 일치하는지
  4. rrf_signal       : best_score 단계 (현재 의미 약함, kw search
                        부활 시 재활성)

분류:
  - high  : doc_kind_diversity >= 2  AND  category_match  AND  hit >= 3
  - medium: doc_kind_diversity >= 1  AND  hit >= 2
  - low   : 그 외 (hit 0 / 카테고리 무매칭 / single doc_kind 등)

NEXUS_CONFIDENCE_HIGH / NEXUS_CONFIDENCE_MEDIUM 은 deprecated. 코드는
유지 (config.py) 하되 본 분류기는 사용 안 함. kw search 부활 후
rrf_signal 가중치 재활성 시 재사용 여지.
"""

from __future__ import annotations

import re
from typing import Iterable


# "(분류) ..." 형식의 doc_title prefix 추출 — chatbot 의 카테고리 라벨
# 컨벤션과 일치. multi-byte 한국어 분류명을 위해 \w 대신 [^)\s] 사용.
_TITLE_CAT_PREFIX = re.compile(r"^\(\s*([^)\s][^)]*?)\s*\)")


def _title_category(doc_title: str) -> str | None:
    """doc_title 의 "(분류)" prefix 를 추출. 없으면 None."""
    if not doc_title:
        return None
    m = _TITLE_CAT_PREFIX.match(doc_title)
    return m.group(1).strip() if m else None


def _category_match(question: str, contexts: list[dict]) -> bool:
    """top hit 의 doc_title prefix 가 inferred 카테고리와 일치 여부.

    inferred 가 None (질문에서 도메인 키워드 0개 매칭) 이면 False.
    contexts 가 비어 있어도 False.
    "공통" 은 fallback 카테고리이므로 일치로 인정하지 않는다 — 사용자가
    재무 질문했는데 공통 사규에서만 답하면 신뢰도가 약하다고 판단.
    """
    if not contexts:
        return False
    # lazy import — confidence ↔ chatbot 순환 회피.
    from .chatbot import infer_categories

    inferred = infer_categories(question)
    if not inferred:
        return False

    inferred_set = {c.strip() for c in inferred if c}
    inferred_set.discard("공통")  # 공통은 매칭에서 제외
    if not inferred_set:
        return False

    top = contexts[0] or {}
    title_cat = _title_category(str(top.get("doc_title") or ""))
    return bool(title_cat and title_cat in inferred_set)


def _doc_kind_diversity(contexts: list[dict]) -> int:
    kinds = {c.get("doc_kind") for c in contexts if c.get("doc_kind")}
    return len(kinds)


def calculate_confidence(question: str, contexts: list[dict]) -> str:
    """4개 시그널 조합으로 'high' | 'medium' | 'low' 분류.

    Args:
        question: 사용자 질의 (mask 후 또는 raw — infer_categories 는
                  한글 키워드 매칭이라 mask 영향 적음).
        contexts: chatbot 의 retrieval 결과 (또는 retrieve_for_eval 결과).

    Returns:
        'high' / 'medium' / 'low'. critical 모드의 prefix 활성·chip
        표시는 호출자 (chatbot.py / app.py) 가 분기.
    """
    hit = len(contexts or [])
    if hit == 0:
        return "low"

    diversity = _doc_kind_diversity(contexts)
    cat_ok = _category_match(question, contexts)

    if diversity >= 2 and cat_ok and hit >= 3:
        return "high"
    if diversity >= 1 and hit >= 2:
        return "medium"
    return "low"


# ── 디버깅·진단 보조 ─────────────────────────────────────────
def signals(question: str, contexts: list[dict]) -> dict:
    """본 분류기가 사용한 시그널 dump — admin Eval 탭 등에서 활용 가능."""
    scores: list[float] = []
    for c in (contexts or []):
        try:
            scores.append(float(c.get("score") or 0.0))
        except (TypeError, ValueError):
            continue
    return {
        "hit_count": len(contexts or []),
        "doc_kind_diversity": _doc_kind_diversity(contexts or []),
        "category_match": _category_match(question, contexts or []),
        "best_score": max(scores) if scores else 0.0,
    }
