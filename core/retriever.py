"""하이브리드 검색 (RPC: nexus_hybrid_search) 래퍼."""

from __future__ import annotations

from typing import Any

from .config import settings
from .embedder import embed_one


def hybrid_search(
    supabase: Any,
    *,
    question: str,
    categories: list[str] | None,
    doc_kinds: list[str] | None = None,
    top_k: int | None = None,
) -> list[dict]:
    s = settings()
    emb = embed_one(question, task_type="RETRIEVAL_QUERY")
    payload: dict = {
        "query_text": question,
        "query_embed": emb,
        "filter_categories": categories or None,
        "filter_doc_kinds": doc_kinds or None,
        "top_k": top_k or s.top_k,
        "fanout": max(20, (top_k or s.top_k) * 10),
        "rrf_k": 60,
        "fallback_to_common": True,
    }
    res = supabase.rpc("nexus_hybrid_search", payload).execute()
    # RPC 결과 dict 의 키 (RETURN TABLE 시그니처 그대로):
    #   chunk_id, document_id, doc_title, doc_kind, article_no, case_no,
    #   text, score, owning_department
    # owning_department 는 DB 마이그레이션 단계 ② 로 시그니처에 추가됨.
    # build_user_prompt 가 c.get("owning_department") 로 그대로 읽어 헤더에
    # 표기하므로 별도 변환 불필요.
    return res.data or []
