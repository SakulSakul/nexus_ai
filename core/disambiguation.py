"""모호한 query 의 후보 doc 식별 (PR-Disambiguation-Phase1).

retrieval 후 top doc 들의 score 차이 작거나 같은 사규명 다른 도메인 prefix 인
경우 → "모호한 query" 로 식별. 사용자에게 선택지 제시 가능.
"""
from __future__ import annotations

import re
from typing import Optional


# 사규 prefix pattern: "(안전)", "(환경)", "(공정거래)" 등
_PREFIX_RE = re.compile(r"^\(([^)]+)\)\s*(.+)$")

# score 차이 threshold (top1 대비 top2 가 80% 이상이면 모호)
_SCORE_RATIO_THRESHOLD = 0.80

# 최소 candidates (모호 판단)
_MIN_CANDIDATES = 2

# 최대 선택지 수
_MAX_CHOICES = 4


def _parse_title(title: str) -> tuple[Optional[str], str]:
    """사규명을 prefix 와 base 로 분리.

    "(안전) 리스크 관리 지침" → ("안전", "리스크 관리 지침")
    "신세계그룹 CREDO" → (None, "신세계그룹 CREDO")
    """
    if not title:
        return (None, "")
    m = _PREFIX_RE.match(title.strip())
    if not m:
        return (None, title.strip())
    return (m.group(1).strip(), m.group(2).strip())


def _query_core_tokens(question: str) -> set:
    """query 의 핵심 단어 추출 (2글자+, 조사/종결부호 제거)."""
    tokens: set = set()
    for t in (question or "").split():
        t = t.rstrip("?!.,;:'\"").lower()
        if len(t) >= 2:
            tokens.add(t)
    return tokens


def _doc_chunks_match_query(chunks: list, q_tokens: set) -> bool:
    """doc 의 chunk 들이 query 와 의미 매칭되는지 (PR-Disambiguation-Precision).

    a) force_include_source 가 title_direct / auto_keywords (또는 auto_kw) → 매칭
    b) chunk text 가 query 핵심 단어 포함 → 매칭
    """
    for c in chunks:
        src = (c.get("force_include_source") or "").lower()
        if "title_direct" in src or "auto_keywords" in src or "auto_kw" in src:
            return True
        text = (c.get("text") or "").lower()
        if text and any(tok in text for tok in q_tokens):
            return True
    return False


def detect_ambiguity(top_chunks: list[dict], question: str = "") -> dict:
    """retrieval top chunks 가 모호한지 판단.

    Returns: {
        "is_ambiguous": bool,
        "reason": str,
        "candidate_docs": list of unique top doc titles (최대 4개),
    }
    """
    if not top_chunks or len(top_chunks) < _MIN_CANDIDATES:
        return {"is_ambiguous": False, "reason": "insufficient_candidates", "candidate_docs": []}

    # top_chunks 의 doc title 추출 + title 별 chunk 그룹화
    seen_titles: list[str] = []
    seen_set: set = set()
    chunks_by_title: dict[str, list] = {}
    for c in top_chunks[:10]:
        title = c.get("doc_title") or c.get("title") or c.get("document_title") or ""
        if not title:
            continue
        if title not in seen_set:
            seen_titles.append(title)
            seen_set.add(title)
        chunks_by_title.setdefault(title, []).append(c)

    if len(seen_titles) < _MIN_CANDIDATES:
        return {"is_ambiguous": False, "reason": "single_doc", "candidate_docs": []}

    # 모호 detect 1: 같은 base 사규명, 다른 prefix
    base_map: dict[str, list[str]] = {}
    for t in seen_titles:
        prefix, base = _parse_title(t)
        if not base:
            continue
        base_map.setdefault(base, []).append(t)

    multi_prefix_groups = {b: titles for b, titles in base_map.items() if len(titles) >= 2}

    if multi_prefix_groups:
        # 가장 많은 group 의 candidates
        best_group = max(multi_prefix_groups.values(), key=len)
        # PR-Disambiguation-Precision: query 와 의미 매칭되는 candidate 만 유지
        q_tokens = _query_core_tokens(question)
        matched_candidates = [
            t for t in best_group
            if _doc_chunks_match_query(chunks_by_title.get(t, []), q_tokens)
        ]
        # 매칭된 candidate 가 2개 미만이면 모호 X (false positive 제거)
        if len(matched_candidates) < _MIN_CANDIDATES:
            return {"is_ambiguous": False, "reason": "no_query_match", "candidate_docs": []}
        return {
            "is_ambiguous": True,
            "reason": "domain_overlap",
            "candidate_docs": matched_candidates[:_MAX_CHOICES],
        }

    # 모호 detect 2: top 2 의 score 비슷 — Phase 2 에서 구현. Phase 1 은 domain_overlap 만.

    return {"is_ambiguous": False, "reason": "clear_top", "candidate_docs": []}


def format_choice_suggestion(candidates: list[str]) -> str:
    """선택지를 사용자 친화적 문구로.

    ["(안전) 리스크 관리 지침", "(환경) 리스크 관리 지침"]
    → "💡 유사한 사규가 여러 개 있습니다. 어느 사규에 대한 답변을 원하시나요?
         · (안전) 리스크 관리 지침
         · (환경) 리스크 관리 지침
         ..."
    """
    if not candidates:
        return ""

    lines = ["", "---", "💡 **유사한 사규가 여러 개 있습니다.** 어느 사규에 대한 답변을 원하시나요?"]
    for c in candidates:
        lines.append(f"· {c}")
    lines.append("")
    lines.append("위 선택지 중 구체적으로 다시 질문해 주시면 더 정확한 답변을 드릴 수 있습니다.")

    return "\n".join(lines)
