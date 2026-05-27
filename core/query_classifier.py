"""PR-Phase-17.1: Query Classifier — Modular RAG 의 첫 모듈 (Shadow Mode).

4-way query 분류 (simple_faq / standard / complex / critical) — Adaptive Path 기반.

안전 도입:
- ENABLE_QUERY_CLASSIFIER_LOGGING 기본 false → 머지 시 ZERO regression
  (기본값에서는 ask/ask_stream 의 shadow 호출 자체가 실행 안 됨).
- ENABLE_QUERY_CLASSIFIER_ACTION 기본 false → action 미적용, logging/측정 전용.
- 정확도 sim 은 pages/admin.py 의 "🧭 Classifier Sim" 탭에서 실 Gemini 로 실행
  (live API test 는 admin 패널 버튼으로 embed — 운영 원칙 정합).

Gemini 호출 패턴은 core/nexus_query_rewriter.py 와 동일 (google-genai Client).
"""
from __future__ import annotations

import sys
import time
from typing import Literal

from .config import get_secret, settings

ClassificationResult = Literal["simple_faq", "standard", "complex", "critical"]
_VALID: tuple[str, ...] = ("simple_faq", "standard", "complex", "critical")

ENABLE_QUERY_CLASSIFIER_LOGGING: bool = (
    get_secret("ENABLE_QUERY_CLASSIFIER_LOGGING", "false").lower() == "true"
)
ENABLE_QUERY_CLASSIFIER_ACTION: bool = (
    get_secret("ENABLE_QUERY_CLASSIFIER_ACTION", "false").lower() == "true"
)
_CLASSIFIER_MODEL: str = get_secret("QUERY_CLASSIFIER_MODEL", "gemini-2.5-flash-lite")

CLASSIFIER_PROMPT = """당신은 신세계디에프 사규 챗봇의 query 분류기입니다.
사용자 query 를 4 가지 카테고리 중 하나로 분류하세요:

1. simple_faq: 빈번하게 묻는 단순 안내 query
   예: "자진 신고", "외부 강의 강의료", "휴가 신청 방법", "회의실 예약"
2. standard: 일반적인 사규 조회 query
   예: "성희롱 신고 방법", "환경 위반 신고", "공정거래 위반"
3. complex: 4개 이상 사규 인용이 필요한 복합 query
   예: "외부 강의 강의료 처리 + 클린뱅크 이관 + 신고 절차"
4. critical: 비위/사고/심각 사안 query
   예: "폭행 사건 보고", "중대재해 발생", "횡령사실 신고", "성희롱 피해"

규칙:
- 정확히 한 단어로만 응답: simple_faq / standard / complex / critical
- 다른 설명 금지

Query: {question}"""


def classify_query(question: str) -> dict:
    """Query 를 4-way 분류.

    Returns: {"category": str, "elapsed": float, "model": str}
    Gemini 실패 시 category="standard" (안전 default) — 절대 raise 하지 않음
    (shadow mode 에서 본 흐름을 깨지 않기 위함).
    """
    start = time.perf_counter()
    category: str = "standard"
    try:
        from google import genai

        s = settings()
        cli = genai.Client(api_key=s.gemini_api_key)
        res = cli.models.generate_content(
            model=_CLASSIFIER_MODEL,
            contents=CLASSIFIER_PROMPT.format(question=question or ""),
        )
        raw = (getattr(res, "text", "") or "").strip().lower()
        for v in _VALID:
            if v in raw:
                category = v
                break
    except Exception as e:
        print(
            f"[query_classifier] FAILED: {type(e).__name__}: {e}",
            file=sys.stderr, flush=True,
        )
    elapsed = time.perf_counter() - start
    if ENABLE_QUERY_CLASSIFIER_LOGGING:
        print(
            f"[query_classifier] q={(question or '')[:50]!r} "
            f"category={category} elapsed={elapsed:.2f}s",
            file=sys.stderr, flush=True,
        )
    return {"category": category, "elapsed": elapsed, "model": _CLASSIFIER_MODEL}


# ── 자동화 sim 데이터셋 (정답 = prompt few-shot 예시 기반 추정) ──
SIM_DATASET: dict[str, list[str]] = {
    "simple_faq": [
        "자진 신고",
        "외부 강의 강의료",
        "휴가 신청 방법",
        "신고 방법 안내",
        "회의실 예약",
    ],
    "standard": [
        "성희롱 신고 방법",
        "환경 위반 신고",
        "공정거래 위반",
        "정보유출 신고 절차",
        "협력회사 부당행위",
        "범죄사실 인지",
        "위반사실 보고",
    ],
    "complex": [
        "외부 강의 강의료 처리 + 클린뱅크 이관 + 신고 절차",
        "성희롱 + 직장 내 괴롭힘 + 보복 금지 + 신고자 보호",
        "비위사실 자진 신고 + 7일 이내 + 징계 감경 + SHRS 경로",
    ],
    "critical": [
        "폭행 사건 보고",
        "중대재해 발생",
        "횡령사실 신고",
        "성희롱 피해",
        "직장 내 폭행",
        "비위사실 발견",
    ],
}


def run_classifier_sim() -> dict:
    """SIM_DATASET 일괄 분류 + per-category 정확도 + 오분류 list.

    실 Gemini 호출 (classify_query). pages/admin.py 의 "🧭 Classifier Sim"
    탭에서 사용. 환경에 GEMINI_API_KEY 가 있어야 의미 있는 결과가 나온다
    (없으면 모든 결과가 안전 default 'standard' 로 떨어짐).
    """
    per_category: dict = {}
    misclassified: list = []
    total = 0
    total_correct = 0
    total_elapsed = 0.0
    for expected, queries in SIM_DATASET.items():
        correct = 0
        for q in queries:
            r = classify_query(q)
            total += 1
            total_elapsed += r["elapsed"]
            if r["category"] == expected:
                correct += 1
                total_correct += 1
            else:
                misclassified.append(
                    {"query": q, "expected": expected, "actual": r["category"]}
                )
        per_category[expected] = {"correct": correct, "total": len(queries)}
    return {
        "per_category": per_category,
        "overall_correct": total_correct,
        "overall_total": total,
        "accuracy": (total_correct / total) if total else 0.0,
        "avg_elapsed": (total_elapsed / total) if total else 0.0,
        "misclassified": misclassified,
    }
