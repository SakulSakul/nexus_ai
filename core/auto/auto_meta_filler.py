"""Auto-Meta Filler — PR-Stage-A-1.

active docs 의 auto_keywords / auto_summary / auto_query_examples 일괄 채움.
LLM: Claude Opus 4.7 (auto_tagger.extract_doc_full_meta 호출).
"""

from __future__ import annotations

import sys
import time
from typing import Callable, Optional

from .cache import _get_sb
from .auto_tagger import extract_doc_full_meta


def fetch_doc_text_sample(supabase, doc_id: str, max_chars: int = 3000) -> str:
    """doc 의 chunks 앞부분 가져옴 (LLM 입력용).

    PR-Stage-A-1-Hotfix: nexus_chunks 의 컬럼은 document_id / text
    (auto_tagger.py 와 동일 스키마).
    """
    try:
        result = (
            supabase.table("nexus_chunks")
            .select("text")
            .eq("document_id", doc_id)
            .limit(5)
            .execute()
        )
        text = ""
        for row in result.data or []:
            text += (row.get("text") or "") + "\n\n"
            if len(text) >= max_chars:
                break
        return text[:max_chars]
    except Exception as e:
        print(f"[meta_filler] chunks fetch failed for {doc_id}: {e}",
              file=sys.stderr, flush=True)
        return ""


def fill_meta_all_docs(
    *,
    dry_run: bool = True,
    progress_callback: Optional[Callable] = None,
    only_missing: bool = True,
) -> dict:
    """active doc 전체의 auto_keywords/auto_summary/auto_query_examples 채움.

    Args:
        dry_run: True 면 추출만, False 면 DB UPDATE.
        progress_callback: callback(idx, total, doc_title).
        only_missing: True 면 auto_keywords 가 빈 list 인 doc 만 처리. False 면 전체.

    Returns:
        {"total": N, "processed": M, "updated": K, "errors": L,
         "samples": [{"doc_id", "title", "meta"}, ...] (앞 5개)}
    """
    sb = _get_sb()
    if sb is None:
        return {"total": 0, "processed": 0, "updated": 0, "errors": 0,
                "samples": [], "note": "Supabase 연결 실패"}

    # active docs 조회
    try:
        docs_result = (
            sb.table("nexus_documents")
            .select("id, title, auto_keywords")
            .eq("status", "active")
            .order("id")
            .execute()
        )
        all_docs = docs_result.data or []
    except Exception as e:
        return {"total": 0, "processed": 0, "updated": 0, "errors": 0,
                "samples": [], "note": f"docs fetch error: {e}"}

    # only_missing 필터
    if only_missing:
        target_docs = [
            d for d in all_docs
            if not d.get("auto_keywords") or len(d["auto_keywords"]) == 0
        ]
    else:
        target_docs = all_docs

    total = len(target_docs)
    processed = 0
    updated = 0
    errors = 0
    samples: list[dict] = []

    for idx, doc in enumerate(target_docs, 1):
        doc_id = doc["id"]
        title = doc.get("title") or ""

        if progress_callback:
            try:
                progress_callback(idx, total, title)
            except Exception:
                pass

        text_sample = fetch_doc_text_sample(sb, doc_id)
        meta = extract_doc_full_meta(doc_id, title, text_sample)
        processed += 1

        # 에러 감지
        if meta.get("rationale", "").startswith("error:") or \
           meta.get("rationale", "").startswith("SDK import error:"):
            errors += 1
            continue

        # sample 수집 (앞 5개)
        if len(samples) < 5:
            samples.append({
                "doc_id": doc_id,
                "title": title,
                "meta": meta,
            })

        # DB UPDATE
        if not dry_run:
            try:
                sb.table("nexus_documents").update({
                    "auto_keywords": meta.get("auto_keywords", []),
                    "auto_summary": meta.get("auto_summary", ""),
                    "auto_query_examples": meta.get("auto_query_examples", []),
                }).eq("id", doc_id).execute()
                updated += 1
            except Exception as e:
                errors += 1
                print(f"[meta_filler] UPDATE failed for {doc_id}: {e}",
                      file=sys.stderr, flush=True)

        # rate limit 보호 (Claude API)
        time.sleep(0.3)

    return {
        "total": total,
        "processed": processed,
        "updated": updated,
        "errors": errors,
        "samples": samples,
        "dry_run": dry_run,
    }
