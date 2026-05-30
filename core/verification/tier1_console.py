"""Tier-1 회귀 콘솔 runner — 라우팅/배지/classifier 고속 검증 (LLM 합성 없음).

regression_cases.json 케이스를 query 당 classify_query + incident_nodes (+ 필요 시
retrieval→category_visual) 까지만 실행해 기대값과 대조. Gemini 합성 미실행 →
query 당 수 초, 비용 최소. Streamlit 비의존 (admin 탭 + 향후 CLI/CI 공용).
무거운 import 는 함수 내부 lazy — 모듈 import 는 stdlib 만 (순환 import 회피).
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

FIXTURE_PATH = (
    Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "regression_cases.json"
)


@dataclass
class CaseResult:
    case_id: str
    query: str
    passed: bool
    failures: list[str] = field(default_factory=list)
    actual_category: str = ""
    actual_classifier: str = ""
    actual_nodes: list[str] = field(default_factory=list)
    elapsed: float = 0.0
    error: Optional[str] = None


def load_cases(path: Path | None = None) -> list[dict]:
    """fixture JSON -> cases list. 파일/형식 이상 시 []."""
    try:
        data = json.loads((path or FIXTURE_PATH).read_text(encoding="utf-8"))
        return [c for c in (data.get("cases") or []) if c.get("query")]
    except Exception:
        return []


def _route_only(question: str, supabase: Any, *, need_category: bool) -> dict:
    """ask() 의 합성 직전 상태만 재현 (Gemini 미실행).
    classifier + incident_nodes 는 항상, category 는 need_category 일 때만 검색 실행.
    """
    from core.query_classifier import classify_query
    from core.nexus_query_rewriter import (
        nexus_classify_to_incident_nodes, rewrite_query_for_retrieval,
    )

    try:
        classifier = (classify_query(question, supabase=supabase) or {}).get("category", "")
    except Exception:
        classifier = ""

    nodes = set(nexus_classify_to_incident_nodes(question or ""))
    try:
        rew = rewrite_query_for_retrieval(question or "")
        if rew:
            nodes |= set(nexus_classify_to_incident_nodes(rew))
    except Exception:
        pass
    user_nodes = sorted(nodes)

    category = ""
    if need_category:
        try:
            from core.retriever import hybrid_search
            from core.personality import category_visual
            contexts = hybrid_search(
                supabase, question=question, raw_question=question,
                categories=None, top_k=None,
            ) or []
            for c in contexts:
                if isinstance(c, dict):
                    c["_user_incident_nodes"] = list(user_nodes)
            _icon, _color, category = category_visual(contexts)
        except Exception:
            category = ""

    return {"category": category, "classifier": classifier, "incident_nodes": user_nodes}


def _check_case(case: dict, routed: dict) -> list[str]:
    """기대값 대조 -> 실패 사유 list (빈 list = PASS)."""
    failures: list[str] = []
    exp = case.get("expect") or {}
    if "classifier" in exp and routed["classifier"] != exp["classifier"]:
        failures.append(f"classifier 기대={exp['classifier']} 실제={routed['classifier'] or '_'}")
    if "category" in exp and routed["category"] != exp["category"]:
        failures.append(f"category 기대={exp['category']} 실제={routed['category'] or '_'}")
    missing = [n for n in (exp.get("incident_nodes_include") or []) if n not in routed["incident_nodes"]]
    if missing:
        failures.append(f"노드 누락={missing} (실제={routed['incident_nodes']})")
    leaked = [n for n in (exp.get("incident_nodes_exclude") or []) if n in routed["incident_nodes"]]
    if leaked:
        failures.append(f"노드 오염={leaked} (실제={routed['incident_nodes']})")
    return failures


def run_tier1(
    supabase: Any,
    cases: list[dict] | None = None,
    on_progress: Optional[Callable[[int, int, dict], None]] = None,
) -> dict:
    """Tier-1 일괄 실행. Returns {total, passed, failed, results:[CaseResult]}."""
    cases = cases if cases is not None else load_cases()
    results: list[CaseResult] = []
    total = len(cases)
    for i, case in enumerate(cases):
        if on_progress:
            try:
                on_progress(i, total, case)
            except Exception:
                pass
        t0 = time.perf_counter()
        try:
            need_cat = "category" in (case.get("expect") or {})
            routed = _route_only(case["query"], supabase, need_category=need_cat)
            failures = _check_case(case, routed)
            results.append(CaseResult(
                case_id=case.get("id", f"case_{i}"), query=case["query"],
                passed=(not failures), failures=failures,
                actual_category=routed["category"], actual_classifier=routed["classifier"],
                actual_nodes=routed["incident_nodes"], elapsed=time.perf_counter() - t0,
            ))
        except Exception as e:
            results.append(CaseResult(
                case_id=case.get("id", f"case_{i}"), query=case.get("query", ""),
                passed=False, error=f"{type(e).__name__}: {e}",
                elapsed=time.perf_counter() - t0,
            ))
    passed = sum(1 for r in results if r.passed)
    return {"total": total, "passed": passed, "failed": total - passed, "results": results}
