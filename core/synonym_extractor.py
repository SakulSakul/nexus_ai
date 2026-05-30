"""PR-Phase-19.2.1: 사규 chunk 의 동의어 자동 추출 (regex + Claude Haiku 4.5).

핵심 안전 원칙:
- ★★ 외부 LLM 학습 데이터 / 사규 외 지식 / 추론 확장 절대 금지.
- 사규 단락 내부에 명시적으로 정의된 동의어 쌍만 추출.
- 모든 추출 결과는 approved=false 로 저장 → admin 검수 후 승인.

선례 미러링: core/auto/cache.py (안전 흡수 패턴).
"""
from __future__ import annotations

import json
import re
from typing import Any


# ── Regex 패턴 (신뢰도 별) ───────────────────────────────────
# HIGH: 명시적 정의 관용구 — false positive 거의 없음.
HIGH_CONFIDENCE_PATTERNS: list[tuple[str, float]] = [
    # "X(이하 'Y' 라 한다)" / "X (이하 Y)" / "X (이하 Y라 함)"
    (
        r"([가-힣A-Za-z]{2,})\s*\(\s*이하\s*['\"]?\s*([가-힣A-Za-z]{2,})\s*['\"]?\s*"
        r"[이]?라\s*[한함]다?",
        0.95,
    ),
    # "X(이하 Y)" 단순형
    (r"([가-힣A-Za-z]{2,})\s*\(\s*이하\s+([가-힣A-Za-z]{2,})\s*\)", 0.90),
]

# LOW: false positive 많음 — confidence < 0.7 → 사쿨님 확정 임계 미만이라
# extract_regex_synonyms 의 기본 호출에서 자동 필터됨.
LOW_CONFIDENCE_PATTERNS: list[tuple[str, float]] = [
    # "X(Y)" 단순 괄호 (가짜 동의어 多)
    (r"([가-힣A-Za-z]{2,})\s*\(\s*([가-힣A-Za-z]{2,})\s*\)", 0.5),
    # "X 또는 Y" (OR 절·예시 절과 충돌)
    (r"([가-힣A-Za-z]{2,})\s*또는\s*([가-힣A-Za-z]{2,})", 0.5),
    # "X · Y" 가운데점
    (r"([가-힣A-Za-z]{2,})·([가-힣A-Za-z]{2,})", 0.5),
]

CONFIDENCE_THRESHOLD: float = 0.7   # 사쿨님 확정 (Option 7건 #4)


def extract_regex_synonyms(
    chunk_text: str, threshold: float = CONFIDENCE_THRESHOLD,
) -> list[dict]:
    """Regex 기반 동의어 추출 — threshold 이상 confidence 만.

    Returns: [{"primary_term", "synonym_term", "extraction_method", "confidence",
               "evidence_text"}].
    """
    if not chunk_text:
        return []
    results: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for pattern, conf in HIGH_CONFIDENCE_PATTERNS + LOW_CONFIDENCE_PATTERNS:
        if conf < threshold:
            continue
        try:
            for match in re.findall(pattern, chunk_text):
                if not isinstance(match, tuple) or len(match) < 2:
                    continue
                primary = (match[0] or "").strip()
                synonym = (match[1] or "").strip()
                if not primary or not synonym or primary == synonym:
                    continue
                key = (primary, synonym)
                if key in seen:
                    continue
                seen.add(key)
                results.append({
                    "primary_term":     primary,
                    "synonym_term":     synonym,
                    "extraction_method": "regex",
                    "confidence":        conf,
                    "evidence_text":     None,
                })
        except Exception:
            continue
    return results


_OPUS_PROMPT_TEMPLATE = """다음은 신세계디에프 사규의 한 단락이다. 이 단락 내부에 \
명시적으로 정의된 **1:1 동의어 쌍**만 추출하라.

★ 추출 대상 (✅ Approve):
1. 영문 약어 ↔ 한글 정의:
   - "B/L (선하증권)"             → B/L ↔ 선하증권
   - "FBS (Firm Banking System)"  → FBS ↔ Firm Banking System
2. 정식명 ↔ 약칭:
   - "외부감사 및 회계 등에 관한 규정(이하 '외감규정')"
     → 외부감사 및 회계 등에 관한 규정 ↔ 외감규정
3. 사규에 명시된 1:1 매핑:
   - "통합물류창고(센터): ... 이하 '통물' 이라 한다" → 통합물류창고(센터) ↔ 통물

★ 절대 금지 (❌ Reject):

1) **정의문 추출 금지**:
   - "X 란 ... 을 말한다" / "X 는 ... 를 의미한다" 의 정의 부분 추출 금지.
   - synonym 길이 > 25자 = 정의문 가능성 → 추출 금지.
   - 예: "침해사고" 의 정의("정보통신망 또는 정보시스템에 …") → 추출 금지.

2) **1:N 예시 나열 금지**:
   - "X = A, B, C, D" 패턴(1:N) 추출 금지.
   - 동의어는 1:1 매핑만.
   - 예: "사채(파생상품 / 금융상품 / 차입금)" → 추출 금지(예시 나열).

3) **synonym 길이 제한**:
   - synonym 25자 초과 = 추출 금지.
   - 절(clause)·문장 형식 = 정의문 가능성 → 추출 금지.

4) **문서 / 양식 번호 금지**:
   - "SSGDF-J-GU-…" 같은 코드 형식 금지.
   - 양식·보고서 번호 금지.

5) **단방향 관계 금지**:
   - "X 의 일부" / "X 의 종류" 관계 금지.
   - "X 또는 Y" 에서 "Y 가 X 의 일종" 패턴 금지.

6) **외부 지식 차단**:
   - 사규 외 지식·외부 LLM 학습 데이터 사용 금지.
   - 단락 내부에 정의되지 않은 추론·확장 금지.

JSON 출력 (예시):
{{"pairs": [{{"primary": "외감규정", "synonym": "외부감사 및 회계 등에 관한 규정", "evidence": "외부감사 및 회계 등에 관한 규정(이하 '외감규정')"}}]}}

단락에 명시적 동의어 정의가 없으면: {{"pairs": []}}

[단락 본문]
{chunk_text}

JSON 출력:"""


def extract_with_opus(chunk_text: str, anthropic_client: Any) -> list[dict]:
    """Claude Opus 4.7 의 LLM 보조 추출 (강화된 prompt, 외부지식 차단).

    PR-Phase-19.2.2: Haiku 4.5 → Opus 4.7 모델 변경 + prompt 6중 가드:
      ① 정의문 ② 1:N 나열 ③ 25자 제한 ④ 양식 번호 ⑤ 단방향 ⑥ 외부 지식.
    """
    if not chunk_text or anthropic_client is None:
        return []
    try:
        response = anthropic_client.messages.create(
            model="claude-opus-4-7",
            max_tokens=1024,
            messages=[{
                "role":    "user",
                "content": _OPUS_PROMPT_TEMPLATE.format(chunk_text=chunk_text),
            }],
        )
        raw = ""
        for block in response.content:
            if getattr(block, "type", None) == "text":
                raw += getattr(block, "text", "") or ""
        raw = raw.strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw)
        parsed = json.loads(raw)
        results: list[dict] = []
        for pair in (parsed.get("pairs") or []):
            primary = (pair.get("primary") or "").strip()
            synonym = (pair.get("synonym") or "").strip()
            if not primary or not synonym or primary == synonym:
                continue
            # 클라이언트측 25자 가드 (prompt 안전망 — LLM 이 룰 어겨도 차단)
            if len(synonym) > 25 or len(primary) > 25:
                continue
            evidence = (pair.get("evidence") or "")[:200]
            results.append({
                "primary_term":      primary,
                "synonym_term":      synonym,
                "extraction_method": "llm_assisted",
                "confidence":        0.90,
                "evidence_text":     evidence,
            })
        return results
    except Exception:
        return []


# ── 19.2.1 호환 alias (extract_with_haiku 호출처를 깨지 않기 위함) ──
extract_with_haiku = extract_with_opus


def extract_synonyms_from_chunks(
    chunks: list[dict], anthropic_client: Any = None,
) -> list[dict]:
    """모든 chunk 의 동의어 자동 추출 (regex + Haiku).

    chunks 입력 형식: [{"id": uuid, "doc_id": uuid, "text": str}]
    anthropic_client=None 이면 regex 만 (LLM 호출 skip).
    """
    all_results: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for chunk in chunks or []:
        text = chunk.get("text") or ""
        if not text:
            continue
        regex_hits = extract_regex_synonyms(text)
        llm_hits = (
            extract_with_opus(text, anthropic_client)
            if anthropic_client is not None else []
        )
        for r in regex_hits + llm_hits:
            key = (r["primary_term"], r["synonym_term"])
            if key in seen:
                continue
            seen.add(key)
            r["source_chunk_id"] = chunk.get("id")
            r["source_doc_id"]   = chunk.get("doc_id")
            all_results.append(r)
    return all_results
