"""AuditLogEntry — Supabase 저장 단위."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class AuditLogEntry:
    source: str
    query: str
    rewritten_query: Optional[str] = None
    incident_nodes: list = field(default_factory=list)

    retrieved_chunk_ids: list = field(default_factory=list)
    retrieved_chunk_count: int = 0

    gemini_model_id: Optional[str] = None
    gemini_answer: Optional[str] = None
    gemini_latency_ms: int = 0

    claude_model_id: Optional[str] = None
    claude_verdict: Optional[str] = None
    claude_score: Optional[float] = None
    claude_report: Optional[dict] = None
    claude_latency_ms: int = 0

    total_latency_ms: int = 0
    notes: Optional[str] = None

    def to_payload(self) -> dict:
        """Supabase insert 용 dict (None 값 제거)."""
        raw = {
            "source": self.source,
            "query": self.query,
            "rewritten_query": self.rewritten_query,
            "incident_nodes": self.incident_nodes or None,
            "retrieved_chunk_ids": self.retrieved_chunk_ids or None,
            "retrieved_chunk_count": self.retrieved_chunk_count,
            "gemini_model_id": self.gemini_model_id,
            "gemini_answer": self.gemini_answer,
            "gemini_latency_ms": self.gemini_latency_ms,
            "claude_model_id": self.claude_model_id,
            "claude_verdict": self.claude_verdict,
            "claude_score": self.claude_score,
            "claude_report": self.claude_report,
            "claude_latency_ms": self.claude_latency_ms,
            "total_latency_ms": self.total_latency_ms,
            "notes": self.notes,
        }
        return {k: v for k, v in raw.items() if v is not None}
