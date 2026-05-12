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

import sys
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
# v2: 0.20 → 0.50 (top-5 진입 확실 보장).
FORCE_INCLUDE_DOC_BOOST: float = 0.50

# Layer 3 (hardcoded title-based whitelist) — RPC + direct table 둘 다 실패 시
# 최후 안전망. user_incident_nodes 의 도메인 분류 후 해당 whitelist 만 매칭.
# 운영 중 신규 doc 추가되면 본 dict 업데이트 (Layer 1/2 정상 동작 시 미사용).
# PR-Fix-L3-Domain-Split: 윤리 질문이 사건사고 SOP 만 retrieve 하는 회귀 해결.
L3_FALLBACK_BY_DOMAIN: dict = {
    "incident": (
        "AEO 출입통제",
        "매장 안전보건관리 지침",
        "안전보건관리규정",
        "일반 사건사고 보고지침",
        "중대 사건사고 보고지침",
        "중대재해 대응 지침",
        "사건, 부적합 시정조치 지침",
    ),
    "ethics": (
        "신세계그룹 CREDO",
        "임직원 징계기준",
        "클린뱅크 운영 지침",
    ),
}

# user_incident_nodes (Gemini classifier AVAILABLE_INCIDENT_NODES + rule_based
# fallback nexus_query_rewriter 노드 union) → 도메인 매핑.
# 미정의 노드는 L3 매칭 시 양쪽 union (안전 fallback).
INCIDENT_NODE_TO_DOMAIN: dict = {
    # 사건사고·안전 도메인
    "사건사고보고": "incident",
    "인사사고": "incident",
    "고객상해": "incident",
    "정보유출": "incident",
    "근로자안전": "incident",
    "직원상해": "incident",
    "매장사고": "incident",
    "응급대응": "incident",
    "안전관리": "incident",
    "시설안전": "incident",
    # 윤리·금품·CSR 도메인 (Gemini classifier 노드)
    "윤리보고": "ethics",
    "윤리위반": "ethics",
    "비위행위": "ethics",
    "횡령": "ethics",
    "배임": "ethics",
    "금전사고": "ethics",
    "절도": "ethics",
    "성희롱": "ethics",
    "괴롭힘": "ethics",
    # nexus_query_rewriter rule_based fallback 노드 (line 354~360 참고)
    "조직관리": "ethics",
    "횡령수수": "ethics",
    "거래행위": "ethics",
    "부정계산": "ethics",
    "부정적립": "ethics",
    "직원절취": "ethics",
    "고객관리": "ethics",
    "고객절취": "ethics",
    "불공정행위": "ethics",
    "거래관리": "ethics",
}

# 절차 키워드 — 매장 사고 응급/보고/분류 전반 (best chunk 선정용).
# 청크가 본 키워드를 많이 포함할수록 절차 청크로 간주 → relevance-aware
# best chunk per doc 선정에 활용.
PROCEDURE_KEYWORDS: tuple = (
    # 응급 대응
    "응급조치", "응급 조치", "병원 후송", "병원후송", "보안실", "현장 보존",
    "현장보존", "응급구호", "응급 구호", "구급",
    # 보고 절차
    "신고", "보고", "유선보고", "유선 보고", "구두보고", "SRMS", "정식 보고",
    "사건사고 보고", "사고 보고", "1차 보고", "2차 보고",
    # 시한
    "24시간", "12시간", "2시간 이내", "즉시 보고", "즉시 인지", "최초 인지자",
    # 분류
    "고객상해", "인사사고", "중대 사건사고", "일반 사건사고", "사고 분류",
    "중대재해", "인명사고",
    # 부서·역할
    "CSR팀", "관리감독자", "안전보건 담당", "안전관리 책임자", "점장",
    "본사 지원부서",
    # 매장 사고 mechanism
    "매장 안전사고", "낙상", "전도", "추락", "매장 내 사고", "시설물",
)
# 청크 키워드 1개당 rrf_score 가산 — best chunk selection 결정성 유지하면서
# tiebreaker 역할 (절차 키워드 많은 청크 우선).
PROCEDURE_KEYWORD_WEIGHT: float = 0.01

# Universal Incident SOP — 모든 사건사고 적용 (사용자 통찰 2026-05-11).
# 일반/중대 사건사고 보고지침 청크에 분류/판정/시한/절차 모두 명시됨.
UNIVERSAL_INCIDENT_SOP_TITLES: set = {
    "(공통) 일반 사건사고 보고지침",
    "(공통) 중대 사건사고 보고지침",
}

# Universal SOP 도큐먼트는 chunk 0 + 1 양쪽 모두 top-K 강제 포함
# (MAX_CHUNKS_PER_DOC cap 우회). 분류+판정 / 시한+절차 가 각각 분리된 청크라
# 1개만으로는 답변의 4단계 구조 미완성. phrasing 별 chunk 선택 변동 차단.
UNIVERSAL_SOP_REQUIRED_CHUNK_INDICES: set = {0, 1}


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
        "force_include_source": row.get("force_include_source") or "",
        "is_universal_sop": bool(row.get("is_universal_sop")),
        "chunk_incident_boost_applied": bool(row.get("chunk_incident_boost_applied")),
        "matched_chunk_incident_nodes": row.get("matched_chunk_incident_nodes") or [],
        "procedure_keyword_count": int(row.get("procedure_keyword_count") or 0),
        "matched_procedure_keywords": row.get("matched_procedure_keywords") or [],
        "enrichment": row.get("enrichment") or "",
    }


def _ensure_universal_sop_completeness(
    top_k_chunks: list,
    all_force_chunks: list,
) -> list:
    """Universal SOP 도큐먼트의 모든 chunks 를 final 결과에 포함.

    근거 (PR #89 DEBUG): Layer 1 RPC 가 chunk_idx 미반환 → chunk index
    기반 필터 불가. Universal SOP 도큐먼트는 작은 doc (일반 4 chunks /
    중대 3 chunks) 이라 모두 포함해도 LLM 컨텍스트 부담 minimal.
    효과: 4 phrasing 동일 chunk set → 동일 답변 (신뢰성 4/4).

    UNIVERSAL_SOP_REQUIRED_CHUNK_INDICES 상수는 호환성 유지 위해 잔존 (미사용).
    """
    if not all_force_chunks:
        print(
            "[retriever:universal_sop:enrichment] SKIP empty raw_chunks",
            file=sys.stderr, flush=True,
        )
        return list(top_k_chunks)

    out = list(top_k_chunks)
    existing_chunk_ids: set = set()
    for c in out:
        if not isinstance(c, dict):
            continue
        cid = c.get("id") or c.get("chunk_id")
        if cid:
            existing_chunk_ids.add(cid)

    added_count = 0
    sop_doc_counts: dict = {}

    for chunk in all_force_chunks:
        if not isinstance(chunk, dict):
            continue
        doc_title = (
            chunk.get("doc_title")
            or chunk.get("title")
            or chunk.get("document_title")
            or ""
        )
        if doc_title not in UNIVERSAL_INCIDENT_SOP_TITLES:
            continue
        chunk_id = chunk.get("id") or chunk.get("chunk_id")
        if chunk_id and chunk_id in existing_chunk_ids:
            continue
        enriched = dict(chunk)
        enriched["enrichment"] = "universal_sop_completeness"
        enriched["is_universal_sop"] = True
        enriched["doc_title"] = doc_title
        out.append(enriched)
        if chunk_id:
            existing_chunk_ids.add(chunk_id)
        added_count += 1
        sop_doc_counts[doc_title] = sop_doc_counts.get(doc_title, 0) + 1

    print(
        f"[retriever:universal_sop:enrichment] "
        f"added={added_count} per_doc={sop_doc_counts} "
        f"final_chunks={len(out)}",
        file=sys.stderr, flush=True,
    )
    return out


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

        # 1.4) Track C v2 — Triple-layer fallback force-include.
        # Layer 1: SQL RPC (intersect SQL-side, 가장 신뢰)
        # Layer 2: Direct table query (RPC 미배포/실패 시)
        # Layer 3: Hardcoded title-based whitelist (둘 다 실패 시 최후 안전망)
        if user_incident_nodes:
            nodes_list = sorted(user_incident_nodes)
            force_chunks_raw: list = []
            force_include_source: str = "none"
            _doc_meta_enrich: dict = {}

            # ── Layer 1: SQL RPC ─────────────────────────────
            try:
                force_resp = supabase.rpc(
                    "nexus_force_include_chunks_by_incident_nodes",
                    {"p_nodes": nodes_list},
                ).execute()
                force_chunks_raw = force_resp.data or []
                if force_chunks_raw:
                    force_include_source = "rpc"
                print(
                    f"[retriever:force_include:L1_RPC] nodes={nodes_list} "
                    f"returned={len(force_chunks_raw)}",
                    file=sys.stderr, flush=True,
                )
            except Exception as e:
                print(
                    f"[retriever:force_include:L1_RPC] FAILED: "
                    f"{type(e).__name__}: {e}",
                    file=sys.stderr, flush=True,
                )

            # ── Layer 2: Direct table query ─────────────────
            if not force_chunks_raw:
                try:
                    docs_resp = (
                        supabase.table("nexus_documents")
                        .select("id, title, doc_kind, meta")
                        .eq("status", "active")
                        .execute()
                    )
                    all_docs = docs_resp.data or []
                    print(
                        f"[retriever:force_include:L2_DIRECT] "
                        f"active_docs_fetched={len(all_docs)}",
                        file=sys.stderr, flush=True,
                    )
                    matched_doc_ids: list = []
                    for doc in all_docs:
                        doc_meta = doc.get("meta")
                        if isinstance(doc_meta, str):
                            try:
                                import json as _json
                                doc_meta = _json.loads(doc_meta)
                            except Exception:
                                continue
                        if not isinstance(doc_meta, dict):
                            continue
                        doc_nodes_raw = doc_meta.get("incident_nodes") or []
                        if not isinstance(doc_nodes_raw, list):
                            continue
                        if set(doc_nodes_raw) & user_incident_nodes:
                            matched_doc_ids.append(doc["id"])
                            _doc_meta_enrich[doc["id"]] = doc
                    print(
                        f"[retriever:force_include:L2_DIRECT] "
                        f"matched_doc_ids={len(matched_doc_ids)}",
                        file=sys.stderr, flush=True,
                    )
                    if matched_doc_ids:
                        chunks_resp = (
                            supabase.table("nexus_chunks")
                            .select("id, document_id, chunk_idx, article_no, text")
                            .in_("document_id", matched_doc_ids)
                            .execute()
                        )
                        force_chunks_raw = chunks_resp.data or []
                        if force_chunks_raw:
                            force_include_source = "direct_table"
                        print(
                            f"[retriever:force_include:L2_DIRECT] "
                            f"chunks_fetched={len(force_chunks_raw)}",
                            file=sys.stderr, flush=True,
                        )
                except Exception as e:
                    print(
                        f"[retriever:force_include:L2_DIRECT] FAILED: "
                        f"{type(e).__name__}: {e}",
                        file=sys.stderr, flush=True,
                    )

            # ── Layer 3: Hardcoded title whitelist ──────────
            if not force_chunks_raw:
                try:
                    print(
                        "[retriever:force_include:L3_HARDCODED] "
                        "entering last-resort fallback",
                        file=sys.stderr, flush=True,
                    )
                    docs_resp = (
                        supabase.table("nexus_documents")
                        .select("id, title, doc_kind")
                        .eq("status", "active")
                        .execute()
                    )
                    all_docs = docs_resp.data or []
                    matched_doc_ids = []
                    # PR-Fix-L3-Domain-Split: user_incident_nodes 의 도메인 분류
                    # → 해당 whitelist 만 매칭. 윤리 노드면 윤리 사규 whitelist,
                    # 사건사고 노드면 기존 사건사고/안전 whitelist. 미매핑 노드는
                    # 양쪽 union (안전 fallback).
                    _domains: set = set()
                    for _node in user_incident_nodes:
                        _d = INCIDENT_NODE_TO_DOMAIN.get(_node)
                        if _d:
                            _domains.add(_d)
                    if not _domains:
                        _domains = set(L3_FALLBACK_BY_DOMAIN.keys())
                    _active_titles: set = set()
                    for _d in _domains:
                        _active_titles |= set(L3_FALLBACK_BY_DOMAIN.get(_d, ()))
                    print(
                        f"[retriever:force_include:L3_HARDCODED] "
                        f"domains={sorted(_domains)} whitelist_size={len(_active_titles)}",
                        file=sys.stderr, flush=True,
                    )
                    for doc in all_docs:
                        title = doc.get("title") or ""
                        for known in _active_titles:
                            if known in title:
                                matched_doc_ids.append(doc["id"])
                                _doc_meta_enrich[doc["id"]] = doc
                                break
                    print(
                        f"[retriever:force_include:L3_HARDCODED] "
                        f"matched_via_title={len(matched_doc_ids)}",
                        file=sys.stderr, flush=True,
                    )
                    if matched_doc_ids:
                        chunks_resp = (
                            supabase.table("nexus_chunks")
                            .select("id, document_id, chunk_idx, article_no, text")
                            .in_("document_id", matched_doc_ids)
                            .execute()
                        )
                        force_chunks_raw = chunks_resp.data or []
                        if force_chunks_raw:
                            force_include_source = "hardcoded_whitelist"
                except Exception as e:
                    print(
                        f"[retriever:force_include:L3_HARDCODED] FAILED: "
                        f"{type(e).__name__}: {e}",
                        file=sys.stderr, flush=True,
                    )

            # ── Union into raw_chunks (dedup by chunk id) ───
            existing_chunk_ids = {c.get("id") for c in raw_chunks if c.get("id")}
            added_count = 0
            skipped_count = 0
            for fc in force_chunks_raw:
                if fc.get("id") in existing_chunk_ids:
                    skipped_count += 1
                    continue
                _doc = _doc_meta_enrich.get(fc.get("document_id"), {}) or {}
                _title = fc.get("doc_title") or _doc.get("title") or ""
                raw_chunks.append({
                    "id": fc.get("id"),
                    "document_id": fc.get("document_id"),
                    "doc_title": _title,
                    "doc_kind": _doc.get("doc_kind"),
                    "article_no": fc.get("article_no"),
                    "text": fc.get("text") or "",
                    "categories": fc.get("categories") or [],
                    "chunk_incident_nodes": fc.get("chunk_incident_nodes") or [],
                    "rrf_score": 0.0,
                    "force_included_by_intent": True,
                    "force_include_source": force_include_source,
                    "is_universal_sop": _title in UNIVERSAL_INCIDENT_SOP_TITLES,
                })
                added_count += 1
            print(
                f"[retriever:force_include:FINAL] source={force_include_source} "
                f"total_force_chunks={len(force_chunks_raw)} "
                f"added={added_count} skipped_duplicates={skipped_count}",
                file=sys.stderr, flush=True,
            )

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
                    _title = d.get("title") or ""
                    raw_chunks.append({
                        "id": ec.get("id"),
                        "document_id": ec.get("document_id"),
                        "doc_title": _title,
                        "doc_kind": d.get("doc_kind"),
                        "article_no": ec.get("article_no"),
                        "text": ec.get("text") or "",
                        "categories": ec.get("categories") or [],
                        "chunk_incident_nodes": ec.get("chunk_incident_nodes") or [],
                        "rrf_score": 0.0,
                        "force_included": True,
                        "is_universal_sop": _title in UNIVERSAL_INCIDENT_SOP_TITLES,
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

            # Relevance-aware: 절차 키워드 매칭 수 측정 + 약한 rrf 가산.
            # best_chunk_per_doc 선정 시 절차 청크가 intro 청크보다 우선되도록.
            proc_matches = [kw for kw in PROCEDURE_KEYWORDS if kw in chunk_text]
            chunk["procedure_keyword_count"] = len(proc_matches)
            chunk["matched_procedure_keywords"] = proc_matches
            if proc_matches:
                chunk["rrf_score"] = (
                    (chunk.get("rrf_score") or 0.0)
                    + PROCEDURE_KEYWORD_WEIGHT * len(proc_matches)
                )

        # 4) Deterministic Top-K Selection (PR #81)
        # 정렬: rrf_score 내림차순 + chunk_id 사전순 (UUID — 항상 동일 결과).
        MAX_CHUNKS_PER_DOC = 2
        TOP_K = 5
        raw_chunks.sort(
            key=lambda c: (
                -(c.get("rrf_score") or 0.0),
                -(c.get("procedure_keyword_count") or 0),
                str(c.get("id") or ""),
            )
        )

        # 4-1) 매칭 doc 별 대표 chunk (sort 후 첫 발견 = best score chunk).
        best_chunk_per_doc: dict = {}
        for chunk in raw_chunks:
            if not chunk.get("force_included_by_intent"):
                continue
            doc_id = chunk.get("document_id") or ""
            if not doc_id or doc_id in best_chunk_per_doc:
                continue
            best_chunk_per_doc[doc_id] = chunk

        matched_doc_count = len(best_chunk_per_doc)
        guaranteed_chunks = list(best_chunk_per_doc.values())
        # guaranteed_chunks 도 결정적 정렬 (rrf desc + chunk_id asc).
        guaranteed_chunks.sort(
            key=lambda c: (
                -(c.get("rrf_score") or 0.0),
                -(c.get("procedure_keyword_count") or 0),
                str(c.get("id") or ""),
            )
        )
        # 매칭 doc 가 TOP_K 보다 많으면 점수 순 cap (방어 코드).
        guaranteed_chunks = guaranteed_chunks[:TOP_K]

        # 4-2) final 초기화 — 매칭 doc 대표 chunk 우선 등록 (TOP_K 전체 활용).
        final_rows: list = list(guaranteed_chunks)
        final_chunk_ids: set = {c.get("id") for c in final_rows if c.get("id")}
        doc_count_in_final: dict = {}
        for c in final_rows:
            doc_id = c.get("document_id") or ""
            doc_count_in_final[doc_id] = doc_count_in_final.get(doc_id, 0) + 1

        # 4-3) 남은 슬롯을 일반 chunk 로 채움 (diversity cap 적용).
        for chunk in raw_chunks:
            if len(final_rows) >= TOP_K:
                break
            if chunk.get("id") in final_chunk_ids:
                continue
            doc_id = chunk.get("document_id") or ""
            if doc_count_in_final.get(doc_id, 0) >= MAX_CHUNKS_PER_DOC:
                continue
            final_rows.append(chunk)
            final_chunk_ids.add(chunk.get("id"))
            doc_count_in_final[doc_id] = doc_count_in_final.get(doc_id, 0) + 1

        # 4-4) 안전망 — 여전히 부족하면 cap 무시 채움.
        for chunk in raw_chunks:
            if len(final_rows) >= TOP_K:
                break
            if chunk.get("id") in final_chunk_ids:
                continue
            final_rows.append(chunk)
            final_chunk_ids.add(chunk.get("id"))

        # 4-5) 진단 로깅.
        unique_final_docs = {
            c.get("document_id") for c in final_rows if c.get("document_id")
        }
        final_doc_dist: dict = {}
        for c in final_rows:
            d = c.get("document_id") or "?"
            final_doc_dist[d] = final_doc_dist.get(d, 0) + 1
        print(
            f"[retriever:top_k_selection] "
            f"matched_docs={matched_doc_count} "
            f"guaranteed_in_top_k={len(guaranteed_chunks)} "
            f"final_chunks={len(final_rows)} "
            f"final_unique_docs={len(unique_final_docs)} "
            f"top_k={TOP_K} "
            f"max_per_doc={MAX_CHUNKS_PER_DOC}",
            file=sys.stderr, flush=True,
        )
        print(
            f"[retriever:procedure_score] "
            f"total_chunks_with_proc_match="
            f"{sum(1 for c in raw_chunks if (c.get('procedure_keyword_count') or 0) > 0)} "
            f"max_proc_match_in_top5="
            f"{max((c.get('procedure_keyword_count') or 0 for c in final_rows), default=0)}",
            file=sys.stderr, flush=True,
        )
        universal_sop_titles_in_top = sorted({
            c.get("doc_title", "?") for c in final_rows if c.get("is_universal_sop")
        })
        print(
            f"[retriever:universal_sop] "
            f"in_top_k={sum(1 for c in final_rows if c.get('is_universal_sop'))} "
            f"titles={universal_sop_titles_in_top}",
            file=sys.stderr, flush=True,
        )

        # 4-6) 매칭 doc 누락 감지 (있으면 코드 버그).
        all_force_doc_ids = {
            c.get("document_id")
            for c in raw_chunks
            if c.get("force_included_by_intent") and c.get("document_id")
        }
        dropped_matched_docs = all_force_doc_ids - unique_final_docs
        if dropped_matched_docs:
            print(
                f"[retriever:top_k_selection] WARNING: "
                f"{len(dropped_matched_docs)} matched doc(s) dropped from top-K: "
                f"{list(dropped_matched_docs)[:5]}",
                file=sys.stderr, flush=True,
            )

        # PR #88 — Universal SOP completeness: chunk 0+1 둘 다 강제 합류
        # (cap 우회). all_force_chunks = raw_chunks (force-included 청크 전체 풀).
        final_rows = _ensure_universal_sop_completeness(
            final_rows, raw_chunks,
        )
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
