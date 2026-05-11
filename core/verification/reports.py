"""VerificationReport schema + Korean rendering."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Verdict(str, Enum):
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"
    ERROR = "error"  # Claude API 호출 실패 등


@dataclass
class ClaimGrounding:
    claim_text: str
    cited_clause: str  # e.g. "(공통) 일반 사건사고 보고지침 제4.1.3조"
    matched_chunk_id: str | None
    match_type: str  # "exact" | "semantic" | "partial" | "none"
    match_evidence: str | None  # 청크 텍스트의 supporting snippet
    issue: str | None = None


@dataclass
class CoverageGap:
    missing_doc_or_clause: str
    expected_topic: str
    severity: str  # "HIGH" | "MEDIUM" | "LOW"
    rationale: str


@dataclass
class VerificationReport:
    verdict: Verdict
    overall_score: float  # 0-100

    grounded_claims: list[ClaimGrounding] = field(default_factory=list)
    hallucinated_claims: list[ClaimGrounding] = field(default_factory=list)
    coverage_gaps: list[CoverageGap] = field(default_factory=list)
    consistency_issues: list[str] = field(default_factory=list)

    judge_model: str = "claude-opus-4-7"
    judge_latency_ms: int = 0

    explanation: str = ""
    raw_response: str = ""  # 원본 Claude 응답 (디버그용)
    error: str | None = None

    @classmethod
    def from_error(cls, error_msg: str) -> "VerificationReport":
        return cls(
            verdict=Verdict.ERROR,
            overall_score=0.0,
            error=error_msg,
            explanation=f"검증 실패: {error_msg}",
        )

    @classmethod
    def from_json(
        cls, data: dict[str, Any], raw: str = "", latency_ms: int = 0,
    ) -> "VerificationReport":
        try:
            grounded = [
                ClaimGrounding(
                    claim_text=c.get("claim_text", ""),
                    cited_clause=c.get("cited_clause", ""),
                    matched_chunk_id=c.get("matched_chunk_id"),
                    match_type=c.get("match_type", "unknown"),
                    match_evidence=c.get("match_evidence"),
                )
                for c in data.get("grounded_claims", [])
            ]
            hallucinated = [
                ClaimGrounding(
                    claim_text=c.get("claim_text", ""),
                    cited_clause=c.get("cited_clause", ""),
                    matched_chunk_id=None,
                    match_type="none",
                    match_evidence=c.get("evidence"),
                    issue=c.get("issue", ""),
                )
                for c in data.get("hallucinated_claims", [])
            ]
            gaps = [
                CoverageGap(
                    missing_doc_or_clause=g.get("missing_doc_or_clause", ""),
                    expected_topic=g.get("expected_topic", ""),
                    severity=g.get("severity", "MEDIUM"),
                    rationale=g.get("rationale", ""),
                )
                for g in data.get("coverage_gaps", [])
            ]
            verdict_str = data.get("verdict", "fail")
            try:
                verdict = Verdict(verdict_str)
            except ValueError:
                verdict = Verdict.FAIL
            return cls(
                verdict=verdict,
                overall_score=float(data.get("overall_score", 0)),
                grounded_claims=grounded,
                hallucinated_claims=hallucinated,
                coverage_gaps=gaps,
                consistency_issues=data.get("consistency_issues", []),
                explanation=data.get("explanation", ""),
                raw_response=raw,
                judge_latency_ms=latency_ms,
            )
        except Exception as e:
            return cls.from_error(
                f"VerificationReport parse error: {type(e).__name__}: {e}"
            )


def render_report_markdown(report: VerificationReport) -> str:
    """Streamlit markdown 으로 렌더링."""
    verdict_emoji = {
        Verdict.PASS: "✅",
        Verdict.WARN: "⚠️",
        Verdict.FAIL: "❌",
        Verdict.ERROR: "🔥",
    }[report.verdict]

    lines: list[str] = [
        f"### {verdict_emoji} Verdict: **{report.verdict.value.upper()}**",
        f"**Overall score:** {report.overall_score:.1f} / 100",
        f"**Judge model:** `{report.judge_model}` ({report.judge_latency_ms}ms)",
        "",
    ]

    if report.error:
        lines.append(f"### 🔥 Error\n{report.error}")
        return "\n".join(lines)

    if report.explanation:
        lines.extend([f"**요약:** {report.explanation}", ""])

    if report.grounded_claims:
        lines.append(f"#### ✅ Grounded claims ({len(report.grounded_claims)})")
        for i, c in enumerate(report.grounded_claims, 1):
            lines.append(
                f"{i}. `{c.match_type}` — *{c.cited_clause}*  \n"
                f"   → {c.claim_text[:120]}{'...' if len(c.claim_text) > 120 else ''}"
            )
        lines.append("")

    if report.hallucinated_claims:
        lines.append(f"#### ❌ Hallucinated claims ({len(report.hallucinated_claims)})")
        for i, c in enumerate(report.hallucinated_claims, 1):
            lines.append(
                f"{i}. **{c.cited_clause}**  \n"
                f"   Issue: {c.issue}  \n"
                f"   Claim: {c.claim_text[:120]}"
            )
        lines.append("")

    if report.coverage_gaps:
        lines.append(f"#### 🕳️ Coverage gaps ({len(report.coverage_gaps)})")
        severity_emoji = {"HIGH": "🔴", "MEDIUM": "🟡", "LOW": "🟢"}
        for i, g in enumerate(report.coverage_gaps, 1):
            emoji = severity_emoji.get(g.severity, "⚪")
            lines.append(
                f"{i}. {emoji} **{g.missing_doc_or_clause}** ({g.severity})  \n"
                f"   Topic: {g.expected_topic}  \n"
                f"   Why: {g.rationale}"
            )
        lines.append("")

    if report.consistency_issues:
        lines.append(f"#### ⚠️ Consistency issues ({len(report.consistency_issues)})")
        for i, issue in enumerate(report.consistency_issues, 1):
            lines.append(f"{i}. {issue}")
        lines.append("")

    return "\n".join(lines)
