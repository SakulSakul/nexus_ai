"""검증 자동화 module — 미리 등록된 query 자동 실행 + 결과 수집.

PR-Add-Validation-Automation:
- 새 PR 머지 후 회귀 자동 검증 (수동 6 query 입력 대체)
- LLM variability 객관 측정 (반복 실행 시 hit rate)
- Golden Dataset baseline 누적

사용 (admin panel):
- '검증 실행' button click → 8 query 순차 실행 → 종합 표 + Markdown export
- 각 query ~15~40초, 총 ~10분
- 비용 ~$0.24/실행 (query 당 $0.030)
"""

from __future__ import annotations

import re
import sys
import time
from dataclasses import asdict, dataclass, field
from typing import Any


# 검증 query — 새 PR 머지 후 회귀 검증용
# 모든 도메인 cover: CSR / 환경 / 공정거래 / 총무 / 재무 / Critical / 인사 graceful / 정보보안
DEFAULT_VALIDATION_QUERIES: tuple[str, ...] = (
    "거래처에서 명절 선물을 받았어요",
    "환경 사고 발생 시 어떻게 해야 하나요?",
    "경쟁사 직원과 가격 정보 공유해도 되나요?",
    "회사 인장 도용한 사례를 발견했어요",
    "해외 출장 비용 정산 방법",
    "직장 내 괴롭힘 신고하려고 하는데 가해자가 동기예요",
    "휴가 미사용 수당 받을 수 있나요?",
    "개인정보 유출 사고가 발생했어요",
)


# Button 분기 keyword (app.py:_render_action_buttons 와 동일 — PR #158)
_REPORT_KEYWORDS: tuple[str, ...] = (
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

_HR_GRACEFUL_KEYWORDS: tuple[str, ...] = (
    "인사 규정·복리후생 등 인사 행정 사항은 인사교육팀에 문의",
    "인사교육팀에 문의해 주시기 바랍니다",
)


# === PR-DB-Based-Validation-Queries: DB CRUD ===

def fetch_active_queries(supabase: Any) -> tuple[str, ...]:
    """DB 의 active validation queries 조회.

    DB 조회 실패 시 (table 없음/permission 등) 안전 fallback —
    hardcoded DEFAULT_VALIDATION_QUERIES 사용.

    Returns:
        tuple[str, ...] — active query_text 순서대로.
    """
    try:
        result = (
            supabase.table("nexus_validation_queries")
            .select("query_text, category, expected_button")
            .eq("is_active", True)
            .order("id", desc=False)
            .execute()
        )
        if result.data:
            queries = tuple(
                row["query_text"] for row in result.data if row.get("query_text")
            )
            if queries:
                print(
                    f"[validation] DB fetched {len(queries)} active queries",
                    file=sys.stderr,
                    flush=True,
                )
                return queries
    except Exception as e:
        print(
            f"[validation] DB fetch failed, using hardcoded fallback: {e}",
            file=sys.stderr,
            flush=True,
        )
    return DEFAULT_VALIDATION_QUERIES


def add_query(
    supabase: Any,
    query_text: str,
    *,
    category: str | None = None,
    expected_button: str | None = None,
    note: str | None = None,
) -> dict | None:
    """새 validation query 추가."""
    try:
        result = (
            supabase.table("nexus_validation_queries")
            .insert(
                {
                    "query_text": query_text,
                    "category": category,
                    "expected_button": expected_button,
                    "note": note,
                    "is_active": True,
                }
            )
            .execute()
        )
        return result.data[0] if result.data else None
    except Exception as e:
        print(f"[validation] add_query failed: {e}", file=sys.stderr, flush=True)
        return None


def list_all_queries(supabase: Any) -> list[dict]:
    """모든 validation query 조회 (active + inactive)."""
    try:
        result = (
            supabase.table("nexus_validation_queries")
            .select("*")
            .order("id", desc=False)
            .execute()
        )
        return result.data or []
    except Exception:
        return []


def set_query_active(supabase: Any, query_id: int, is_active: bool) -> bool:
    """query 활성/비활성 toggle."""
    try:
        supabase.table("nexus_validation_queries").update(
            {"is_active": is_active}
        ).eq("id", query_id).execute()
        return True
    except Exception:
        return False


def delete_query(supabase: Any, query_id: int) -> bool:
    """query 삭제."""
    try:
        supabase.table("nexus_validation_queries").delete().eq(
            "id", query_id
        ).execute()
        return True
    except Exception:
        return False


@dataclass
class ValidationResult:
    """단일 query 검증 결과."""

    idx: int
    query: str
    answer_text: str
    answer_chars: int
    elapsed_seconds: float
    is_critical: bool
    confidence: str
    matched_doc_count: int
    cited_docs: list[str] = field(default_factory=list)
    button_type: str = ""
    error: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)

    def to_summary_row(self) -> dict:
        """DataFrame 표시용 요약 행."""
        return {
            "#": self.idx,
            "Query": self.query[:30] + ("…" if len(self.query) > 30 else ""),
            "Chars": self.answer_chars,
            "Elapsed (s)": round(self.elapsed_seconds, 1),
            "Critical": "✅" if self.is_critical else "",
            "Conf": self.confidence,
            "Docs": self.matched_doc_count,
            "Button": self.button_type,
            "Error": self.error or "",
        }

    def to_markdown(self) -> str:
        """Markdown export — Claude 수석에 paste 용."""
        if self.error:
            return f"## Q{self.idx}: {self.query}\n\n🔴 ERROR: {self.error}\n"
        cited_str = ", ".join(self.cited_docs[:10]) if self.cited_docs else "(없음)"
        return (
            f"## Q{self.idx}: {self.query}\n\n"
            f"- 답변 크기: {self.answer_chars} chars ({self.elapsed_seconds:.1f}초)\n"
            f"- Critical: {self.is_critical}, Confidence: {self.confidence}\n"
            f"- 매칭 docs: {self.matched_doc_count}\n"
            f"- 인용 docs: {cited_str}\n"
            f"- Button: {self.button_type}\n\n"
            f"### 답변 본문\n\n"
            f"```\n{self.answer_text}\n```\n"
        )


def _classify_button(answer_text: str, is_critical: bool, confidence: str) -> str:
    """app.py:_render_action_buttons 와 동일한 분기 logic — button label 만 추출.

    PR #158 의 logic 재현:
    - is_critical OR REPORT_KEYWORDS 매칭 → 신고 방법 안내
    - confidence=='low' OR HR_GRACEFUL_KEYWORDS 매칭 → 인사교육팀 문의
    - 그 외 → 숨김
    """
    at = answer_text or ""
    is_report = is_critical or any(kw in at for kw in _REPORT_KEYWORDS)
    is_hr = (confidence == "low") or any(kw in at for kw in _HR_GRACEFUL_KEYWORDS)
    if is_report:
        return "📞 신고 방법 안내"
    if is_hr:
        return "📞 인사교육팀 문의"
    return "(숨김)"


def _extract_cited_docs(answer_text: str) -> list[str]:
    """답변 본문에서 「📎 ((도메인) doc명))」 형식 추출 (중복 제거).

    PR #149 의 카테고리 chip logic 과 동일 패턴.
    """
    if not answer_text:
        return []
    pattern = r"📎\s*\(\(([^)]+)\)\s+([^)]+)\)?\)?"
    matches = re.findall(pattern, answer_text)
    seen = set()
    result = []
    for domain, title in matches:
        key = f"({domain}) {title.strip()}"
        if key not in seen:
            seen.add(key)
            result.append(key)
    return result


def run_validation(
    supabase: Any,
    *,
    queries: tuple[str, ...] | None = None,
    on_progress: Any = None,
) -> list[ValidationResult]:
    """검증 query 순차 자동 실행.

    Args:
        supabase: chatbot.ask 의 supabase client.
        queries: 검증 query list. None 시 DB 의 active queries 자동 조회
                 (DB 실패 시 DEFAULT_VALIDATION_QUERIES fallback).
        on_progress: callback(idx, total, query_text) — progress bar 용.

    Returns:
        list[ValidationResult] — 모든 query 의 결과 (error 포함).
    """
    from .chatbot import ask

    if queries is None:
        # PR-DB-Based-Validation-Queries: DB 의 active queries 우선
        qs = fetch_active_queries(supabase)
    else:
        qs = queries
    results: list[ValidationResult] = []
    total = len(qs)

    for idx, query in enumerate(qs, 1):
        if on_progress:
            try:
                on_progress(idx, total, query)
            except Exception:
                pass

        start = time.time()
        try:
            ans = ask(supabase, question=query, category=None)
            elapsed = time.time() - start

            results.append(
                ValidationResult(
                    idx=idx,
                    query=query,
                    answer_text=ans.text,
                    answer_chars=len(ans.text or ""),
                    elapsed_seconds=elapsed,
                    is_critical=bool(ans.is_critical),
                    confidence=ans.confidence,
                    matched_doc_count=len(ans.contexts or []),
                    cited_docs=_extract_cited_docs(ans.text or ""),
                    button_type=_classify_button(
                        ans.text or "", bool(ans.is_critical), ans.confidence
                    ),
                )
            )
        except Exception as e:
            elapsed = time.time() - start
            print(
                f"[validation] Q{idx} error: {e}",
                file=sys.stderr,
                flush=True,
            )
            results.append(
                ValidationResult(
                    idx=idx,
                    query=query,
                    answer_text="",
                    answer_chars=0,
                    elapsed_seconds=elapsed,
                    is_critical=False,
                    confidence="",
                    matched_doc_count=0,
                    cited_docs=[],
                    button_type="(error)",
                    error=str(e)[:200],
                )
            )

    return results


def results_to_markdown(results: list[ValidationResult]) -> str:
    """결과 리스트 → Markdown 전체 export."""
    lines = [
        "# DF COMPASS 검증 결과",
        "",
        f"Total: {len(results)} queries",
        "",
        "## 종합 표",
        "",
        "| # | Query | Chars | Elapsed | Critical | Conf | Docs | Button |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in results:
        lines.append(
            f"| {r.idx} | {r.query[:30]} | {r.answer_chars} | "
            f"{r.elapsed_seconds:.1f}s | {'✅' if r.is_critical else ''} | "
            f"{r.confidence} | {r.matched_doc_count} | {r.button_type} |"
        )
    lines.append("")
    lines.append("---")
    lines.append("")
    for r in results:
        lines.append(r.to_markdown())
        lines.append("")
    return "\n".join(lines)
