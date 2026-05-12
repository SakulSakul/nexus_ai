"""Structured synthesis schema — claims with chunk_id provenance."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class StructuredClaim:
    text: str
    chunk_id: str
    verbatim_quote: str
    doc_title: str
    clause: str = ""


@dataclass
class StructuredSection:
    title: str
    claims: list = field(default_factory=list)


@dataclass
class StructuredAnswer:
    sections: list = field(default_factory=list)
    unsupported_topics: list = field(default_factory=list)
    data_gaps: list = field(default_factory=list)
    raw_json: dict = field(default_factory=dict)

    @classmethod
    def from_json(cls, raw: dict) -> "StructuredAnswer":
        sections = []
        for s in raw.get("sections", []) or []:
            claims = [
                StructuredClaim(
                    text=c.get("text", ""),
                    chunk_id=str(c.get("chunk_id", "")),
                    verbatim_quote=c.get("verbatim_quote", ""),
                    doc_title=c.get("doc_title", ""),
                    clause=c.get("clause", ""),
                )
                for c in s.get("claims", []) or []
            ]
            sections.append(StructuredSection(title=s.get("title", ""), claims=claims))
        return cls(
            sections=sections,
            unsupported_topics=raw.get("unsupported_topics") or [],
            data_gaps=raw.get("data_gaps") or [],
            raw_json=raw,
        )

    def to_dict(self) -> dict:
        return asdict(self)


GEMINI_RESPONSE_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "sections": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "claims": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "text": {"type": "string"},
                                "chunk_id": {"type": "string"},
                                "verbatim_quote": {"type": "string"},
                                "doc_title": {"type": "string"},
                                "clause": {"type": "string"},
                            },
                            "required": ["text", "chunk_id", "verbatim_quote", "doc_title"],
                        },
                    },
                },
                "required": ["title", "claims"],
            },
        },
        "unsupported_topics": {"type": "array", "items": {"type": "string"}},
        "data_gaps": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["sections"],
}
