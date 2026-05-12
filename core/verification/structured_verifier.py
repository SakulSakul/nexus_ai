"""Deterministic structured verifier — chunk_id + verbatim_quote 검증."""

from __future__ import annotations

from dataclasses import dataclass, field

from core.synthesis.structured_schema import StructuredAnswer, StructuredClaim


@dataclass
class HallucinatedClaim:
    claim: StructuredClaim
    reason: str


@dataclass
class CoverageGap:
    topic: str
    severity: str
    expected_doc: str = ""


@dataclass
class StructuredVerificationResult:
    verdict: str
    overall_score: float
    grounded_count: int = 0
    hallucinated_count: int = 0
    hallucinated_details: list = field(default_factory=list)
    coverage_gaps: list = field(default_factory=list)
    chunk_usage_rate: float = 0.0


def _verbatim_matches(quote: str, chunk_text: str, threshold: float = 0.7) -> bool:
    """Phase 7.1: Token-overlap based fuzzy matching.

    - Exact match 우선 (fast path)
    - 실패 시 whitespace normalize
    - 그래도 실패 시 token overlap (한국어 2+자 토큰, 70% 이상)
    """
    if not quote:
        return True
    # Fast path: exact substring.
    if quote in chunk_text:
        return True
    # Whitespace normalize.
    nq = " ".join(quote.split())
    nt = " ".join(chunk_text.split())
    if nq in nt:
        return True
    # Token overlap (조항 분리 / 줄바꿈에 robust).
    q_tokens = {t for t in nq.split() if len(t) >= 2}
    if not q_tokens:
        return False
    t_tokens = set(nt.split())
    overlap = len(q_tokens & t_tokens) / len(q_tokens)
    return overlap >= threshold


def _topic_covered(topic: str, all_claims_text: str, threshold: float = 0.4) -> bool:
    """Phase 7.1 + 7.2: Partial keyword overlap.

    - 키워드 40% 이상 매칭 시 covered (Phase 7.2: 50% → 40%)
    - 모든 claim text 합본에서 검색 (claim 분산 허용)
    """
    keywords = [kw for kw in (topic or "").split() if len(kw) >= 2]
    if not keywords:
        return False
    matched = sum(1 for kw in keywords if kw in all_claims_text)
    return (matched / len(keywords)) >= threshold


def verify_structured(
    answer: StructuredAnswer, chunks: list, golden: dict | None = None,
) -> StructuredVerificationResult:
    """Deterministic 검증:
    - chunk_id 가 실제 청크 리스트에 존재
    - verbatim_quote 가 해당 청크 텍스트에 존재 (Phase 7.1 fuzzy)
    - golden expected_clauses 의 topic 키워드 답변 본문 커버
    """
    chunk_map: dict = {}
    for c in chunks or []:
        if not isinstance(c, dict):
            continue
        cid = str(c.get("id") or c.get("chunk_id") or "")
        text = c.get("text") or c.get("content") or ""
        if cid:
            chunk_map[cid] = text

    grounded: list = []
    hallucinated: list = []
    used_ids: set = set()

    for section in answer.sections:
        for claim in section.claims:
            if claim.chunk_id not in chunk_map:
                hallucinated.append(HallucinatedClaim(claim, "chunk_id_not_found"))
                continue
            chunk_text = chunk_map[claim.chunk_id]
            quote = (claim.verbatim_quote or "").strip()
            if not _verbatim_matches(quote, chunk_text):
                hallucinated.append(HallucinatedClaim(claim, "quote_not_in_chunk"))
                continue
            grounded.append(claim)
            used_ids.add(claim.chunk_id)

    coverage_gaps: list = []
    if isinstance(golden, dict):
        # Phase 7.1: 모든 claim text 합본 — 분산된 claim 도 cover 인정.
        all_claims_text = " ".join(
            claim.text
            for section in answer.sections
            for claim in section.claims
        )
        # Phase 7.2: unsupported_topics / data_gaps 도 검색 대상.
        # LLM 이 청크 한계를 정직히 명시한 항목 → coverage gap 으로 penalize 안 함.
        acknowledged_text = " ".join(
            (answer.unsupported_topics or []) + (answer.data_gaps or [])
        )
        for expected in golden.get("expected_clauses", []) or []:
            topic = expected.get("topic", "") or ""
            severity = expected.get("severity", "MEDIUM")
            if _topic_covered(topic, all_claims_text):
                continue
            if acknowledged_text and _topic_covered(
                topic, acknowledged_text, threshold=0.3,
            ):
                continue
            coverage_gaps.append(CoverageGap(
                topic=topic,
                severity=severity,
                expected_doc=expected.get("expected_doc", "") or "",
            ))

    high_gaps = sum(1 for g in coverage_gaps if g.severity == "HIGH")
    total = len(grounded) + len(hallucinated)

    # Phase 7.2: Verdict scoring 재조정.
    # 진짜 risk (Hallucination) 없으면 최소 WARN. HIGH gap 0 + MEDIUM only 면
    # PASS or 좋은 WARN. unsupported/data_gaps 에 정직히 명시한 항목은 covered.
    if hallucinated:
        verdict = "fail"
        score = max(0.0, 100.0 - 30 * len(hallucinated) - 5 * high_gaps)
    elif total == 0:
        verdict = "fail"
        score = 0.0
    elif high_gaps > 5:
        verdict = "fail"
        score = max(40.0, 100.0 - 10 * high_gaps - 3 * len(coverage_gaps))
    elif high_gaps > 2:
        verdict = "warn"
        score = max(60.0, 100.0 - 8 * high_gaps - 2 * len(coverage_gaps))
    elif high_gaps > 0:
        verdict = "warn"
        score = max(70.0, 100.0 - 6 * high_gaps - 2 * len(coverage_gaps))
    elif coverage_gaps:
        medium_count = sum(1 for g in coverage_gaps if g.severity == "MEDIUM")
        if medium_count >= 4:
            verdict = "warn"
            score = max(75.0, 100.0 - 4 * medium_count)
        else:
            verdict = "pass"
            score = max(80.0, 100.0 - 3 * len(coverage_gaps))
    else:
        verdict = "pass"
        score = 100.0

    return StructuredVerificationResult(
        verdict=verdict,
        overall_score=float(score),
        grounded_count=len(grounded),
        hallucinated_count=len(hallucinated),
        hallucinated_details=hallucinated,
        coverage_gaps=coverage_gaps,
        chunk_usage_rate=(len(used_ids) / len(chunks)) if chunks else 0.0,
    )
