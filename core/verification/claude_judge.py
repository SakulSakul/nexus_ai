"""Claude Opus judge — 답변 정합성 검증."""

from __future__ import annotations

import json
import os
import re
import sys
import time
from typing import Any

try:
    import anthropic
    _ANTHROPIC_AVAILABLE = True
except ImportError:
    _ANTHROPIC_AVAILABLE = False

from .reports import VerificationReport, Verdict  # noqa: F401


CLAUDE_MODEL = "claude-opus-4-7"
MAX_TOKENS = 4096
TIMEOUT_SECONDS = 90


CLAUDE_JUDGE_SYSTEM_PROMPT = """\
당신은 신세계디에프 사규 컴플라이언스 검증 judge 입니다.

역할: Gemini 가 생성한 답변이 source 사규 청크와 **엄격하게** grounded 되어 있는지 검증.

원칙:
1. 답변의 모든 사실적 claim 은 청크 텍스트에 근거해야 함
2. 인용된 조항 번호 (예: 4.1.3조) 는 해당 청크에 실제 존재해야 함
3. 시한, 부서명, 처분 등급은 청크 텍스트와 정확히 일치해야 함
4. 발명/추정된 claim 은 모두 hallucination 으로 flag
5. Coverage: incident_type 에 매핑된 expected 사규/조항 중 누락된 것 flag
6. Strict mode: 의심스러우면 hallucination 으로 분류 (fail-closed)

출력: 아래 JSON schema (다른 텍스트 없이 JSON 만):

{
  "verdict": "pass" | "warn" | "fail",
  "overall_score": <0-100>,

  "grounded_claims": [
    {
      "claim_text": "<답변에서 verbatim 발췌, 200자 이내>",
      "cited_clause": "<예: (공통) 일반 사건사고 보고지침 제4.1.3조>",
      "matched_chunk_id": "<청크 ID>",
      "match_type": "exact" | "semantic" | "partial",
      "match_evidence": "<청크에서 supporting snippet 발췌, 200자 이내>"
    }
  ],

  "hallucinated_claims": [
    {
      "claim_text": "<verbatim>",
      "cited_clause": "<as cited or '인용 없음'>",
      "issue": "<예: '4.1.5조' 가 어느 청크에도 없음 / 시한 불일치 / 부서명 fabricated>",
      "evidence": "<청크에서 발견한 실제 내용 or '관련 청크 없음'>"
    }
  ],

  "coverage_gaps": [
    {
      "missing_doc_or_clause": "<예: '(공통) 일반... 4.2.2조'>",
      "expected_topic": "<해당 조항이 다룰 주제>",
      "severity": "HIGH" | "MEDIUM" | "LOW",
      "rationale": "<왜 누락이 문제인지>"
    }
  ],

  "consistency_issues": [
    "<답변 내 모순 — 같은 조항 다른 인용 / 시한 충돌 등>"
  ],

  "explanation": "<2-3 문장 요약>"
}

Verdict 기준:
- pass: hallucinated_claims=0 AND HIGH severity coverage_gaps=0 AND consistency_issues=0 AND score>=90
- warn: hallucinated_claims=0 AND HIGH coverage_gaps<=0 AND (MEDIUM gaps OR consistency_issues>0) AND score 70-89
- fail: hallucinated_claims>0 OR HIGH coverage_gaps>0 OR score<70

엄격하게. 컴플라이언스 실패는 법적/HR 결과 동반."""


def _format_chunks_for_prompt(chunks: list) -> str:
    lines: list[str] = []
    for i, c in enumerate(chunks or []):
        if not isinstance(c, dict):
            continue
        chunk_id = c.get("id") or c.get("chunk_id") or f"chunk_{i}"
        doc_title = c.get("doc_title") or "<unknown>"
        article_no = c.get("article_no") or ""
        text = c.get("text") or ""
        lines.append(
            f"--- CHUNK {i+1} ---\n"
            f"chunk_id: {chunk_id}\n"
            f"doc_title: {doc_title}\n"
            f"article_no: {article_no}\n"
            f"text:\n{text}\n"
        )
    return "\n".join(lines)


def _format_golden_coverage(golden: dict) -> str:
    if not golden:
        return "(golden coverage 미정의)"
    lines = [f"# Incident type: {golden.get('description', 'unknown')}"]
    required_docs = golden.get("required_docs", {}) or {}
    for doc_title, info in required_docs.items():
        lines.append(f"\n## {doc_title} ({info.get('severity', 'REQUIRED')})")
        for clause_info in info.get("required_clauses", []) or []:
            lines.append(
                f"  - {clause_info['clause']} [{clause_info.get('severity', 'MEDIUM')}]: "
                f"{clause_info.get('topic', '')}"
            )
    sections = golden.get("expected_sections", []) or []
    if sections:
        lines.append("\n## Expected answer sections:")
        for s in sections:
            lines.append(f"  - {s}")
    return "\n".join(lines)


def _format_verification_input(
    query: str,
    chunks: list,
    answer: str,
    golden: dict | None,
    incident_nodes: list | None,
) -> str:
    return f"""\
# 사용자 질문
{query}

# 분류된 incident nodes
{incident_nodes or []}

# Source 사규 청크 ({len(chunks or [])} 개)
{_format_chunks_for_prompt(chunks or [])}

# Gemini 가 생성한 답변
{answer}

# Expected coverage (golden taxonomy)
{_format_golden_coverage(golden or {})}

위 답변을 청크 + golden 기준으로 엄격하게 검증하고 JSON 출력해주세요."""


_JSON_BLOCK_PATTERN = re.compile(r"\{[\s\S]*\}", re.MULTILINE)


def _parse_json_from_response(text: str) -> dict:
    fence_match = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", text)
    if fence_match:
        return json.loads(fence_match.group(1))
    match = _JSON_BLOCK_PATTERN.search(text)
    if match:
        return json.loads(match.group(0))
    raise ValueError("No JSON block found in response")


def verify_with_claude(
    query: str,
    chunks: list,
    answer: str,
    golden_citations: dict | None = None,
    incident_nodes: list | None = None,
    api_key: str | None = None,
) -> VerificationReport:
    """Claude Opus 로 답변 정합성 검증."""
    if not _ANTHROPIC_AVAILABLE:
        return VerificationReport.from_error(
            "anthropic SDK 미설치. requirements.txt 확인."
        )

    api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        try:
            import streamlit as st
            api_key = st.secrets.get("ANTHROPIC_API_KEY")
        except Exception:
            pass
    if not api_key:
        return VerificationReport.from_error(
            "ANTHROPIC_API_KEY 미설정 (Streamlit Cloud secrets 또는 env var 확인)"
        )

    if not answer or not chunks:
        return VerificationReport.from_error(
            f"입력 누락: answer={'있음' if answer else '없음'} / chunks={len(chunks or [])}"
        )

    client = anthropic.Anthropic(api_key=api_key, timeout=TIMEOUT_SECONDS)
    user_message = _format_verification_input(
        query, chunks, answer, golden_citations, incident_nodes
    )
    start_time = time.time()
    raw_text = ""
    try:
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=MAX_TOKENS,
            system=CLAUDE_JUDGE_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )
        latency_ms = int((time.time() - start_time) * 1000)
        raw_text = response.content[0].text if response.content else ""
        print(
            f"[claude_judge] verdict_pending model={CLAUDE_MODEL} "
            f"latency={latency_ms}ms tokens_in={response.usage.input_tokens} "
            f"tokens_out={response.usage.output_tokens}",
            file=sys.stderr, flush=True,
        )
        data = _parse_json_from_response(raw_text)
        report = VerificationReport.from_json(data, raw=raw_text, latency_ms=latency_ms)
        print(
            f"[claude_judge] verdict={report.verdict.value} "
            f"score={report.overall_score:.1f} "
            f"grounded={len(report.grounded_claims)} "
            f"hallucinated={len(report.hallucinated_claims)} "
            f"gaps={len(report.coverage_gaps)}",
            file=sys.stderr, flush=True,
        )
        return report
    except anthropic.APIConnectionError as e:
        return VerificationReport.from_error(f"API 연결 실패: {e}")
    except anthropic.RateLimitError as e:
        return VerificationReport.from_error(f"Rate limit: {e}")
    except anthropic.APIStatusError as e:
        return VerificationReport.from_error(
            f"API status {e.status_code}: {getattr(e, 'message', str(e))}"
        )
    except json.JSONDecodeError as e:
        return VerificationReport.from_error(
            f"JSON 파싱 실패: {e}. Raw response 의 처음 500자: {raw_text[:500]}"
        )
    except Exception as e:
        return VerificationReport.from_error(f"{type(e).__name__}: {e}")
