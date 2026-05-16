"""Button 분기 logic — UI ↔ Validation 통일 (Single Source of Truth).

PR-Multi-Signal-Button-Branch-Refactor:
- Query intent signal (사용자 의도)
- Matched docs categories signal (retrieval 결과)
- Answer keyword signal (현재 logic, fallback)

Priority order:
1. Critical mode → report
2. Query HR intent + answer graceful → hr_inquiry
3. Query HR intent + low confidence → hr_inquiry
4. Report intent (query/contexts/answer) → report
5. Answer graceful (fallback) → hr_inquiry
6. Default → hidden
"""
from __future__ import annotations

import re


# ── Signal 1: Query intent keywords ──────────────────────────────────────
# 사용자 query 자체의 keyword 가 가장 강한 signal — LLM variability 영향 0.

QUERY_HR_INTENT_KEYWORDS: tuple[str, ...] = (
    "휴가", "수당", "복리후생", "근태", "휴직", "급여",
    "출퇴근", "재택", "부서 이동", "승진", "평가",
    "이의 제기", "근무 시간", "월급", "퇴직금",
    "초과근무", "연차", "교육 신청", "직급",
)

QUERY_REPORT_INTENT_KEYWORDS: tuple[str, ...] = (
    "신고", "보고", "위반", "분실", "도용", "유출",
    "수수", "받았", "발견", "위조", "횡령", "뇌물",
    "절도", "압력", "누설", "반출", "협박", "해킹",
    "발생했", "공유 요구", "사적으로", "추천했",
    "변경했", "도둑질", "갑질", "차별",
)


# ── Signal 2: Doc domain categories ─────────────────────────────────────
# Retrieval 결과 의 도메인 — 답변 본문 variability 영향 X.

REPORT_DOC_DOMAINS: frozenset[str] = frozenset({
    "공통", "공정거래", "정보보안", "안전", "환경",
    "재무", "총무", "영업", "CSR",
})
HR_ONLY_DOMAINS: frozenset[str] = frozenset({"인사"})


# ── Signal 3: Answer keyword (PR #158 의 logic, fallback) ──────────────

ANSWER_REPORT_KEYWORDS: tuple[str, ...] = (
    "신고·조사",
    "SRMS",
    "신세계면세점 핫라인",
    "클린신고",
    "일반 사건사고 보고지침",
    "중대 사건사고 보고지침",
    "공정거래법 위반",
    "공정거래를 저해",
    "위변조 또는 허위작성",
    "부정/부실행위",
)

ANSWER_HR_GRACEFUL_KEYWORDS: tuple[str, ...] = (
    "인사 규정·복리후생 등 인사 행정 사항은 인사교육팀에 문의",
    "인사교육팀에 문의해 주시기 바랍니다",
)


def _extract_context_domains(contexts: list[dict] | None) -> set[str]:
    """contexts 의 title 에서 (도메인) 추출. PR #149 의 카테고리 chip logic 과 동일 패턴."""
    if not contexts:
        return set()
    domains: set[str] = set()
    for ctx in contexts:
        if not isinstance(ctx, dict):
            continue
        title = ctx.get("title")
        if not title:
            continue
        m = re.match(r"\(([^)]+)\)", title)
        if m:
            domains.add(m.group(1).strip())
    return domains


def classify_button(
    query: str,
    answer_text: str,
    contexts: list[dict] | None,
    is_critical: bool,
    confidence: str,
) -> str:
    """Multi-signal button 분기.

    Args:
        query: 사용자 원본 query
        answer_text: 챗봇 답변 본문
        contexts: matched docs list (각 dict 에 "title" 키)
        is_critical: critical mode flag
        confidence: "low" | "medium" | "high"

    Returns:
        "report" | "hr_inquiry" | "hidden"
    """
    query = query or ""
    answer_text = answer_text or ""
    confidence = confidence or ""

    # ═══ 1. Critical 항상 report ═══
    if is_critical:
        return "report"

    # ═══ Signal 추출 ═══
    query_has_hr_intent = any(kw in query for kw in QUERY_HR_INTENT_KEYWORDS)
    query_has_report_intent = any(kw in query for kw in QUERY_REPORT_INTENT_KEYWORDS)

    answer_has_graceful = any(kw in answer_text for kw in ANSWER_HR_GRACEFUL_KEYWORDS)
    answer_has_report = any(kw in answer_text for kw in ANSWER_REPORT_KEYWORDS)

    context_domains = _extract_context_domains(contexts)
    contexts_only_hr = bool(context_domains) and (context_domains <= HR_ONLY_DOMAINS)
    contexts_has_report = bool(context_domains & REPORT_DOC_DOMAINS)

    # ═══ 2. HR intent + graceful 답변 → hr_inquiry ═══
    # Q39 출퇴근, Q40 재택, Q7 휴가 등 cover (retrieval noise 가 있어도 HR 우선)
    if query_has_hr_intent and answer_has_graceful:
        return "hr_inquiry"

    # ═══ 3. HR intent + low confidence → hr_inquiry ═══
    if query_has_hr_intent and confidence == "low":
        return "hr_inquiry"

    # ═══ 4. Report intent (query / contexts / answer) → report ═══
    # Q13 협력사 지정 / Q18 자녀 추천 / Q20 채용 압력 / Q24 노트북 반출 /
    # Q35 PW 공유 등 cover (query intent 또는 contexts 기반)
    if (
        query_has_report_intent
        or (contexts_has_report and not contexts_only_hr)
        or answer_has_report
    ):
        # HR intent + answer graceful 시 우선 graceful (위 2번에서 이미 처리)
        return "report"

    # ═══ 5. Answer graceful (fallback) → hr_inquiry ═══
    if answer_has_graceful or confidence == "low":
        return "hr_inquiry"

    # ═══ 6. Default → hidden ═══
    return "hidden"
