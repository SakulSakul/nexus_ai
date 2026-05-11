"""하이브리드 검색 (RPC: nexus_hybrid_search) 래퍼.

retrieve_for_eval — chatbot 의 retrieval pipeline 을 한 함수로 노출.
eval/runner.py (브라우저·CLI) 와 외부 검증 도구가 chatbot 과 동일한
contexts 결과를 받도록 한다. chatbot.py 의 ask/ask_stream 본문은
무수정 (호환성 유지) — 본 함수는 동일 흐름 재현이 목적.

DF COMPASS Tier 1+2 (2026-05-11):
- USE_HYBRID_SEARCH=True 일 때 검색 직전 Gemini 로 사규 용어 확장(Tier 1)
  + 신규 RPC nexus_hybrid_search_v2 호출(Tier 2). 외부 인터페이스
  (hybrid_search 시그니처·반환 dict 키) 무변경. False 면 즉시 기존 경로
  롤백.
"""

from __future__ import annotations

from typing import Any

from .config import settings
from .embedder import embed_one


# Tier 1 + Tier 2 활성화 토글. False 면 즉시 기존 RPC 경로로 롤백.
# 2026-05-11 핫픽스: rewriter 1글자 절단 버그 수정 검증 전까지 False 유지.
# admin "🔬 검색 비교" 패널에서 사용자가 raw vs cleaned 확인 후 True 로 복귀.
USE_HYBRID_SEARCH: bool = True


def _normalize_v2_row(row: dict) -> dict:
    """nexus_hybrid_search_v2 결과를 기존 hybrid_search 결과 dict 키 셋에
    맞춰 정규화. chatbot.build_user_prompt / _balance_by_doc_kind /
    confidence.calculate_confidence 가 같은 키 (chunk_id, doc_title,
    doc_kind, article_no, case_no, text, score, owning_department,
    categories) 를 그대로 사용할 수 있게 한다.
    """
    return {
        "chunk_id": row.get("id"),
        "document_id": row.get("document_id"),
        "doc_title": row.get("doc_title"),
        "doc_kind": row.get("doc_kind"),
        "article_no": row.get("article_no"),
        "case_no": None,
        "text": row.get("text"),
        "score": row.get("rrf_score"),
        "owning_department": None,
        "categories": row.get("categories") or [],
    }


def hybrid_search(
    supabase: Any,
    *,
    question: str,
    categories: list[str] | None,
    doc_kinds: list[str] | None = None,
    top_k: int | None = None,
) -> list[dict]:
    s = settings()
    if USE_HYBRID_SEARCH:
        # Tier 1 — 사규 용어 확장. 실패 시 원문 반환 (raise 안 함).
        from .nexus_query_rewriter import (
            rewrite_query_for_retrieval, nexus_build_keyword_tsquery,
        )
        retrieval_query_text = rewrite_query_for_retrieval(question)
        retrieval_embedding = embed_one(
            retrieval_query_text, task_type="RETRIEVAL_QUERY",
        )
        # Tier 2 보조: 한국어 조사 제거 + prefix tsquery 빌더. RPC v3 가
        # to_tsquery('simple', …) 로 받기 때문에 plainto_tsquery 형식이 아닌
        # 정식 tsquery 표현식("토큰:* | 토큰:*") 을 넘긴다.
        ts_query = nexus_build_keyword_tsquery(retrieval_query_text, original=question)
        match_count = top_k or s.top_k
        payload = {
            "query_embedding": retrieval_embedding,
            "query_text": ts_query,
            "match_count": match_count,
            "rrf_k": 60,
            "pool_size": max(30, match_count * 6),
        }
        res = supabase.rpc("nexus_hybrid_search_v2", payload).execute()
        rows = res.data or []
        return [_normalize_v2_row(r) for r in rows]

    # ── 기존 경로 (rollback safety net) ──────────────────────────
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
    #   text, score, owning_department, categories: list[str]
    # owning_department 는 DB 마이그레이션 단계 ② 로 시그니처에 추가됨.
    # categories 는 db/09 마이그레이션으로 추가 — chatbot.py 가
    # query_logs.hit_categories 평탄화 적재에 사용. multi-category chunk 는
    # 길이>=2 의 list 가 들어올 수 있음.
    # build_user_prompt 가 c.get("owning_department") 로 그대로 읽어 헤더에
    # 표기하므로 별도 변환 불필요.
    return res.data or []


def retrieve_for_eval(
    supabase: Any,
    question: str,
    *,
    mask: bool = True,
    with_critical: bool = False,
) -> list[dict]:
    """chatbot 의 retrieval pipeline 재현 — eval / 외부 검증용.

    chatbot.py 의 ask/ask_stream 흐름과 동일한 contexts 결과를 반환.
    공유 헬퍼 (mask_pii / infer_categories / detect / load_keywords /
    _DOC_KIND_RATIOS / _balance_by_doc_kind) 는 함수 내부에서 lazy import —
    retriever ↔ chatbot 순환 import 회피.

    Args:
        supabase: Supabase Client (anon 또는 service_role).
        question: 사용자 질의 raw 문자열.
        mask: True 면 mask_pii 적용 (chatbot 기본 동작).
        with_critical: True 면 critical 키워드 감지 → safety/harassment
                       카테고리 보강. eval 은 보통 False 로 호출 (fixture
                       검증 정확도 우선). chatbot 전체 흐름 재현 시 True.

    Returns:
        list[dict] — chatbot 의 ask().contexts 와 동일 형식 (chunk_id,
        doc_title, doc_kind, article_no, case_no, text, score,
        owning_department, categories).
    """
    # lazy import — chatbot 모듈 로딩 시점에 retriever 가 이미 import 된
    # 상태라 top-level import 는 순환을 만든다. 함수 호출 시점엔 안전.
    from .chatbot import (  # noqa: WPS433 — 의도된 lazy import
        infer_categories,
        _DOC_KIND_RATIOS,
        _balance_by_doc_kind,
    )

    if mask:
        from .pii_filter import mask_pii
        masked = mask_pii(question, [])
    else:
        masked = question

    # 카테고리 라우팅 — chatbot.py:683-691 와 동일.
    inferred = infer_categories(masked)
    cats: list[str] | None = (
        list(set(inferred) | {"공통"}) if inferred else None
    )

    # critical 보강 (선택) — chatbot.py:693-698 와 동일.
    if with_critical:
        try:
            from .critical_mode import detect, load_keywords
            keywords = load_keywords(supabase)
            detection = detect(question, keywords)
            if not detection.triggered:
                detection = detect(masked, keywords)
            if detection.triggered:
                if detection.kind == "safety":
                    cats = list(set((cats or []) + ["안전", "공통"]))
                elif detection.kind == "harassment":
                    cats = list(set((cats or []) + ["공통"]))
        except Exception:
            # critical 보강 실패는 retrieval 흐름을 막지 않는다.
            pass

    # pool_size = sum(_DOC_KIND_RATIOS.values()) + 3 (= 10 in 베타)
    # → balance 후 사용자에게 노출되는 contexts 수와 일치.
    pool_size = sum(_DOC_KIND_RATIOS.values()) + 3
    contexts_raw = hybrid_search(
        supabase, question=masked, categories=cats, top_k=pool_size,
    )
    return _balance_by_doc_kind(contexts_raw)
