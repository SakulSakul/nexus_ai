"""DF COMPASS · Retrieval Eval Runner (PR-Q1).

사용법:
    python eval/run.py [--fixtures eval/fixtures.yaml] [--top-k 3]

각 fixture 의 question 으로 retrieval (core.retriever.hybrid_search) 만
호출 — LLM 호출은 안 함. 결과를 expected_sources 와 비교해 precision /
recall / pass-fail 산출. 추가로 best_score 분포를 출력해 confidence
threshold 튜닝 baseline 으로 활용.

환경변수:
    SUPABASE_URL, SUPABASE_KEY  — anon 키로 RPC 호출 가능 (RLS 적용된
                                  query_logs 와 별개로 nexus_chunks /
                                  nexus_hybrid_search 는 anon 허용 가정).
    GEMINI_API_KEY              — embed_one 호출용.

출력:
    - 콘솔: per-fixture id · category · P · R · best_score · pass/fail
    - 파일: eval/results/<timestamp>.json (전체 metric + per-fixture detail)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

# 프로젝트 루트를 sys.path 에 추가 — `python eval/run.py` 직접 실행 호환.
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


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


def _load_yaml(path: Path) -> list[dict]:
    try:
        import yaml  # type: ignore
    except ImportError:
        print("ERROR: PyYAML 미설치 — `pip install pyyaml` 필요.", file=sys.stderr)
        sys.exit(2)
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or []
    if not isinstance(data, list):
        print(f"ERROR: {path} 는 list of fixture 형식이어야 합니다.",
              file=sys.stderr)
        sys.exit(2)
    return data


def _supabase():
    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_KEY", "")
    if not url or not key:
        # streamlit secrets 대체 경로
        try:
            from core.config import settings
            s = settings()
            url = url or s.supabase_url
            key = key or s.supabase_key
        except Exception:
            pass
    if not url or not key:
        print("ERROR: SUPABASE_URL / SUPABASE_KEY 미설정 — eval 불가.",
              file=sys.stderr)
        sys.exit(2)
    from supabase import create_client
    return create_client(url, key)


def _match_expected(hit_title: str, expected_substrings: list[str]) -> bool:
    """expected substring 중 하나라도 hit_title 에 포함되면 매치."""
    return any(s and s in (hit_title or "") for s in expected_substrings)


def _evaluate_one(
    sb: Any, fx: dict, *, top_k: int,
) -> FixtureResult:
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
        # hit > 0 이어도 RPC 가 fallback_to_common 으로 채웠을 수 있어
        # best_score 가 매우 낮으면 사실상 무의미한 hit. 일단 명세 그대로
        # "hit 0 또는 fallback" 으로 단순화 — best_score < threshold 도
        # 옵션이지만 RRF 분포 보고 튜닝.
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
    # recall = 매치된 expected 종류 수 / 전체 expected 종류 수
    recall = (len(matched_expected) / len(expected)) if expected else 0.0
    passed = recall >= 0.5  # expected 중 절반 이상 hit 면 pass (starter baseline)

    return FixtureResult(
        id=fid, category=category, question=question,
        expected=expected, hit_titles=hit_titles,
        precision=precision, recall=recall,
        best_score=best_score, hit_count=hit_count,
        passed=passed,
    )


def _print_table(results: list[FixtureResult]) -> None:
    header = f"{'id':<5} {'category':<14} {'P':>5} {'R':>5} {'best':>7} {'hit':>3} {'pass':>5}"
    print(header)
    print("-" * len(header))
    for r in results:
        flag = "✅" if r.passed else "❌"
        print(
            f"{r.id:<5} {r.category:<14} "
            f"{r.precision:>5.2f} {r.recall:>5.2f} "
            f"{r.best_score:>7.4f} {r.hit_count:>3} {flag:>5}"
        )
        if r.note:
            print(f"      └─ {r.note}")


def _summarize(results: list[FixtureResult], fixtures_path: str) -> RunSummary:
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


def main() -> int:
    ap = argparse.ArgumentParser(description="DF COMPASS retrieval eval runner")
    ap.add_argument("--fixtures", default=str(_ROOT / "eval" / "fixtures.yaml"))
    ap.add_argument("--top-k", type=int, default=3)
    ap.add_argument(
        "--no-write", action="store_true",
        help="결과 JSON 파일 생성 안 함 (CI dry-run 용).",
    )
    args = ap.parse_args()

    fixtures_path = Path(args.fixtures)
    if not fixtures_path.exists():
        print(f"ERROR: fixtures 파일 없음: {fixtures_path}", file=sys.stderr)
        return 2

    fixtures = _load_yaml(fixtures_path)
    sb = _supabase()

    print(f"Loaded {len(fixtures)} fixtures from {fixtures_path}")
    print(f"Running retrieval (top_k={args.top_k}) ...")
    print()

    results: list[FixtureResult] = []
    for fx in fixtures:
        r = _evaluate_one(sb, fx, top_k=args.top_k)
        results.append(r)

    _print_table(results)
    print()

    summary = _summarize(results, str(fixtures_path))
    print(f"Total {summary.total} | Passed {summary.passed} | Failed {summary.failed}")
    print(f"Avg precision: {summary.avg_precision:.3f}  "
          f"Avg recall: {summary.avg_recall:.3f}")
    print(f"best_score range: min {summary.score_min:.4f}  "
          f"max {summary.score_max:.4f}  avg {summary.score_avg:.4f}")
    print()
    print("By category:")
    for cat, m in summary.by_category.items():
        print(f"  {cat:<14} pass {m['passed']:>2}/{m['total']:<2}  "
              f"P {m['avg_precision']:.2f}  R {m['avg_recall']:.2f}  "
              f"score {m['score_avg']:.4f}")

    if not args.no_write:
        out_dir = _ROOT / "eval" / "results"
        out_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%dT%H%M%S")
        out_path = out_dir / f"{ts}.json"
        payload = asdict(summary)
        # FixtureResult dataclass 도 asdict 로 자동 직렬화됨
        with out_path.open("w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        print()
        print(f"Wrote {out_path}")

    return 0 if summary.failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
