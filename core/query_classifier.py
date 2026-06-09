"""PR-Phase-17.1: Query Classifier — Modular RAG 의 첫 모듈 (Shadow Mode).

4-way query 분류 (simple_faq / standard / complex / critical) — Adaptive Path 기반.

안전 도입:
- ENABLE_QUERY_CLASSIFIER_LOGGING 기본 false → 머지 시 ZERO regression
  (기본값에서는 ask/ask_stream 의 shadow 호출 자체가 실행 안 됨).
- ENABLE_QUERY_CLASSIFIER_ACTION 기본 false → action 미적용, logging/측정 전용.
- 정확도 sim 은 pages/admin.py 의 "🧭 Classifier Sim" 탭에서 실 Claude 로 실행
  (live API test 는 admin 패널 버튼으로 embed — 운영 원칙 정합).

모델: Claude Haiku 4.5 (Anthropic SDK). 호출 패턴은 Critical Mode
(core/chatbot.py:_gen_claude) 와 동일 — instruction following 강 → 1단어 출력 일관.
"""
from __future__ import annotations

import sys
import time
from typing import Any, Literal

from .config import get_secret, settings

ClassificationResult = Literal["simple_faq", "standard", "complex", "critical", "out_of_scope"]
_VALID: tuple[str, ...] = ("simple_faq", "standard", "complex", "critical", "out_of_scope")

ENABLE_QUERY_CLASSIFIER_LOGGING: bool = (
    get_secret("ENABLE_QUERY_CLASSIFIER_LOGGING", "false").lower() == "true"
)
ENABLE_QUERY_CLASSIFIER_ACTION: bool = (
    get_secret("ENABLE_QUERY_CLASSIFIER_ACTION", "false").lower() == "true"
)
CLASSIFIER_MODEL: str = get_secret("QUERY_CLASSIFIER_MODEL", "claude-haiku-4-5")

CLASSIFIER_PROMPT = """당신은 신세계디에프 사규 챗봇의 query 분류기입니다.
사용자 query 를 5 가지 카테고리 중 하나로 분류하세요:

1. simple_faq: 빈번하게 묻는 단순 안내 query (단일 답변 가능)
   예: "자진 신고", "외부 강의 강의료", "신고 방법 안내"
2. standard: 일반 사규/절차/방법의 단순 조회 query (정보 탐색 의도 — "어떻게 / 방법 / 절차").
   포괄적 사내 규정 위반의 보고·신고 절차도 여기 포함 (특정 강력범죄 미명시).
   예: "성희롱 신고 방법", "환경 위반 신고", "공정거래 위반", "협력회사 부당행위", "위반사실 보고"
   ★ 재무/감사/총무 사규 어휘 (반드시 standard, OOS 금지):
       "법인카드 사용/한도/규정", "출장비 정산/지침", "비용 처리/한도",
       "경비 신청/처리", "감사 절차/대응/보고", "계약 체결/검토",
       "거래처 등록", "구매 승인" — 재무·감사·총무 부서의 사규 조회.
3. complex: 4개 이상 사규 또는 다중 도메인 인용이 필요한 복합 query (단일 사규로 답변 불가)
   예: "성희롱 + 직장 내 괴롭힘 + 보복 금지 + 신고자 보호",
       "비위사실 자진 신고 + 7일 이내 + 징계 감경 + SHRS 경로",
       "외부 강의 강의료 + 클린뱅크 이관 + 신고 절차"
4. critical: 실제 사고/범죄/위반 사실의 '발생' 또는 '발견'을 보고·신고·인지하는 query.
   인명 위협·형사 범죄 등 즉시 핫라인 가동 + 24시간 內 SRMS 등록이 필요한 사안.
   ★ 초고위험 예외: 정보유출 / 중대재해 / 강력범죄 / 보안 사고 는 '절차·방법'을
     묻더라도 무조건 critical (핫라인 즉시 가동 + 법정 시한 — 예: 개인정보 72시간).
   Positive 예: "폭행 사건 보고", "중대재해 발생", "횡령사실 신고", "성희롱 피해",
       "직장 내 폭행", "비위사실 발견", "범죄사실 인지",
       "정보유출 신고 절차"(절차여도 초고위험 → critical)
   Negative (→ standard 로 분류): "성희롱 신고 방법"(방법 안내),
       "환경 위반 신고"(절차 조회), "공정거래 위반"(사규 조회),
       "위반사실 보고"(포괄적 위반 보고)
5. out_of_scope: 사규/윤리/컴플라이언스 범위를 벗어난 query — 검색·생성을
   건너뛰고 담당 부서로 라우팅. IT 시스템 장애, 총무 시설 예약, 개인 급여·
   인사기록, 잡담/테스트, 타사 사규 등 단순 행정·외부 문의.
   Positive 예: "VPN 접속 장애"(IT), "내 연봉 알려줘"(개인), "롯데면세점 사규"(타사),
       "오늘 날씨"(일반상식), "안녕"/"hello"/"테스트"(잡담), "회의실 예약"(총무)
   ★★ 절대 금지 (사용자 안전 — Critical False Positive=0):
     - 신고/사고/위반/보고/제보/피해/발견/인지/유출/폭행/성희롱/횡령/범죄/
       중대재해/응급/부상/사망/괴롭힘/사건/협박/감금 중 하나라도 포함 →
       OOS 절대 금지 (critical 또는 standard 우선).
     - 회사 사규/규정/지침/윤리에 조금이라도 걸칠 가능성이 있으면 standard
       우선 (보수적 default — 애매할 때 OOS 로 빠지지 말 것).
     - 회의실/PC/VPN 도 신고·사고 맥락이면 즉시 critical/standard 재판정
       (예: "회의실에서 폭행 발생" = critical, "VPN 통한 정보유출" = critical).
     - 재무/감사/총무 사규 어휘 ("법인카드 사용 규정", "출장비 정산", "비용
       처리 지침", "경비 신청", "감사 절차", "계약 체결", "거래처 등록" 등)
       포함 → OOS 금지, standard 우선.
   ⭐ 핵심 판별 (OOS vs standard):
     [OOS]      = 사규에 명시되지 않은 단순 행동 (회의실 예약·VPN 접속·
                  노트북 교체·주차 등록·구내식당·연봉 조회·잡담·타사 사규).
     [standard] = 사규 어휘 (~사용 규정/정산 지침/처리 방법/한도/체결/등록 등이
                  재무·감사·총무 등 회사 사규에 명시된 사항).
     애매하면 standard 우선 (보수적 default).

규칙:
- 정확히 한 단어로만 응답: simple_faq / standard / complex / critical / out_of_scope
- 다른 설명 금지

Query: {question}

Respond with ONE word only from these options: simple_faq, standard, complex, critical, out_of_scope. Do not add any explanation."""


def classify_query(question: str, supabase: Any = None) -> dict:
    """Query 를 5-way 분류.

    Returns: {"category": str, "elapsed": float, "model": str}
    호출 실패 시 category="standard" (안전 default) — 절대 raise 하지 않음
    (shadow mode 에서 본 흐름을 깨지 않기 위함).

    PR-Phase-19.2.3: supabase 인자 (Optional) 추가. 전달 시 사규 동의어 사전
    으로 query 를 확장한 후 Haiku 에 전달 → 사내 약어("통물","FBS","SHRS"
    등) 도 OOS 가 아닌 standard/critical 로 정분류. supabase=None 시 기존
    동작 (회귀 0). ENABLE_SYNONYM_EXPANSION=false 시 expand 가 input 그대로
    반환 (이중 안전).

    Claude Haiku 4.5 (Anthropic SDK) — Critical Mode(core/chatbot.py:_gen_claude)
    와 동일 패턴. ANTHROPIC_API_KEY 재사용 (추가 secret 불필요).
    """
    start = time.perf_counter()
    category: str = "standard"

    # PR-Phase-19.2.3: 분류 전 사규 동의어 확장 (silent fallback).
    classify_question = question or ""
    if supabase is not None and classify_question:
        try:
            from .synonym_expander import expand_query_with_synonyms
            expanded, _subs = expand_query_with_synonyms(
                classify_question, supabase,
            )
            if _subs:
                classify_question = expanded
                print(
                    f"[SYN_DIAG:classifier:EXPANDED] "
                    f"orig={(question or '')[:50]!r} "
                    f"expanded={classify_question[:80]!r} "
                    f"subs={_subs}",
                    file=sys.stderr, flush=True,
                )
        except Exception as _exp_e:
            print(
                f"[SYN_DIAG:classifier:EXPAND_FAIL] "
                f"err={type(_exp_e).__name__}: {_exp_e}",
                file=sys.stderr, flush=True,
            )
            # silent fallback — original question 사용 (회귀 안전)

    try:
        import anthropic

        s = settings()
        cli = anthropic.Anthropic(
            api_key=s.anthropic_api_key, timeout=30.0, max_retries=0
        )
        res = cli.messages.create(
            model=CLASSIFIER_MODEL,
            max_tokens=50,
            temperature=0.0,
            messages=[{
                "role": "user",
                "content": CLASSIFIER_PROMPT.format(question=classify_question),
            }],
        )
        raw = ""
        for block in res.content:
            if getattr(block, "type", None) == "text":
                raw += getattr(block, "text", "") or ""
        raw = raw.strip().lower()
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
    return {"category": category, "elapsed": elapsed, "model": CLASSIFIER_MODEL}


# ── 자동화 sim 데이터셋 (정답 = prompt few-shot 예시 기반 추정) ──
SIM_DATASET: dict[str, list[str]] = {
    "simple_faq": [
        "자진 신고",
        "외부 강의 강의료",
        "휴가 신청 방법",
        "신고 방법 안내",
    ],
    "standard": [
        "성희롱 신고 방법",
        "환경 위반 신고",
        "공정거래 위반",
        "협력회사 부당행위",
        "위반사실 보고",
        "출장비 정산",
        "법인카드 사용",
        "비용 처리 지침",
        "경비 신청",
        "감사 절차",
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
        "정보유출 신고 절차",
        "범죄사실 인지",
    ],
    "out_of_scope": [
        "VPN 접속 장애",
        "내 연봉 알려줘",
        "롯데면세점 사규",
        "오늘 날씨",
        "안녕",
        "회의실 예약",
    ],
}


def run_classifier_sim() -> dict:
    """SIM_DATASET 일괄 분류 + per-category 정확도 + 오분류 list.

    실 Claude 호출 (classify_query). pages/admin.py 의 "🧭 Classifier Sim"
    탭에서 사용. 환경에 ANTHROPIC_API_KEY 가 있어야 의미 있는 결과가 나온다
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
