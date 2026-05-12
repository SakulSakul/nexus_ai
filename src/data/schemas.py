"""DB row → Chunk mapper."""
from __future__ import annotations

from typing import Any

from src.service.models import Chunk


def chunk_from_row(row: dict[str, Any]) -> Chunk:
    categories_raw = row.get("categories") or []
    if isinstance(categories_raw, str):
        categories_raw = (
            categories_raw.strip("{}").split(",") if categories_raw else []
        )
    categories = tuple(c.strip() for c in categories_raw if c and c.strip())

    score_raw = row.get("score")
    if score_raw is None:
        score_raw = row.get("rrf_score") or row.get("sim_score") or 0.0

    return Chunk(
        id=str(row.get("id") or row.get("chunk_id") or ""),
        document_id=str(row.get("document_id") or ""),
        document_title=str(row.get("doc_title") or row.get("document_title") or ""),
        article_no=row.get("article_no"),
        text=str(row.get("text") or ""),
        categories=categories,
        score=float(score_raw),
        doc_kind=str(row.get("doc_kind") or "rule"),
    )
