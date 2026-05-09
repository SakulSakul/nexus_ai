"""DF COMPASS · Retrieval Eval CLI (PR-Q1).

핵심 로직은 eval/runner.py. 본 모듈은 콘솔 진입점 (CI / 로컬 디버깅용).
브라우저 진입점은 pages/admin.py 의 🔍 Eval 탭 (PR-Q1.1).

사용법:
    python eval/run.py [--fixtures eval/fixtures.yaml] [--top-k 3] [--no-write]

환경변수:
    SUPABASE_URL, SUPABASE_KEY, GEMINI_API_KEY  (또는 Streamlit secrets)

출력:
    - 콘솔: per-fixture id · category · P · R · best_score · pass/fail
    - 파일: eval/results/<timestamp>.json (--no-write 로 비활성)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# 프로젝트 루트를 sys.path 에 추가 — `python eval/run.py` 직접 실행 호환.
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from eval.runner import (  # noqa: E402
    DEFAULT_FIXTURES,
    FixtureResult,
    RunSummary,
    run_all,
    write_results_json,
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


def _print_summary(summary: RunSummary) -> None:
    print()
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


def main() -> int:
    ap = argparse.ArgumentParser(description="DF COMPASS retrieval eval runner")
    ap.add_argument("--fixtures", default=str(DEFAULT_FIXTURES))
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

    print(f"Loaded fixtures from {fixtures_path}")
    print(f"Running retrieval (top_k={args.top_k}) ...")
    print()

    try:
        summary = run_all(fixtures_path=fixtures_path, top_k=args.top_k)
    except RuntimeError as e:
        # SUPABASE_URL/KEY 미설정, PyYAML 미설치 등 친화 에러.
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    except Exception as e:
        print(f"ERROR: {type(e).__name__}: {e}", file=sys.stderr)
        return 2

    _print_table(summary.fixtures)
    _print_summary(summary)

    if not args.no_write:
        out = write_results_json(summary)
        print()
        print(f"Wrote {out}")

    return 0 if summary.failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
