"""Domain models — 외부 의존 없음. service/ai/data layer 공유."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class AnswerStatus(str, Enum):
    OK = "ok"
    INSUFFICIENT = "insufficient"
    ERROR = "error"


@dataclass(frozen=True)
class Chunk:
    id: str
    document_id: str
    document_title: str
    article_no: Optional[str]
    text: str
    categories: tuple[str, ...]
    score: float
    doc_kind: str

    @property
    def citation_label(self) -> str:
        if self.article_no:
            return f"[§{self.document_title} {self.article_no}]"
        return f"[§{self.document_title}]"


@dataclass(frozen=True)
class Citation:
    chunk_id: str
    document_title: str
    article_no: Optional[str]
    chunk_text: str

    @classmethod
    def from_chunk(cls, chunk: Chunk) -> "Citation":
        return cls(
            chunk_id=chunk.id,
            document_title=chunk.document_title,
            article_no=chunk.article_no,
            chunk_text=chunk.text,
        )


@dataclass(frozen=True)
class Answer:
    status: AnswerStatus
    text: str
    citations: tuple[Citation, ...] = field(default_factory=tuple)
    chunks_retrieved: int = 0
    elapsed_ms: int = 0
    error_message: Optional[str] = None

    @classmethod
    def insufficient(cls, chunks_retrieved: int = 0, elapsed_ms: int = 0) -> "Answer":
        return cls(
            status=AnswerStatus.INSUFFICIENT,
            text="제공된 사규에서 해당 정보를 확인할 수 없습니다. 정확한 사항은 인사팀 또는 CSR팀에 문의해 주세요.",
            citations=tuple(),
            chunks_retrieved=chunks_retrieved,
            elapsed_ms=elapsed_ms,
        )

    @classmethod
    def error(cls, message: str, elapsed_ms: int = 0) -> "Answer":
        return cls(
            status=AnswerStatus.ERROR,
            text="일시적 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.",
            error_message=message,
            elapsed_ms=elapsed_ms,
        )
