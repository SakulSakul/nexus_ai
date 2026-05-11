"""LLM 답변 사후 검증 및 자동 보정.

Layer 3 of synthesis hardening (PR #83) — prompt 무시 시 last-resort 안전망.
Layer 1 (SYSTEM_PROMPT) / Layer 2 (FORBIDDEN PATTERNS) 가 LLM 의 conservative
bias 를 막지 못한 경우 본 모듈이 답변을 자동 보정한다.

자동 보정 범위 (force-included 청크 있을 때만):
- "[참조: 검색 결과 없음]" → 실제 doc titles 자동 교체
- [참조] 섹션 자체 누락 시 force-included docs 자동 첨부

자동 보정 안 하지만 stderr 경고:
- "확인되지 않습니다" 류 표현 사용 (사용자가 답변 다시 시도 가능)
"""

from __future__ import annotations

import re
import sys


# Forbidden patterns — force-included 청크 있을 때 사용 시 자동 교체
_FORBIDDEN_NO_REF_PATTERNS: tuple = (
    r"\[참조:\s*검색 결과 없음\s*\]",
    r"\[참조:\s*관련 사규 미발견\s*\]",
    r"\[참조:\s*해당 사규 없음\s*\]",
    r"참조:\s*검색 결과 없음(?!\])",  # 대괄호 없는 변형
)

_WARNING_PATTERNS: tuple = (
    "관련 사규에서 확인되지 않습니다",
    "관련 사규가 확인되지 않았습니다",
    "해당 유형 문서가 검색되지 않았습니다",
    "검색되지 않았습니다",
)


def validate_and_repair_answer(
    answer: str,
    force_included_doc_titles: list,
    raw_chunks_count: int,
) -> tuple[str, list]:
    """LLM 답변을 검증하고 필요 시 자동 보정.

    Args:
        answer: LLM 이 생성한 답변
        force_included_doc_titles: force-include 된 doc titles (중복 제거)
        raw_chunks_count: 전체 검색된 청크 수

    Returns:
        (repaired_answer, applied_repairs_log)
    """
    if not answer:
        return answer, []

    repairs: list = []
    repaired = answer

    # 진짜 검색 결과 0건 케이스 — 보정 안 함.
    if not force_included_doc_titles and raw_chunks_count == 0:
        return answer, []

    # ==========================================================
    # Repair 1: "[참조: 검색 결과 없음]" → 실제 doc titles
    # ==========================================================
    if force_included_doc_titles:
        actual_ref_line = f"[참조: {', '.join(force_included_doc_titles)}]"
        for pattern in _FORBIDDEN_NO_REF_PATTERNS:
            if re.search(pattern, repaired):
                repaired = re.sub(pattern, actual_ref_line, repaired)
                repairs.append(
                    f"FORBIDDEN_NO_REF: '{pattern}' → '{actual_ref_line[:80]}...'"
                )
                print(
                    "[synthesis:validator] FORBIDDEN_NO_REF repaired",
                    file=sys.stderr, flush=True,
                )

    # ==========================================================
    # Repair 2: [참조: ] 섹션 자체 누락 시 자동 추가
    # ==========================================================
    if force_included_doc_titles and "[참조:" not in repaired:
        actual_ref_line = f"[참조: {', '.join(force_included_doc_titles)}]"
        repaired = repaired.rstrip() + f"\n\n{actual_ref_line}"
        repairs.append(f"MISSING_REF_SECTION: 자동 추가 — {actual_ref_line[:80]}")
        print(
            "[synthesis:validator] MISSING_REF auto-injected",
            file=sys.stderr, flush=True,
        )

    # ==========================================================
    # Repair 3: "확인되지 않습니다" — force-included 있는데 사용 시 stderr 경고
    # ==========================================================
    if force_included_doc_titles:
        for pattern in _WARNING_PATTERNS:
            if pattern in repaired:
                repairs.append(
                    f"SUSPICIOUS_DENIAL: '{pattern}' present despite "
                    f"{len(force_included_doc_titles)} force-included docs"
                )
                print(
                    f"[synthesis:validator] WARNING: LLM denial despite "
                    f"force-included chunks — '{pattern}'",
                    file=sys.stderr, flush=True,
                )
                # 자동 보정 안 함 — LLM 응답을 본문 차원에서 자동 교체하면 침해 큼.

    return repaired, repairs


def extract_force_included_titles(chunks: list) -> list:
    """contexts/chunks 에서 force-included doc title 만 dedup 추출."""
    titles: list = []
    seen: set = set()
    for c in (chunks or []):
        if not c.get("force_included_by_intent"):
            continue
        title = c.get("doc_title") or ""
        if title and title not in seen:
            titles.append(title)
            seen.add(title)
    return titles
