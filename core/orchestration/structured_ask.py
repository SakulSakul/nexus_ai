"""Phase 7 X+ orchestrator — Fully Automated Constitution-Driven RAG.

흐름:
1. auto_classify (Gemini Flash) → incident_nodes
2. ask() retrieve → chunks (chatbot.ask 본체는 무수정)
3. auto_golden (Claude Opus) → expected_clauses 동적 생성
4. ask_structured (Gemini Pro + 헌법 prompt) → StructuredAnswer
5. verify_structured (deterministic) → verdict + score
6. render_structured_to_markdown → 사용자 표시
7. audit log 저장
"""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass
from typing import Any

from core.synthesis.structured_synth import ask_structured
from core.synthesis.structured_schema import StructuredAnswer
from core.verification.structured_verifier import (
    verify_structured, StructuredVerificationResult,
)
from core.rendering.structured_renderer import render_structured_to_markdown
from core.auto.auto_classifier import auto_classify
from core.auto.auto_golden import auto_golden


@dataclass
class StructuredAskResult:
    rendered_markdown: str
    structured_answer: StructuredAnswer
    verification: StructuredVerificationResult
    chunks: list
    incident_nodes: list
    classifier_source: str
    golden_source: str
    elapsed_total_ms: int
    elapsed_gemini_ms: int


def structured_ask(
    supabase: Any,
    question: str,
    *,
    audit_source: str = "structured_xplus",
) -> StructuredAskResult:
    """Phase 7 X+ orchestrator."""
    t0 = time.time()

    # 1. auto_classify.
    incident_nodes, cls_source = auto_classify(question)

    # 2. retrieve (chatbot.ask 본체 무수정).
    try:
        from core.chatbot import ask as _live_ask
        ans = _live_ask(supabase, question=question, category=None)
        if hasattr(ans, "contexts"):
            chunks = list(ans.contexts) if ans.contexts else []
        else:
            chunks = []
    except Exception as e:
        print(
            f"[structured_ask] retrieve failed: {type(e).__name__}: {e}",
            file=sys.stderr, flush=True,
        )
        chunks = []

    # 3. auto_golden.
    golden, golden_source = auto_golden(incident_nodes, chunks)

    # 4. structured synthesis.
    answer, elapsed_gemini_ms = ask_structured(question, chunks)

    # 5. deterministic verify.
    verification = verify_structured(answer, chunks, golden)

    # 6. render.
    rendered = render_structured_to_markdown(answer)
    elapsed_total_ms = int((time.time() - t0) * 1000)

    # 7. audit log (silent fail).
    try:
        from core.audit.logger import log_query
        from core.audit.schemas import AuditLogEntry
        chunk_ids = [
            str(c.get("id") or c.get("chunk_id") or "")
            for c in chunks if isinstance(c, dict)
        ]
        log_query(AuditLogEntry(
            source=audit_source,
            query=question,
            incident_nodes=incident_nodes,
            retrieved_chunk_ids=chunk_ids,
            retrieved_chunk_count=len(chunks),
            gemini_model_id="gemini-2.5-pro-structured",
            gemini_answer=rendered[:5000],
            gemini_latency_ms=elapsed_gemini_ms,
            claude_verdict=verification.verdict,
            claude_score=verification.overall_score,
            claude_report={
                "verdict": verification.verdict,
                "overall_score": verification.overall_score,
                "grounded_count": verification.grounded_count,
                "hallucinated_count": verification.hallucinated_count,
                "high_gaps": sum(
                    1 for g in verification.coverage_gaps
                    if g.severity == "HIGH"
                ),
                "chunk_usage_rate": verification.chunk_usage_rate,
                "classifier_source": cls_source,
                "golden_source": golden_source,
                "engine": "structured_xplus",
            },
            total_latency_ms=elapsed_total_ms,
            notes="xplus",
        ))
    except Exception as e:
        print(
            f"[structured_ask] audit failed (non-blocking): "
            f"{type(e).__name__}: {e}",
            file=sys.stderr, flush=True,
        )

    return StructuredAskResult(
        rendered_markdown=rendered,
        structured_answer=answer,
        verification=verification,
        chunks=chunks,
        incident_nodes=incident_nodes,
        classifier_source=cls_source,
        golden_source=golden_source,
        elapsed_total_ms=elapsed_total_ms,
        elapsed_gemini_ms=elapsed_gemini_ms,
    )
