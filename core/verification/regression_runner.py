"""회귀 테스트 일괄 runner — ask() + Claude judge 자동화 (Phase 2.6)."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from .reports import VerificationReport, Verdict
from .claude_judge import verify_with_claude


@dataclass
class RegressionResult:
    category: str
    query: str
    verdict: str
    score: float
    grounded_count: int
    hallucinated_count: int
    high_gaps: int
    medium_gaps: int
    low_gaps: int
    incident_nodes: list = field(default_factory=list)
    chunk_count: int = 0
    error: Optional[str] = None
    report: Optional[VerificationReport] = None  # full for drill-down


def run_regression_suite(
    supabase: Any,
    cases: list,
    on_progress: Optional[Callable[[int, int, dict], None]] = None,
    delay_seconds: float = 2.0,
    max_retries: int = 2,
) -> list:
    """회귀 테스트 일괄 실행.

    각 case 마다:
    1. ask(supabase, question=query, category=None) → answer + contexts
    2. classifier → incident_nodes
    3. lookup_golden(incident_nodes)
    4. verify_with_claude(...)
    5. 결과 수집

    API rate limit (529) 시 max_retries 까지 자동 재시도.
    """
    from core.chatbot import ask
    from core.nexus_query_rewriter import nexus_classify_to_incident_nodes
    from core.taxonomy.golden_citations import lookup_golden

    results: list = []
    total = len(cases)

    for i, case in enumerate(cases):
        if on_progress:
            try:
                on_progress(i, total, case)
            except Exception:
                pass
        result = _run_single_case(
            supabase, case, ask, nexus_classify_to_incident_nodes,
            lookup_golden, max_retries,
        )
        results.append(result)
        # API rate limit 회피 + 사용자 체감 progress 위한 sleep.
        if i < total - 1:
            time.sleep(delay_seconds)

    return results


def _run_single_case(
    supabase: Any,
    case: dict,
    ask_fn: Callable,
    classify_fn: Callable,
    lookup_golden_fn: Callable,
    max_retries: int,
) -> RegressionResult:
    query = case["query"]
    category = case["category"]

    try:
        # 1. ask() 호출 — Answer dataclass 반환.
        _t_ask = time.time()
        ans = ask_fn(supabase, question=query, category=None)
        gemini_latency_ms = int((time.time() - _t_ask) * 1000)
        if hasattr(ans, "text") and hasattr(ans, "contexts"):
            answer_text = ans.text or ""
            chunks = list(ans.contexts) if ans.contexts else []
        else:
            answer_text = str(ans)
            chunks = []

        # 2. classifier
        incident_nodes = sorted(set(classify_fn(query) or []))

        # 3. golden lookup
        golden = lookup_golden_fn(incident_nodes)

        # 4. verification with retry on 529.
        report = _verify_with_retry(
            query, chunks, answer_text, golden, incident_nodes, max_retries,
        )

        # Phase 3: audit log (silent fail).
        try:
            from core.audit.logger import log_query
            from core.audit.schemas import AuditLogEntry
            chunk_ids = [
                str(c.get("id") or c.get("chunk_id") or "")
                for c in chunks if isinstance(c, dict)
            ]
            verdict_val = (
                report.verdict.value
                if hasattr(report.verdict, "value")
                else "error"
            )
            report_payload = {
                "verdict": verdict_val,
                "overall_score": report.overall_score,
                "grounded_count": len(report.grounded_claims),
                "hallucinated_count": len(report.hallucinated_claims),
                "high_gaps": sum(
                    1 for g in report.coverage_gaps if g.severity == "HIGH"
                ),
                "medium_gaps": sum(
                    1 for g in report.coverage_gaps if g.severity == "MEDIUM"
                ),
                "low_gaps": sum(
                    1 for g in report.coverage_gaps if g.severity == "LOW"
                ),
                "explanation": report.explanation,
                "error": report.error,
            }
            log_query(AuditLogEntry(
                source="regression_runner",
                query=query,
                incident_nodes=incident_nodes,
                retrieved_chunk_ids=chunk_ids,
                retrieved_chunk_count=len(chunks),
                gemini_model_id="gemini",
                gemini_answer=(answer_text or "")[:5000] or None,
                gemini_latency_ms=gemini_latency_ms,
                claude_model_id=report.judge_model,
                claude_verdict=verdict_val,
                claude_score=report.overall_score,
                claude_report=report_payload,
                claude_latency_ms=report.judge_latency_ms,
                notes=f"category={category}",
            ))
        except Exception as _audit_e:
            import sys as _sys
            print(
                f"[regression_runner] audit hook failed (non-blocking): "
                f"{type(_audit_e).__name__}: {_audit_e}",
                file=_sys.stderr, flush=True,
            )

        return RegressionResult(
            category=category,
            query=query,
            verdict=report.verdict.value,
            score=report.overall_score,
            grounded_count=len(report.grounded_claims),
            hallucinated_count=len(report.hallucinated_claims),
            high_gaps=sum(
                1 for g in report.coverage_gaps if g.severity == "HIGH"
            ),
            medium_gaps=sum(
                1 for g in report.coverage_gaps if g.severity == "MEDIUM"
            ),
            low_gaps=sum(
                1 for g in report.coverage_gaps if g.severity == "LOW"
            ),
            incident_nodes=incident_nodes,
            chunk_count=len(chunks),
            error=report.error,
            report=report,
        )

    except Exception as e:
        empty_report = VerificationReport.from_error(
            f"runner exception: {type(e).__name__}: {e}"
        )
        return RegressionResult(
            category=category,
            query=query,
            verdict="error",
            score=0.0,
            grounded_count=0,
            hallucinated_count=0,
            high_gaps=0,
            medium_gaps=0,
            low_gaps=0,
            incident_nodes=[],
            chunk_count=0,
            error=f"{type(e).__name__}: {e}",
            report=empty_report,
        )


def _verify_with_retry(
    query: str,
    chunks: list,
    answer: str,
    golden: dict | None,
    incident_nodes: list,
    max_retries: int,
) -> VerificationReport:
    """529 overloaded_error / API connection 등 일시적 실패 시 재시도."""
    last_report: Optional[VerificationReport] = None
    for attempt in range(max_retries + 1):
        report = verify_with_claude(
            query=query,
            chunks=chunks,
            answer=answer,
            golden_citations=golden,
            incident_nodes=incident_nodes,
        )
        if report.verdict == Verdict.ERROR and report.error and (
            "529" in report.error
            or "overloaded" in report.error.lower()
            or "rate limit" in report.error.lower()
            or "connection" in report.error.lower()
        ):
            last_report = report
            if attempt < max_retries:
                time.sleep(5 * (attempt + 1))  # 5s, 10s 백오프
                continue
        return report
    return last_report or VerificationReport.from_error("retry exhausted")
