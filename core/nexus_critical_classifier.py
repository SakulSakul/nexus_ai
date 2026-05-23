"""Critical Mode 의 LLM-based classifier (Claude Opus 4.7 Self-Consistency).

PR-Critical-Mode-LLM-Expansion:
- Keyword 매칭 fallback 으로 Claude Opus 4.7 호출.
- Multi-sample (3 calls) + majority vote 으로 안정성 ↑.
- detect rate 14.5% → 55-65% 기대.
- 비용: +9원 × 3 = +27원/critical-suspect query.

Trigger 조건:
- Keyword miss + critical-suspect 의심 시만 LLM 호출.
- 의심: 위협/협박/유출/횡령/괴롭힘 등 의 의미적 카테고리.
"""
from __future__ import annotations

import re
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass


# Critical-suspect 의심 패턴 (regex).
# 이 중 하나라도 매칭되면 LLM classifier 호출.
_SUSPECT_PATTERNS = [
    # Threat (위협, 협박, 보복)
    re.compile(r"(위협|협박|보복|가해|위해|폭언|폭행|학대|모욕|괴롭|갑질)", re.I),
    # Cyber (정보 유출, 해킹)
    re.compile(r"(유출|해킹|악성|침해|개인정보|자료.*외부|비밀번호.*공유)", re.I),
    # Fraud (횡령, 배임, 부정행위)
    re.compile(r"(횡령|배임|사기|부정|착복|공금|뇌물|선물.*받|향응|접대)", re.I),
    # Workplace (괴롭힘, 부당지시)
    re.compile(r"(부당.*지시|차별|배제|소외|왕따|괴롭|폭언|폭행)", re.I),
    # Financial (대출 강요, 금전 요구)
    re.compile(r"(대출.*강요|돈.*빌려|차용|금전.*요구|사적.*거래)", re.I),
    # Safety 자연어 변형
    re.compile(r"(화재|폭발|가스|연기|불.*났|감전|사람.*다쳤|응급|119)", re.I),
    # Harassment 자연어 변형
    re.compile(r"(성희롱|성추행|성폭행|불쾌.*발언|신체.*접촉|음란)", re.I),
]


@dataclass(frozen=True)
class LLMClassifierResult:
    """LLM classifier 결과.

    is_critical: 트리거 여부.
    kind: 'safety' / 'harassment' (사쿨 시스템 의 기존 enum 유지).
    confidence: 0.0-1.0 (Multi-sample 의 majority 비율).
    rationale: 분류 이유 (debug + admin 용).
    samples: 3개 sample 결과 (debug).
    """
    is_critical: bool
    kind: str | None
    confidence: float
    rationale: str
    samples: list[dict]


_CLASSIFIER_SYSTEM_PROMPT = """당신은 신세계 듀티프리의 컴플라이언스 챗봇 보조 분류기입니다.

사용자 query 가 critical 트리거 영역인지 분류합니다:

**Critical 정의**:
1. safety: 화재/폭발/가스누출/감전/추락/식중독 등 즉시 응급 필요
2. harassment: 성희롱/괴롭힘/협박/해킹/횡령/뇌물/유출/부정행위 등 신고 필요

**Critical 아님**:
- 단순 정보 조회 (휴가 절차, 출장비 등)
- 일반 사규 질문 (선물 한도, 회식 비용 등 보통 수준)

**출력 형식 (JSON만, 다른 설명 X)**:
{"is_critical": true|false, "kind": "safety"|"harassment"|null, "rationale": "한 문장 이유"}

예시:
- "성희롱 당했어요" → {"is_critical": true, "kind": "harassment", "rationale": "성희롱은 즉시 신고 필요한 critical 영역"}
- "휴가 며칠 남았어요?" → {"is_critical": false, "kind": null, "rationale": "단순 HR 정보 조회"}
- "동료가 회사 정보를 빼돌리는 것 같아요" → {"is_critical": true, "kind": "harassment", "rationale": "정보유출 의심은 신고 필요"}
"""


def _is_suspect(question: str) -> bool:
    """Critical-suspect 의심 여부 (정규식)."""
    if not question:
        return False
    return any(p.search(question) for p in _SUSPECT_PATTERNS)


def _call_classifier_once(question: str) -> dict | None:
    """Claude Opus 4.7 으로 1회 분류 호출.

    Returns: {"is_critical": bool, "kind": str|None, "rationale": str}
             또는 실패 시 None.
    """
    try:
        from .chatbot import _gen_claude
        text, _, _ = _gen_claude(
            system=_CLASSIFIER_SYSTEM_PROMPT,
            user=f"사용자 query: {question}",
            include_thinking=False,
        )
        import json
        # extract JSON (LLM 가 추가 설명 줄 수 있음 — 첫 { ~ 마지막 } 추출)
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end < 0 or end < start:
            return None
        parsed = json.loads(text[start:end+1])
        if "is_critical" not in parsed:
            return None
        return {
            "is_critical": bool(parsed.get("is_critical", False)),
            "kind": parsed.get("kind") if parsed.get("kind") in ("safety", "harassment") else None,
            "rationale": str(parsed.get("rationale", ""))[:200],
        }
    except Exception as e:
        print(f"[critical_classifier] LLM call failed: {e}", file=sys.stderr, flush=True)
        return None


def classify_with_llm(question: str) -> LLMClassifierResult | None:
    """Claude Opus 4.7 × 3 Self-Consistency 분류.

    Returns: LLMClassifierResult — Multi-sample majority vote 결과.
             또는 None (suspect 아님 OR LLM 호출 모두 실패).
    """
    if not _is_suspect(question):
        return None  # suspect 아니면 LLM 호출 skip

    # PR-Critical-Mode-Parallel: 3 calls 를 parallel 실행 (sequential 9-15초 → 3-5초)
    samples: list[dict] = []
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = [
            executor.submit(_call_classifier_once, question)
            for _ in range(3)
        ]
        for f in futures:
            try:
                result = f.result(timeout=15)
                if result is not None:
                    samples.append(result)
            except Exception as e:
                print(
                    f"[critical_classifier] sample failed: "
                    f"{type(e).__name__}: {e}",
                    file=sys.stderr, flush=True,
                )
                continue

    if not samples:
        return None  # 모든 sample 실패

    # Majority vote: is_critical 의 다수결
    critical_votes = sum(1 for s in samples if s["is_critical"])
    is_critical = critical_votes >= 2  # 3 중 2+ 표

    # kind: critical 인 sample 들의 kind 다수결
    kind = None
    rationale = ""
    if is_critical:
        kinds = [s["kind"] for s in samples if s["is_critical"] and s["kind"]]
        if kinds:
            kind = Counter(kinds).most_common(1)[0][0]
        # rationale: 첫 critical sample 의 rationale
        for s in samples:
            if s["is_critical"]:
                rationale = s["rationale"]
                break

    confidence = critical_votes / len(samples) if samples else 0.0

    print(
        f"[critical_classifier] samples={len(samples)} critical_votes={critical_votes}/{len(samples)} "
        f"is_critical={is_critical} kind={kind} confidence={confidence:.2f}",
        file=sys.stderr, flush=True,
    )

    return LLMClassifierResult(
        is_critical=is_critical,
        kind=kind,
        confidence=confidence,
        rationale=rationale,
        samples=samples,
    )
