"""verified_ask: Gemini 합성 → Claude 검증 → policy decision.

Phase 4 — dual-LLM 본질 실현. 라이브 chat 에서 사용자 답변을 보내기 전에
Claude judge 가 검증. PASS/WARN/FAIL 결과에 따라 답변 표시 정책 결정.

Block-until-verified 모드 — 컴플라이언스 신뢰성 절대 우선.
- PASS: Gemini 답변 그대로 표시
- WARN: Gemini 답변 + 주의 배지 표시
- FAIL: fallback 메시지 (CSR팀 확인 안내), Gemini 답변 미노출
- ERROR (Claude API 실패): Gemini 답변 + 검증 시스템 오류 명시
"""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass
from typing import Any, Optional

from core.chatbot import ask
from core.nexus_query_rewriter import nexus_classify_to_incident_nodes
from core.verification.claude_judge import verify_with_claude
from core.verification.reports import VerificationReport, Verdict
from core.taxonomy.golden_citations import lookup_golden


# 정책 메시지 ─────────────────────────────────────
FALLBACK_MESSAGE = (
    "죄송합니다. 본 시스템이 충분한 신뢰도로 답변하기 어려운 질문입니다.  \n"
    "**CSR팀 또는 관할 부서에 직접 문의 부탁드립니다.**  \n\n"
    "(시스템이 사규 청크와 답변의 정합성을 검증한 결과 신뢰도가 부족합니다)"
)

WARN_BADGE = (
    "⚠️ **검증 결과: 주의** — 본 답변은 일부 사규 조항 누락 가능성이 있습니다. "
    "정확한 사항은 관할 부서 확인 바랍니다."
)


@dataclass
class VerifiedAnswer:
    """라이브 chat 에 반환되는 검증된 답변."""
    text: str                            # 사용자에게 표시될 최종 답변
    verdict: str                         # 'pass' | 'warn' | 'fail' | 'error'
    score: float                         # 0-100
    report: VerificationReport           # 전체 검증 보고서 (디버그/admin 용)
    badge: Optional[str]                 # 사용자 UI 에 표시할 배지 텍스트 ('pass'/'warn'/'fail'/'error'/None)
    elapsed_total_ms: int                # 전체 소요 시간
    elapsed_gemini_ms: int               # Gemini 부분
    elapsed_claude_ms: int               # Claude 부분


def verified_ask(
    supabase: Any,
    question: str,
    *,
    category: Optional[str] = None,
    audit_source: str = "live_chat",
) -> VerifiedAnswer:
    """Gemini 합성 + Claude 검증 통합 흐름.

    Args:
        supabase: Supabase client (chatbot.ask 가 요구).
        question: 사용자 query.
        category: chatbot.ask 의 category 인자 (기본 None — 자동 추론).
        audit_source: audit log 의 source 필드.

    Returns:
        VerifiedAnswer — verdict + 표시할 텍스트 + 배지 + 시간.
    """
    t0 = time.time()

    # === 1. Gemini synthesis ===
    t_gemini_start = time.time()
    try:
        ans = ask(supabase, question=question, category=category)
    except Exception as e:
        print(
            f"[verified_ask] Gemini ask() failed: {type(e).__name__}: {e}",
            file=sys.stderr, flush=True,
        )
        return _error_response(question, f"답변 생성 실패: {e}", audit_source, t0)
    elapsed_gemini_ms = int((time.time() - t_gemini_start) * 1000)

    # Answer dataclass normalize.
    if hasattr(ans, "text") and hasattr(ans, "contexts"):
        gemini_text = ans.text or ""
        chunks = list(ans.contexts) if ans.contexts else []
    elif isinstance(ans, tuple):
        gemini_text = ans[0] if ans else ""
        chunks = list(ans[1]) if len(ans) > 1 and ans[1] else []
    elif isinstance(ans, dict):
        gemini_text = ans.get("text") or ans.get("answer") or ""
        chunks = ans.get("contexts") or ans.get("chunks") or []
    else:
        gemini_text = str(ans)
        chunks = []

    # === 2. Classifier ===
    incident_nodes = sorted(set(nexus_classify_to_incident_nodes(question) or []))

    # === 3. Claude verification ===
    t_claude_start = time.time()
    golden = lookup_golden(incident_nodes)
    report = verify_with_claude(
        query=question,
        chunks=chunks,
        answer=gemini_text,
        golden_citations=golden,
        incident_nodes=incident_nodes,
    )
    elapsed_claude_ms = int((time.time() - t_claude_start) * 1000)

    # === 4. Policy — verdict 별 표시 결정 ===
    verdict_value = (
        report.verdict.value
        if hasattr(report.verdict, "value")
        else str(report.verdict)
    )

    if verdict_value == "pass":
        display_text = gemini_text
        badge = "pass"
    elif verdict_value == "warn":
        display_text = gemini_text + "\n\n---\n" + WARN_BADGE
        badge = "warn"
    elif verdict_value == "fail":
        display_text = FALLBACK_MESSAGE
        badge = "fail"
    else:  # error
        display_text = (
            gemini_text +
            "\n\n---\n⚠️ **검증 시스템 일시 오류** — 답변 사용 시 주의 바랍니다."
        )
        badge = "error"

    elapsed_total_ms = int((time.time() - t0) * 1000)

    # === 5. Audit log (Phase 3 hook — 모듈 미존재 시 silent skip) ===
    _audit_log(
        question=question,
        incident_nodes=incident_nodes,
        chunks=chunks,
        gemini_text=gemini_text,
        elapsed_gemini_ms=elapsed_gemini_ms,
        report=report,
        elapsed_claude_ms=elapsed_claude_ms,
        elapsed_total_ms=elapsed_total_ms,
        audit_source=audit_source,
    )

    print(
        f"[verified_ask] verdict={verdict_value} score={report.overall_score:.1f} "
        f"gemini={elapsed_gemini_ms}ms claude={elapsed_claude_ms}ms "
        f"total={elapsed_total_ms}ms",
        file=sys.stderr, flush=True,
    )

    return VerifiedAnswer(
        text=display_text,
        verdict=verdict_value,
        score=report.overall_score,
        report=report,
        badge=badge,
        elapsed_total_ms=elapsed_total_ms,
        elapsed_gemini_ms=elapsed_gemini_ms,
        elapsed_claude_ms=elapsed_claude_ms,
    )


def _error_response(
    question: str, error_msg: str, audit_source: str, t0: float,
) -> VerifiedAnswer:
    """Gemini 실패 등 critical error 시 fallback."""
    elapsed = int((time.time() - t0) * 1000)
    empty_report = VerificationReport.from_error(error_msg)
    return VerifiedAnswer(
        text=FALLBACK_MESSAGE,
        verdict="error",
        score=0.0,
        report=empty_report,
        badge="error",
        elapsed_total_ms=elapsed,
        elapsed_gemini_ms=0,
        elapsed_claude_ms=0,
    )


def _audit_log(*, question, incident_nodes, chunks, gemini_text,
               elapsed_gemini_ms, report, elapsed_claude_ms,
               elapsed_total_ms, audit_source) -> None:
    """Audit log 저장 (silent fail — Phase 3 미머지 시 흐름 보호)."""
    try:
        from core.audit.logger import log_query
        from core.audit.schemas import AuditLogEntry

        chunk_ids = [
            str(c.get("id") or c.get("chunk_id") or "")
            for c in chunks
        ]
        report_dict = {
            "verdict": (
                report.verdict.value
                if hasattr(report.verdict, "value")
                else "error"
            ),
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
            source=audit_source,
            query=question,
            incident_nodes=incident_nodes,
            retrieved_chunk_ids=chunk_ids,
            retrieved_chunk_count=len(chunks),
            gemini_model_id="gemini",
            gemini_answer=gemini_text[:5000],
            gemini_latency_ms=elapsed_gemini_ms,
            claude_model_id=report.judge_model,
            claude_verdict=report_dict["verdict"],
            claude_score=report.overall_score,
            claude_report=report_dict,
            claude_latency_ms=elapsed_claude_ms,
            total_latency_ms=elapsed_total_ms,
        ))
    except Exception as e:
        # Phase 3 audit 모듈 미머지 / 일시 오류 — main 흐름 보호.
        print(
            f"[verified_ask] audit hook silent skip: "
            f"{type(e).__name__}: {e}",
            file=sys.stderr, flush=True,
        )
