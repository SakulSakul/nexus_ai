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


_HAIKU_PROMPT_TEMPLATE = """다음은 신세계디에프 사규의 한 단락이다. 이 단락 내부에 \
명시적으로 "X (이하 Y 라 한다)" / "X 또는 Y 라 함" / "X = Y" 식으로 정의된 \
동의어 쌍만 추출하라.

★★ 절대 금지:
- 사규 외 지식·외부 LLM 학습 데이터 사용 금지.
- 단락 내부에 정의되지 않은 추론·확장 금지.
- 무관계한 단어쌍 묶음 금지.

JSON 출력 (예시):
{{"pairs": [{{"primary": "중간납품업자", "synonym": "벤더", "evidence": "중간납품업자(벤더)"}}]}}

단락에 정의가 없으면: {{"pairs": []}}

[단락 본문]
{chunk_text}

JSON 출력:"""


def extract_with_haiku(chunk_text: str, anthropic_client: Any) -> list[dict]:
    """Claude Haiku 4.5 의 LLM 보조 추출 (외부 지식 차단 prompt)."""
    if not chunk_text or anthropic_client is None:
        return []
    try:
        response = anthropic_client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=1024,
            messages=[{
                "role":    "user",
                "content": _HAIKU_PROMPT_TEMPLATE.format(chunk_text=chunk_text),
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
            evidence = (pair.get("evidence") or "")[:200]
            results.append({
                "primary_term":      primary,
                "synonym_term":      synonym,
                "extraction_method": "llm_assisted",
                "confidence":        0.85,
                "evidence_text":     evidence,
            })
        return results
    except Exception:
        return []


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
            extract_with_haiku(text, anthropic_client)
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
