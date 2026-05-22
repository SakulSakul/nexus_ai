"""Auto-Testset — PR-Stage-B-Auto-Testset.

docs.auto_query_examples 의 505 query 를 자동 실행 + shadow V3 매칭 분석.
사용자 피드백 의존 0. 자가 진단 시스템.
"""

from __future__ import annotations

import sys
import time
import uuid
from typing import Callable, Optional

from .cache import _get_sb
from core.retriever import _score_keywords_against_query, SHADOW_STOP_KEYWORDS

try:
    from core.nexus_query_rewriter import rewrite_query_for_retrieval
except Exception:
    def rewrite_query_for_retrieval(q: str) -> str:
        return q


def _compute_shadow_matches(
    question: str,
    retrieval_query_text: str,
    docs: list,
    chunks_by_doc: dict,
) -> list:
    """Shadow V3 매칭 결과 계산 (log 없이 return).

    retriever.py 의 _shadow_log_auto_keywords_match 와 동일 로직.
    """
    combined = ((question or "") + " " + (retrieval_query_text or "")).lower()

    query_words: set = set()
    for token in combined.replace("?", " ").replace(".", " ").replace(",", " ").split():
        if len(token) >= 3 and token not in SHADOW_STOP_KEYWORDS:
            query_words.add(token)

    doc_scores: dict = {}
    for doc in docs:
        doc_id = doc.get("id")
        score, matched = _score_keywords_against_query(
            doc.get("auto_keywords") or [],
            combined, query_words,
            direct_weight=2, partial_weight=1,
        )
        doc_scores[doc_id] = {
            "title": doc.get("title") or "",
            "doc_score": score,
            "chunk_score": 0,
        }

    for doc_id, doc_chunks in chunks_by_doc.items():
        if doc_id not in doc_scores:
            continue
        for chunk in doc_chunks:
            score, _ = _score_keywords_against_query(
                chunk.get("auto_keywords") or [],
                combined, query_words,
                direct_weight=3, partial_weight=2,
            )
            if score > 0:
                doc_scores[doc_id]["chunk_score"] += score

    scored: list = []
    for doc_id, info in doc_scores.items():
        total = info["doc_score"] + info["chunk_score"]
        if total >= 3:
            scored.append({
                "id": doc_id,
                "title": info["title"],
                "total": total,
                "doc_score": info["doc_score"],
                "chunk_score": info["chunk_score"],
            })

    scored.sort(key=lambda d: -d["total"])
    return scored


def run_full_testset(
    *,
    use_rewriter: bool = True,
    progress_callback: Optional[Callable] = None,
) -> dict:
    """505 query 자동 실행 + 메트릭 계산.

    Returns:
        {run_id, total_queries, recall_at_1, recall_at_3, recall_at_5,
         recall_overall, weak_docs, errors}
    """
    sb = _get_sb()
    if sb is None:
        return {"error": "Supabase 연결 실패"}

    # docs + chunks fetch
    docs_result = (
        sb.table("nexus_documents")
        .select("id, title, auto_keywords, auto_query_examples")
        .eq("status", "active")
        .execute()
    )
    docs = docs_result.data or []

    chunks_result = (
        sb.table("nexus_chunks")
        .select("id, document_id, chunk_idx, auto_keywords")
        .execute()
    )
    all_chunks = chunks_result.data or []

    docs_by_id = {d["id"]: d for d in docs}
    chunks_by_doc: dict = {}
    for c in all_chunks:
        doc_id = c.get("document_id")
        if doc_id in docs_by_id:
            chunks_by_doc.setdefault(doc_id, []).append(c)

    # testset_run insert
    run_id = str(uuid.uuid4())
    try:
        sb.table("testset_runs").insert({
            "id": run_id,
            "total_queries": 0,
        }).execute()
    except Exception as e:
        return {"error": f"run insert 실패: {e}"}

    # 각 query 실행
    rank_at_1 = 0
    rank_at_3 = 0
    rank_at_5 = 0
    rank_any = 0
    total = 0
    errors = 0
    doc_recall: dict = {}

    for doc in docs:
        doc_id = doc["id"]
        doc_title = doc.get("title") or ""
        queries = doc.get("auto_query_examples") or []

        for q_text in queries:
            if not isinstance(q_text, str) or not q_text.strip():
                continue
            total += 1

            try:
                rewritten = rewrite_query_for_retrieval(q_text) if use_rewriter else q_text
                matches = _compute_shadow_matches(
                    question=q_text,
                    retrieval_query_text=rewritten,
                    docs=docs,
                    chunks_by_doc=chunks_by_doc,
                )

                expected_rank = None
                for idx, m in enumerate(matches, 1):
                    if m["id"] == doc_id:
                        expected_rank = idx
                        break

                if expected_rank is not None:
                    rank_any += 1
                    if expected_rank == 1: rank_at_1 += 1
                    if expected_rank <= 3: rank_at_3 += 1
                    if expected_rank <= 5: rank_at_5 += 1

                if doc_id not in doc_recall:
                    doc_recall[doc_id] = {"title": doc_title, "total": 0, "matched": 0}
                doc_recall[doc_id]["total"] += 1
                if expected_rank is not None:
                    doc_recall[doc_id]["matched"] += 1

                try:
                    sb.table("testset_results").insert({
                        "run_id": run_id,
                        "query_text": q_text,
                        "expected_doc_id": doc_id,
                        "expected_doc_title": doc_title,
                        "matched_candidates": [
                            {"doc_id": m["id"], "title": m["title"],
                             "score": m["total"], "rank": idx}
                            for idx, m in enumerate(matches[:10], 1)
                        ],
                        "expected_rank": expected_rank,
                        "total_candidates": len(matches),
                    }).execute()
                except Exception as e:
                    errors += 1
                    print(f"[auto_testset] result insert failed: {e}",
                          file=sys.stderr, flush=True)

                if progress_callback:
                    try:
                        progress_callback(total, 505, {
                            "doc_title": doc_title,
                            "rank": expected_rank,
                        })
                    except Exception:
                        pass

                time.sleep(0.05)

            except Exception as e:
                errors += 1
                print(f"[auto_testset] {doc_id}/{q_text[:30]}: {e}",
                      file=sys.stderr, flush=True)

    # metrics 계산
    recall_at_1 = rank_at_1 / total if total > 0 else 0
    recall_at_3 = rank_at_3 / total if total > 0 else 0
    recall_at_5 = rank_at_5 / total if total > 0 else 0
    recall_overall = rank_any / total if total > 0 else 0

    try:
        sb.table("testset_runs").update({
            "completed_at": "now()",
            "total_queries": total,
            "recall_at_1": recall_at_1,
            "recall_at_3": recall_at_3,
            "recall_at_5": recall_at_5,
            "recall_overall": recall_overall,
        }).eq("id", run_id).execute()
    except Exception as e:
        print(f"[auto_testset] run update failed: {e}", file=sys.stderr, flush=True)

    # weak doc 식별
    weak_docs = []
    for doc_id, info in doc_recall.items():
        if info["total"] > 0:
            recall = info["matched"] / info["total"]
            if recall < 0.5:
                weak_docs.append({
                    "doc_id": doc_id,
                    "title": info["title"],
                    "recall": recall,
                    "matched": info["matched"],
                    "total": info["total"],
                })
    weak_docs.sort(key=lambda d: d["recall"])

    return {
        "run_id": run_id,
        "total_queries": total,
        "recall_at_1": recall_at_1,
        "recall_at_3": recall_at_3,
        "recall_at_5": recall_at_5,
        "recall_overall": recall_overall,
        "weak_docs": weak_docs[:20],
        "errors": errors,
    }
