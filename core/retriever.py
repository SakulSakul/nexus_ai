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

# Incident-aware rerank — document.meta.incident_nodes 매칭 시 rrf_score
# 에 가산할 boost. admin 디버그 패널이 본 상수를 import 해 표시 일관성 유지.
INCIDENT_BOOST: float = 0.30

# 청크 text 에 응급 대응 키워드가 포함될 때 추가 가산. AEO 출입통제 문서
# 내 "비권한자 침입" 청크가 아닌 "응급조치" 청크 surface 보장 목적.
EMERGENCY_KEYWORDS: tuple = (
    "응급조치", "응급 조치",
    "병원 후송", "병원후송",
    "보안실 통보", "보안실통보", "보안실에 통보",
    "현장 보존", "현장보존",
    "응급구호", "응급 구호",
    "구급",
)
EMERGENCY_CHUNK_BOOST: float = 0.10

# Force-included 청크는 base rrf_score=0 이라 normal 청크와 경쟁 불가 →
# top-5 진입 보장 위해 별도의 큰 가산.
EMERGENCY_FORCE_INCLUDE_BOOST: float = 0.40

# Intent-matched docs force-include — user_incident_nodes 와 meta.incident_nodes
# 가 교집합 있는 모든 active docs 의 모든 청크를 retrieval pool 에 강제 포함.
# 4개 동등 phrasing 이 동일 doc set 을 보장 (결정론적 retrieval).
FORCE_INCLUDE_DOC_BOOST: float = 0.20


def _normalize_v2_row(row: dict) -> dict:
    """nexus_hybrid_search_v2 결과를 기존 hybrid_search 결과 dict 키 셋에
    맞춰 정규화. chatbot.build_user_prompt / _balance_by_doc_kind /
    confidence.calculate_confidence 가 같은 키 (chunk_id, doc_title,
    doc_kind, article_no, case_no, text, score, owning_department,
    categories) 를 그대로 사용할 수 있게 한다.

    incident_boost_applied / matched_incident_nodes 는 retriever 의 rerank
    단계에서 채워지는 디버깅 메타 — 정상 합성 경로는 무시, admin 디버그
    패널은 본 키들을 그대로 읽어 표시.
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
        "incident_boost_applied": bool(row.get("incident_boost_applied")),
        "matched_incident_nodes": row.get("matched_incident_nodes") or [],
        "emergency_chunk_boost_applied": bool(row.get("emergency_chunk_boost_applied")),
        "matched_emergency_keywords": row.get("matched_emergency_keywords") or [],
        "force_included": bool(row.get("force_included")),
        "force_included_by_intent": bool(row.get("force_included_by_intent")),
        "chunk_incident_boost_applied": bool(row.get("chunk_incident_boost_applied")),
        "matched_chunk_incident_nodes": row.get("matched_chunk_incident_nodes") or [],
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
            rewrite_query_for_retrieval,
            nexus_build_keyword_tsquery,
            nexus_classify_to_incident_nodes,
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
        # Incident-aware rerank: 사용자 질문 + rewritten 양쪽에서 incident
        # 노드 분류 후 RPC top-15 로 풀을 확대해 receive → meta.incident_nodes
        # 매칭 시 rrf_score +INCIDENT_BOOST 가산 → 재정렬 후 match_count 컷.
        rpc_match_count = max(match_count, 15)
        payload = {
            "query_embedding": retrieval_embedding,
            "query_text": ts_query,
            "match_count": rpc_match_count,
            "rrf_k": 60,
            "pool_size": max(30, rpc_match_count * 6),
        }
        res = supabase.rpc("nexus_hybrid_search_v2", payload).execute()
        raw_chunks = res.data or []

        # 1) 사용자 입력 incident 분류 — 원본 + rewritten 합쳐 노드 추출.
        user_incident_nodes = set(
            nexus_classify_to_incident_nodes(question or "")
        ) | set(
            nexus_classify_to_incident_nodes(retrieval_query_text or "")
        )

        # 1.4) Track C — Intent-matched docs guaranteed inclusion.
        # user_incident_nodes 와 meta.incident_nodes 교집합 있는 모든 active
        # docs 의 청크를 retrieval pool 에 강제 포함. 4개 동등 phrasing 이
        # 같은 doc set 을 받도록 결정론적 retrieval 보장.
        intent_matched_doc_ids: list = []
        if user_incident_nodes:
            try:
                docs_full_resp = (
                    supabase.table("nexus_documents")
                    .select("id, title, doc_kind, meta")
                    .eq("status", "active")
                    .execute()
                )
                docs_full_rows = docs_full_resp.data or []
                _intent_doc_info: dict = {}
                for d in docs_full_rows:
                    doc_nodes = set((d.get("meta") or {}).get("incident_nodes") or [])
                    if doc_nodes & user_incident_nodes:
                        intent_matched_doc_ids.append(d["id"])
                        _intent_doc_info[d["id"]] = d
                if intent_matched_doc_ids:
                    chunks_resp = (
                        supabase.table("nexus_chunks")
                        .select("id, document_id, chunk_idx, article_no, text, categories, chunk_incident_nodes")
                        .in_("document_id", intent_matched_doc_ids)
                        .execute()
                    )
                    existing_ids = {c.get("id") for c in raw_chunks if c.get("id")}
                    for fc in (chunks_resp.data or []):
                        if fc.get("id") in existing_ids:
                            continue
                        d = _intent_doc_info.get(fc.get("document_id"), {}) or {}
                        raw_chunks.append({
                            "id": fc.get("id"),
                            "document_id": fc.get("document_id"),
                            "doc_title": d.get("title"),
                            "doc_kind": d.get("doc_kind"),
                            "article_no": fc.get("article_no"),
                            "text": fc.get("text") or "",
                            "categories": fc.get("categories") or [],
                            "chunk_incident_nodes": fc.get("chunk_incident_nodes") or [],
                            "rrf_score": 0.0,
                            "force_included_by_intent": True,
                        })
            except Exception:
                # force-include 실패는 검색 흐름을 막지 않는다.
                pass

        # 1.5) Force-include — '응급대응' 의도일 때 chunk_incident_nodes 에
        # '응급대응' 태그된 청크를 vector/keyword pool 미포함이어도 강제 합류.
        # AEO 출입통제 위기상황 대응표 같은 청크 보장. doc title/kind/categories
        # 는 nexus_documents 별도 조회로 enrich.
        if "응급대응" in user_incident_nodes:
            try:
                raw_chunk_ids = {c.get("id") for c in raw_chunks if c.get("id")}
                em_resp = (
                    supabase.table("nexus_chunks")
                    .select("id, document_id, chunk_idx, article_no, text, categories, chunk_incident_nodes")
                    .contains("chunk_incident_nodes", ["응급대응"])
                    .execute()
                )
                em_rows = em_resp.data or []
                # 부족한 doc 메타 (title/kind) 보강 — RPC 결과 schema 와 정렬.
                em_doc_ids = list({
                    e.get("document_id") for e in em_rows
                    if e.get("document_id") and e.get("id") not in raw_chunk_ids
                })
                em_doc_meta: dict = {}
                if em_doc_ids:
                    em_docs_resp = (
                        supabase.table("nexus_documents")
                        .select("id, title, doc_kind, meta")
                        .in_("id", em_doc_ids)
                        .execute()
                    )
                    em_doc_meta = {
                        d["id"]: d for d in (em_docs_resp.data or [])
                    }
                for ec in em_rows:
                    if ec.get("id") in raw_chunk_ids:
                        continue
                    d = em_doc_meta.get(ec.get("document_id"), {}) or {}
                    raw_chunks.append({
                        "id": ec.get("id"),
                        "document_id": ec.get("document_id"),
                        "doc_title": d.get("title"),
                        "doc_kind": d.get("doc_kind"),
                        "article_no": ec.get("article_no"),
                        "text": ec.get("text") or "",
                        "categories": ec.get("categories") or [],
                        "chunk_incident_nodes": ec.get("chunk_incident_nodes") or [],
                        "rrf_score": 0.0,
                        "force_included": True,
                    })
            except Exception:
                # force-include 실패는 검색 흐름을 막지 않는다.
                pass

        # 2) doc meta 일괄 조회 (RPC 결과에 meta 미포함 — 컬럼 미반환).
        doc_meta_map: dict = {}
        if raw_chunks and user_incident_nodes:
            doc_ids = list({
                c.get("document_id") for c in raw_chunks if c.get("document_id")
            })
            if doc_ids:
                try:
                    docs_resp = (
                        supabase.table("nexus_documents")
                        .select("id, meta")
                        .in_("id", doc_ids)
                        .execute()
                    )
                    doc_meta_map = {
                        d["id"]: (d.get("meta") or {})
                        for d in (docs_resp.data or [])
                    }
                except Exception:
                    doc_meta_map = {}

        # 3) Incident-aware boost (module-level INCIDENT_BOOST) + 청크 keyword boost.
        for chunk in raw_chunks:
            meta = doc_meta_map.get(chunk.get("document_id"), {}) or {}
            doc_incident_nodes = set(meta.get("incident_nodes") or [])
            matched = doc_incident_nodes & user_incident_nodes
            if matched:
                chunk["rrf_score"] = (chunk.get("rrf_score") or 0.0) + INCIDENT_BOOST
                chunk["incident_boost_applied"] = True
                chunk["matched_incident_nodes"] = sorted(matched)
            else:
                chunk["incident_boost_applied"] = False
                chunk["matched_incident_nodes"] = []

            # 청크 text 기반 추가 boost (응급 대응 키워드 매칭).
            chunk_text = chunk.get("text") or ""
            matched_keywords = [kw for kw in EMERGENCY_KEYWORDS if kw in chunk_text]
            if matched_keywords:
                chunk["rrf_score"] = (chunk.get("rrf_score") or 0.0) + EMERGENCY_CHUNK_BOOST
                chunk["emergency_chunk_boost_applied"] = True
                chunk["matched_emergency_keywords"] = matched_keywords
            else:
                chunk["emergency_chunk_boost_applied"] = False
                chunk["matched_emergency_keywords"] = []

            # chunk-level incident_nodes 매칭 (force-include 가 채워뒀거나,
            # 향후 일반 청크에도 태그된 경우 둘 다 커버).
            chunk_nodes = set(chunk.get("chunk_incident_nodes") or [])
            chunk_matched = chunk_nodes & user_incident_nodes
            if chunk_matched:
                chunk["rrf_score"] = (chunk.get("rrf_score") or 0.0) + INCIDENT_BOOST
                chunk["chunk_incident_boost_applied"] = True
                chunk["matched_chunk_incident_nodes"] = sorted(chunk_matched)
            else:
                chunk["chunk_incident_boost_applied"] = False
                chunk["matched_chunk_incident_nodes"] = []

            # Force-included 청크는 base rrf_score=0 이므로 top-5 진입 보장 위해 큰 가산.
            if chunk.get("force_included"):
                chunk["rrf_score"] = (chunk.get("rrf_score") or 0.0) + EMERGENCY_FORCE_INCLUDE_BOOST
            # Intent force-include 청크에도 별도 가산 (top-15 안에 진입 가능하도록).
            if chunk.get("force_included_by_intent"):
                chunk["rrf_score"] = (chunk.get("rrf_score") or 0.0) + FORCE_INCLUDE_DOC_BOOST

        # 4) boost 후 재정렬 + doc-level diversity cap (동일 doc 최대 N개).
        raw_chunks.sort(key=lambda c: c.get("rrf_score") or 0.0, reverse=True)
        MAX_CHUNKS_PER_DOC = 2
        TOP_K = 5
        final_rows: list = []
        doc_count: dict = {}
        for chunk in raw_chunks:
            doc_id = chunk.get("document_id") or ""
            if doc_count.get(doc_id, 0) >= MAX_CHUNKS_PER_DOC:
                continue
            final_rows.append(chunk)
            doc_count[doc_id] = doc_count.get(doc_id, 0) + 1
            if len(final_rows) >= TOP_K:
                break
        # 부족하면 cap 무시하고 채움 (안전장치 — 단일 doc 만 hit 한 케이스).
        if len(final_rows) < TOP_K:
            seen_ids = {c.get("id") for c in final_rows}
            for chunk in raw_chunks:
                if chunk.get("id") in seen_ids:
                    continue
                final_rows.append(chunk)
                if len(final_rows) >= TOP_K:
                    break
        return [_normalize_v2_row(r) for r in final_rows]

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
