"""Chunk Meta Filler — PR-Stage-A-1-Chunk.

nexus_chunks 의 auto_keywords 일괄 채움.
LLM: Claude Opus 4.7 (auto_tagger.extract_chunk_keywords 호출).
부모 doc context 활용 (title + auto_categories).
"""

from __future__ import annotations

import sys
import time
from typing import Callable, Optional

from .cache import _get_sb
from .auto_tagger import extract_chunk_keywords


def fill_chunk_keywords_all(
    *,
    dry_run: bool = True,
    sample_size: Optional[int] = None,
    progress_callback: Optional[Callable] = None,
    only_missing: bool = True,
) -> dict:
    """active doc 의 모든 chunk 의 auto_keywords 채움.

    Args:
        dry_run: True 면 DB UPDATE skip (LLM 호출은 sample_size 만큼).
        sample_size: dry_run 시 처음 N개 chunk 만 처리 (비용 최적화).
        progress_callback: callback(idx, total, chunk_info).
        only_missing: True 면 auto_keywords 빈 list 인 chunk 만.

    Returns:
        {"total": N, "processed": M, "updated": K, "errors": L,
         "samples": [{"chunk_id", "doc_title", "chunk_idx", "keywords"}, ...]}
    """
    sb = _get_sb()
    if sb is None:
        return {"total": 0, "processed": 0, "updated": 0, "errors": 0,
                "samples": [], "note": "Supabase 연결 실패"}

    # active doc 의 chunks + parent doc context 조회
    try:
        # nexus_chunks 와 nexus_documents JOIN (parent doc 가 active 인 chunk 만)
        chunks_result = (
            sb.table("nexus_chunks")
            .select(
                "id, document_id, chunk_idx, text, auto_keywords, "
                "nexus_documents!inner(title, status, meta)"
            )
            .eq("nexus_documents.status", "active")
            .order("document_id")
            .order("chunk_idx")
            .execute()
        )
        all_chunks = chunks_result.data or []
    except Exception as e:
        return {"total": 0, "processed": 0, "updated": 0, "errors": 0,
                "samples": [], "note": f"chunks fetch error: {e}"}

    # only_missing 필터
    if only_missing:
        target_chunks = [
            c for c in all_chunks
            if not c.get("auto_keywords") or len(c["auto_keywords"]) == 0
        ]
    else:
        target_chunks = all_chunks

    # dry_run 시 sample_size 만큼 자르기 (비용 최적화)
    if dry_run and sample_size is not None:
        target_chunks = target_chunks[:sample_size]

    total = len(target_chunks)
    processed = 0
    updated = 0
    errors = 0
    samples: list[dict] = []

    for idx, chunk in enumerate(target_chunks, 1):
        chunk_id = chunk["id"]
        chunk_text = chunk.get("text") or ""
        doc_info = chunk.get("nexus_documents") or {}
        doc_title = doc_info.get("title") or ""
        doc_meta = doc_info.get("meta") or {}
        doc_categories = (doc_meta.get("auto_categories") or []) if isinstance(doc_meta, dict) else []

        if progress_callback:
            try:
                progress_callback(idx, total, {
                    "doc_title": doc_title,
                    "chunk_idx": chunk.get("chunk_idx"),
                })
            except Exception:
                pass

        # LLM 호출
        keywords = extract_chunk_keywords(
            chunk_text=chunk_text,
            doc_title=doc_title,
            doc_categories=doc_categories,
        )
        processed += 1

        if not keywords:
            errors += 1
            continue

        # sample 수집 (앞 5개)
        if len(samples) < 5:
            samples.append({
                "chunk_id": chunk_id,
                "doc_title": doc_title,
                "chunk_idx": chunk.get("chunk_idx"),
                "keywords": keywords,
                "text_preview": chunk_text[:100],
            })

        # DB UPDATE — auto_keywords 는 기존 ∪ 신규 merge (수동 패치/기존 키워드 보존)
        if not dry_run:
            try:
                existing_kw = chunk.get("auto_keywords") or []
                seen: set[str] = set()
                merged_kw: list[str] = []
                for k in list(existing_kw) + list(keywords):
                    if isinstance(k, str):
                        ks = k.strip()
                        if ks and ks not in seen:
                            seen.add(ks)
                            merged_kw.append(ks)
                sb.table("nexus_chunks").update({
                    "auto_keywords": merged_kw,
                }).eq("id", chunk_id).execute()
                updated += 1
            except Exception as e:
                errors += 1
                print(f"[chunk_filler] UPDATE failed for {chunk_id}: {e}",
                      file=sys.stderr, flush=True)

        # Claude rate limit 보호
        time.sleep(0.3)

    return {
        "total": total,
        "processed": processed,
        "updated": updated,
        "errors": errors,
        "samples": samples,
        "dry_run": dry_run,
    }
