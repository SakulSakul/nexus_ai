"""RAG 서비스 — 단일 retrieve + 단일 synthesis + citation forcing."""
from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Optional

from src.ai.base import LLMClient
from src.data.repository import DocumentRepository
from src.service.models import Answer, AnswerStatus, Chunk, Citation
from src.service.prompts import (
    CLASSIFIER_SYSTEM_PROMPT,
    SYNTHESIS_SYSTEM_PROMPT,
    build_synthesis_user_prompt,
)


# ── 임계치 상수
# SIMILARITY_THRESHOLD: nexus_hybrid_search_v2 가 RRF score 만 반환 (cosine 아님).
# RRF score 범위 ~0.005~0.05 라 의미있는 cosine threshold 와 단위 mismatch.
# Layer 1 (threshold) 비활성. 진짜 방어는 Layer 2 (prompt forcing) + Layer 3
# (post-LLM citation validator) 가 담당. chunks 0 만 insufficient 강제.
SIMILARITY_THRESHOLD: float = 0.0
RETRIEVE_TOP_K: int = 8
DEFAULT_CATEGORIES: tuple = ("공통",)

CITATION_TAG_RE = re.compile(r"\[§([^\]]+?)\]")


@dataclass
class RAGService:
    repository: DocumentRepository
    llm: LLMClient

    def answer(self, query: str) -> Answer:
        if not query or not query.strip():
            return Answer.error("질문이 비어있습니다.")

        t0 = time.time()

        try:
            cats = self._classify(query)
        except Exception:
            cats = list(DEFAULT_CATEGORIES)

        try:
            chunks = self.repository.search(
                query=query, categories=cats, top_k=RETRIEVE_TOP_K,
            )
        except Exception as e:
            return Answer.error(f"검색 중 오류: {e}", elapsed_ms=self._ms(t0))

        if not chunks:
            return Answer.insufficient(elapsed_ms=self._ms(t0))
        top_score = max(c.score for c in chunks)
        if top_score < SIMILARITY_THRESHOLD:
            return Answer.insufficient(
                chunks_retrieved=len(chunks), elapsed_ms=self._ms(t0),
            )

        try:
            answer_text = self._synthesize(query, chunks)
        except Exception as e:
            return Answer.error(f"합성 중 오류: {e}", elapsed_ms=self._ms(t0))

        validated_citations = self._validate_citations(answer_text, chunks)
        if not validated_citations:
            return Answer.insufficient(
                chunks_retrieved=len(chunks), elapsed_ms=self._ms(t0),
            )

        return Answer(
            status=AnswerStatus.OK,
            text=answer_text,
            citations=tuple(validated_citations),
            chunks_retrieved=len(chunks),
            elapsed_ms=self._ms(t0),
        )

    def _classify(self, query: str) -> list[str]:
        response = self.llm.classify(
            system_prompt=CLASSIFIER_SYSTEM_PROMPT,
            user_prompt=query,
        )
        cats = response.get("categories", [])
        if not isinstance(cats, list) or not cats:
            return list(DEFAULT_CATEGORIES)
        result = list(dict.fromkeys(cats + list(DEFAULT_CATEGORIES)))
        return result[:3]

    def _synthesize(self, query: str, chunks: list[Chunk]) -> str:
        user_prompt = build_synthesis_user_prompt(query, chunks)
        return self.llm.synthesize(
            system_prompt=SYNTHESIS_SYSTEM_PROMPT,
            user_prompt=user_prompt,
        )

    def _validate_citations(
        self, answer_text: str, chunks: list[Chunk],
    ) -> list[Citation]:
        found_tags = CITATION_TAG_RE.findall(answer_text)
        if not found_tags:
            return []

        valid_labels: dict[str, Chunk] = {}
        for c in chunks:
            label_inner = c.citation_label[2:-1]
            valid_labels[label_inner.strip()] = c

        citations: list[Citation] = []
        seen_chunk_ids: set = set()
        for tag in found_tags:
            tag_clean = tag.strip()
            matched_chunk = self._find_matching_chunk(tag_clean, valid_labels)
            if matched_chunk is None:
                return []
            if matched_chunk.id not in seen_chunk_ids:
                citations.append(Citation.from_chunk(matched_chunk))
                seen_chunk_ids.add(matched_chunk.id)

        return citations

    def _find_matching_chunk(
        self, tag: str, valid_labels: dict[str, Chunk],
    ) -> Optional[Chunk]:
        if tag in valid_labels:
            return valid_labels[tag]
        for label, chunk in valid_labels.items():
            if chunk.document_title in tag and tag in label:
                return chunk
            if chunk.document_title == tag:
                return chunk
        return None

    @staticmethod
    def _ms(t0: float) -> int:
        return int((time.time() - t0) * 1000)
