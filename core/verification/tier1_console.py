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

# Harness 안정화 (제품 파이프라인 무관 — 콘솔 신뢰성용):
# transient(임베딩 rate-limit/RPC) 검색 실패가 가짜 FAIL 로 둔갑하던 것 방지.
_RETRIEVAL_MAX_ATTEMPTS = 3      # hybrid_search transient 자동 재시도
_RETRIEVAL_RETRY_SLEEP = 1.5     # 재시도 전 대기(초)
_INTER_CASE_SLEEP = 0.25         # 케이스 간 대기(초) — rate 압박 완화 (0=비활성)


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


def _route_only(question: str, supabase: Any, *, need_category: bool, need_retrieval: bool = False) -> dict:
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

    # PR-OOS-Gate: out_of_scope 면 실제 override 게이트까지 태워 라이브 정합
    if classifier == "out_of_scope":
        try:
            from core.oos_router import gated_oos_decision
            if not gated_oos_decision(supabase, question):
                classifier = "standard"
        except Exception:
            pass

    nodes = set(nexus_classify_to_incident_nodes(question or ""))
    try:
        rew = rewrite_query_for_retrieval(question or "")
        if rew:
            nodes |= set(nexus_classify_to_incident_nodes(rew))
    except Exception:
        pass
    user_nodes = sorted(nodes)

    category = ""
    retrieved_docs: list[str] = []
    route_error: Optional[str] = None
    if need_category or need_retrieval:
        from core.retriever import hybrid_search
        from core.personality import category_visual
        contexts = None
        _last_exc: Optional[Exception] = None
        for _attempt in range(_RETRIEVAL_MAX_ATTEMPTS):  # transient 자동 재시도
            try:
                contexts = hybrid_search(
                    supabase, question=question, raw_question=question,
                    categories=None, top_k=None,
                ) or []
                _last_exc = None
                break
            except Exception as _e:  # noqa: BLE001 — transient 재시도 대상
                _last_exc = _e
                if _attempt < _RETRIEVAL_MAX_ATTEMPTS - 1:
                    time.sleep(_RETRIEVAL_RETRY_SLEEP)
        if _last_exc is not None:
            # 재시도 끝에도 실패 → 조용히 삼키지 않고 ERROR 로 표면화
            route_error = (
                f"retrieval failed x{_RETRIEVAL_MAX_ATTEMPTS}: "
                f"{type(_last_exc).__name__}: {_last_exc}"
            )
        else:
            for c in (contexts or []):
                if isinstance(c, dict):
                    c["_user_incident_nodes"] = list(user_nodes)
            retrieved_docs = sorted({
                str(c.get("doc_title") or "") for c in (contexts or [])
                if isinstance(c, dict) and c.get("doc_title")
            })
            if need_category:
                try:
                    _icon, _color, category = category_visual(contexts or [])
                except Exception as _e:  # noqa: BLE001
                    route_error = f"category_visual failed: {type(_e).__name__}: {_e}"

    return {
        "category": category, "classifier": classifier,
        "incident_nodes": user_nodes, "retrieved_docs": retrieved_docs,
        "error": route_error,
    }


def _check_case(case: dict, routed: dict) -> list[str]:
    """기대값 대조 -> 실패 사유 list (빈 list = PASS)."""
    failures: list[str] = []
    exp = case.get("expect") or {}
    if "classifier" in exp and routed["classifier"] != exp["classifier"]:
        failures.append(f"classifier 기대={exp['classifier']} 실제={routed['classifier'] or '_'}")
    if "classifier_not" in exp and routed["classifier"] == exp["classifier_not"]:
        failures.append(f"classifier 가 {exp['classifier_not']} 이면 안 됨 (실제={routed['classifier'] or '_'})")
    if "category" in exp and routed["category"] != exp["category"]:
        failures.append(f"category 기대={exp['category']} 실제={routed['category'] or '_'}")
    missing = [n for n in (exp.get("incident_nodes_include") or []) if n not in routed["incident_nodes"]]
    if missing:
        failures.append(f"노드 누락={missing} (실제={routed['incident_nodes']})")
    leaked = [n for n in (exp.get("incident_nodes_exclude") or []) if n in routed["incident_nodes"]]
    if leaked:
        failures.append(f"노드 오염={leaked} (실제={routed['incident_nodes']})")
    # Tier-2 grounding: 기대 문서가 검색 top-k(contexts)에 실재하는지 (synthesis 불필요).
    # 라우팅은 PASS인데 정답 사규 미검색으로 답이 틀리던 공백을 메움 (택시→시내교통비
    # 사례). substring 매칭 — 제목 표기 차이에 관대.
    exp_docs = exp.get("expect_retrieved_doc")
    if exp_docs:
        if isinstance(exp_docs, str):
            exp_docs = [exp_docs]
        got = routed.get("retrieved_docs") or []
        for _d in exp_docs:
            if not any(_d in g for g in got):
                failures.append(f"기대 문서 미검색='{_d}' (실제 top-k={got[:8]})")
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
            _exp = case.get("expect") or {}
            need_cat = "category" in _exp
            need_ret = "expect_retrieved_doc" in _exp
            routed = _route_only(case["query"], supabase, need_category=need_cat, need_retrieval=need_ret)
            if routed.get("error"):
                # transient 등 검색 실패 → 가짜 FAIL 로 둔갑시키지 않고 ERROR 로 분리 표시
                results.append(CaseResult(
                    case_id=case.get("id", f"case_{i}"), query=case["query"],
                    passed=False, error=routed["error"],
                    failures=[f"\u26a0\ufe0f ERROR(검색 실패·재시도 소진): {routed['error']}"],
                    actual_category=routed.get("category", ""),
                    actual_classifier=routed.get("classifier", ""),
                    actual_nodes=routed.get("incident_nodes", []),
                    elapsed=time.perf_counter() - t0,
                ))
            else:
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
        if _INTER_CASE_SLEEP > 0:
            time.sleep(_INTER_CASE_SLEEP)
    passed = sum(1 for r in results if r.passed)
    return {"total": total, "passed": passed, "failed": total - passed, "results": results}
