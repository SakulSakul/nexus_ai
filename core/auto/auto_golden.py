"""Auto-golden — Claude Opus 가 query+chunks 보고 expected_clauses 동적 생성."""

from __future__ import annotations

import json
import re
import sys

from .cache import golden_cache_get, golden_cache_set


GOLDEN_SYSTEM_PROMPT = """\
사규 답변 검증 spec 생성기. 사용자가 알아야 할 핵심 정보 (expected_clauses) 동적 생성.

입력:
- incident_nodes
- chunks (제목 + 앞 부분)

출력 (strict JSON):
{
  "expected_clauses": [
    {"topic": "...", "severity": "HIGH|MEDIUM|LOW", "expected_doc": "..."}
  ],
  "required_docs": [
    {"doc_title_pattern": "...", "severity": "HIGH|MEDIUM|LOW"}
  ]
}

severity:
- HIGH: 사용자 의사결정 핵심 (예: 징계 수위, 보고 시한)
- MEDIUM: 부가 정보
- LOW: 참고

3~7개 expected_clauses. 청크 내용 기반.
"""


def auto_golden(incident_nodes: list, chunks: list, *, use_cache: bool = True) -> tuple:
    """(golden_dict, source) — source: 'cache' | 'llm' | 'error'."""
    if use_cache:
        cached = golden_cache_get(incident_nodes)
        if cached is not None:
            return cached, "cache"

    try:
        import anthropic
        from core.config import settings
    except Exception as e:
        print(f"[auto_golden] SDK import 실패: {e}", file=sys.stderr, flush=True)
        return {"expected_clauses": [], "required_docs": []}, "error"

    s = settings()
    api_key = s.anthropic_api_key
    if not api_key:
        return {"expected_clauses": [], "required_docs": []}, "error"

    client = anthropic.Anthropic(api_key=api_key)
    summaries: list = []
    for c in (chunks or [])[:10]:
        if not isinstance(c, dict):
            continue
        title = c.get("doc_title") or c.get("title") or ""
        text = (c.get("text") or c.get("content") or "")[:300]
        summaries.append(f"- {title}: {text}...")
    chunks_block = "\n".join(summaries)
    user_msg = (
        f"incident_nodes: {incident_nodes}\n\n"
        f"청크:\n{chunks_block}\n\nstrict JSON."
    )

    try:
        response = client.messages.create(
            model="claude-opus-4-7",
            max_tokens=2000,
            system=GOLDEN_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_msg}],
        )
        raw_text = response.content[0].text if response.content else "{}"
        if "```" in raw_text:
            m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw_text, re.DOTALL)
            if m:
                raw_text = m.group(1)
        golden = json.loads(raw_text)
        if use_cache:
            golden_cache_set(incident_nodes, golden, "claude-opus-4-7")
        return golden, "llm"
    except Exception as e:
        print(
            f"[auto_golden] failed: {type(e).__name__}: {e}",
            file=sys.stderr, flush=True,
        )
        return {"expected_clauses": [], "required_docs": []}, "error"
