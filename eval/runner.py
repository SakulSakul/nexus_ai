"""DF COMPASS · Retrieval Eval — 공유 runner.

eval/run.py (CLI) 와 pages/admin.py (브라우저) 양쪽에서 import.
fixture 로드 + per-fixture retrieval (LLM 호출 X) + 요약 + JSON 직렬화.

핵심 함수:
    load_fixtures(path) -> list[dict]
    supabase_client()   -> Supabase Client (env / streamlit secrets fallback)
    evaluate_one(sb, fx, top_k) -> FixtureResult
    summarize(results, fixtures_path) -> RunSummary
    run_all(fixtures_path, top_k, on_progress) -> RunSummary
    write_results_json(summary) -> Path
    summary_to_json_bytes(summary) -> bytes  # download_button 용
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

# 프로젝트 루트 (eval/ 의 부모) — 다른 모듈에서 import 시 sys.path 보정.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEFAULT_FIXTURES = ROOT / "eval" / "fixtures.yaml"
RESULTS_DIR = ROOT / "eval" / "results"


@dataclass
class FixtureResult:
    id: str
    category: str
    question: str
    expected: list[str]
    hit_titles: list[str]
    precision: float
    recall: float
    best_score: float
    hit_count: int
    passed: bool
    note: str = ""


@dataclass
class RunSummary:
    timestamp: str
    fixtures_path: str
    total: int = 0
    passed: int = 0
    failed: int = 0
    avg_precision: float = 0.0
    avg_recall: float = 0.0
    score_min: float = 0.0
    score_max: float = 0.0
    score_avg: float = 0.0
    by_category: dict[str, dict[str, float]] = field(default_factory=dict)
    fixtures: list[FixtureResult] = field(default_factory=list)


def load_fixtures(path: Path | str = DEFAULT_FIXTURES) -> list[dict]:
    try:
        import yaml  # type: ignore
    except ImportError as e:
        raise RuntimeError("PyYAML 미설치 — `pip install pyyaml` 필요.") from e
    p = Path(path)
    with p.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or []
    if not isinstance(data, list):
        raise ValueError(f"{p} 는 list of fixture 형식이어야 합니다.")
    return data


def supabase_client():
    """env / Streamlit secrets fallback. core.config.get_secret 경유."""
    from core.config import get_secret
    url = get_secret("SUPABASE_URL")
    key = get_secret("SUPABASE_KEY")
    if not url or not key:
        raise RuntimeError(
            "SUPABASE_URL / SUPABASE_KEY 미설정 — Streamlit secrets 또는 "
            "환경변수에 주입 필요."
        )
    from supabase import create_client
    return create_client(url, key)


def _match_expected(hit_title: str, expected_substrings: list[str]) -> bool:
    """expected substring 중 하나라도 hit_title 에 포함되면 매치."""
    return any(s and s in (hit_title or "") for s in expected_substrings)


def evaluate_one(sb: Any, fx: dict, *, top_k: int = 3) -> FixtureResult:
    """단일 fixture 평가 — retrieval (hybrid_search) 만 호출. LLM X."""
    from core.retriever import hybrid_search

    fid = str(fx.get("id", ""))
    question = str(fx.get("question", "")).strip()
    expected = list(fx.get("expected_sources") or [])
    category = str(fx.get("category", "general"))

    try:
        contexts = hybrid_search(
            sb, question=question, categories=None, top_k=top_k,
        )
    except Exception as e:
        return FixtureResult(
            id=fid, category=category, question=question,
            expected=expected, hit_titles=[],
            precision=0.0, recall=0.0,
            best_score=0.0, hit_count=0,
            passed=False, note=f"retrieval error: {e}",
        )

    hit_titles = [str(c.get("doc_title") or "") for c in contexts]
    scores = [float(c.get("score") or 0.0) for c in contexts]
    best_score = max(scores) if scores else 0.0
    hit_count = len(contexts)

    if category == "negative" or not expected:
        # negative case: hit 0건이면 pass.
        passed = (hit_count == 0)
        precision = 1.0 if passed else 0.0
        recall = 1.0
        return FixtureResult(
            id=fid, category=category, question=question,
            expected=expected, hit_titles=hit_titles,
            precision=precision, recall=recall,
            best_score=best_score, hit_count=hit_count,
            passed=passed,
            note="negative case — hit 0건 expected",
        )

    matched_titles = [t for t in hit_titles if _match_expected(t, expected)]
    matched_expected = [
        s for s in expected
        if any(s in t for t in hit_titles if t)
    ]

    precision = (len(matched_titles) / hit_count) if hit_count else 0.0
    recall = (len(matched_expected) / len(expected)) if expected else 0.0
    passed = recall >= 0.5  # starter baseline

    return FixtureResult(
        id=fid, category=category, question=question,
        expected=expected, hit_titles=hit_titles,
        precision=precision, recall=recall,
        best_score=best_score, hit_count=hit_count,
        passed=passed,
    )


def summarize(results: list[FixtureResult], fixtures_path: str) -> RunSummary:
    summary = RunSummary(
        timestamp=datetime.now().isoformat(),
        fixtures_path=fixtures_path,
        total=len(results),
        passed=sum(1 for r in results if r.passed),
    )
    summary.failed = summary.total - summary.passed

    if results:
        summary.avg_precision = sum(r.precision for r in results) / len(results)
        summary.avg_recall = sum(r.recall for r in results) / len(results)
        scores = [r.best_score for r in results]
        summary.score_min = min(scores)
        summary.score_max = max(scores)
        summary.score_avg = sum(scores) / len(scores)

    by_cat: dict[str, list[FixtureResult]] = {}
    for r in results:
        by_cat.setdefault(r.category, []).append(r)
    for cat, lst in by_cat.items():
        summary.by_category[cat] = {
            "total": len(lst),
            "passed": sum(1 for r in lst if r.passed),
            "avg_precision": sum(r.precision for r in lst) / len(lst),
            "avg_recall": sum(r.recall for r in lst) / len(lst),
            "score_avg": sum(r.best_score for r in lst) / len(lst),
        }

    summary.fixtures = results
    return summary


def run_all(
    *,
    fixtures_path: Path | str = DEFAULT_FIXTURES,
    top_k: int = 3,
    on_progress: Callable[[int, int, FixtureResult], None] | None = None,
) -> RunSummary:
    """Retrieval-only eval.

    on_progress: 선택. (idx_1based, total, last_result) 콜백 — Streamlit
                 progress 표시에 사용. 콜백 자체 예외는 silent (eval 흐름
                 무방해).
    """
    fixtures = load_fixtures(fixtures_path)
    sb = supabase_client()
    results: list[FixtureResult] = []
    total = len(fixtures)
    for i, fx in enumerate(fixtures, start=1):
        r = evaluate_one(sb, fx, top_k=top_k)
        results.append(r)
        if on_progress is not None:
            try:
                on_progress(i, total, r)
            except Exception:
                pass
    return summarize(results, str(fixtures_path))


def write_results_json(
    summary: RunSummary, *, results_dir: Path | str = RESULTS_DIR,
) -> Path:
    d = Path(results_dir)
    d.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%dT%H%M%S")
    out = d / f"{ts}.json"
    with out.open("w", encoding="utf-8") as f:
        json.dump(asdict(summary), f, ensure_ascii=False, indent=2)
    return out


def summary_to_json_bytes(summary: RunSummary) -> bytes:
    """Streamlit download_button 용. 파일 저장 X — 메모리 직렬화만."""
    return json.dumps(asdict(summary), ensure_ascii=False, indent=2).encode("utf-8")
