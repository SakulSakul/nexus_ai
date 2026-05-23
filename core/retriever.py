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

import re
import sys
from typing import Any

from .config import settings
from .embedder import embed_one


# PR-Fix-Domain-Bias: 문서 제목 prefix 도메인 추출 — 예 "(안전) 매장 안전보건..."
# → "안전". per-domain cap 안전망의 단일 source of truth.
_DOMAIN_PREFIX_RE = re.compile(r"^\s*\(([^)]+)\)")


def _chunk_domain(chunk: dict) -> str:
    """문서 제목 prefix 의 도메인 라벨 반환. 없으면 빈 문자열."""
    title = chunk.get("doc_title") or ""
    m = _DOMAIN_PREFIX_RE.match(title)
    return m.group(1).strip() if m else ""


# Tier 1 + Tier 2 활성화 토글. False 면 즉시 기존 RPC 경로로 롤백.
# 2026-05-11 핫픽스: rewriter 1글자 절단 버그 수정 검증 전까지 False 유지.
# admin "🔬 검색 비교" 패널에서 사용자가 raw vs cleaned 확인 후 True 로 복귀.
USE_HYBRID_SEARCH: bool = True
USE_REWRITER: bool = False  # PR-Disable-Rewriter-Default: testset 분석 결과 평균 -98 query (악화 4배)

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
    # PR-Fix-ForceInclude-Domain-Expand: (환경) 도메인 — 환경 사고/사건/위반·
    # 비상시 대응 query 에 (환경) doc force_include 보장.
    # PR-Retrieval-Hunt-B: 녹색구매·환경운영관리 추가 (active rule docs 점검).
    "environment": (
        "비상시대비",       # (환경) 비상시대비대응 / 비상시대비 절차 매칭
        "환경 사건",        # (환경) 환경 사건/시정조치 매칭
        "환경경영",         # (환경) 환경경영매뉴얼 / 환경경영 매뉴얼 매칭
        "녹색 구매",        # (환경) 녹색 구매 지침 매칭
        "환경운영관리",     # (환경) 환경운영관리 지침 매칭
    ),
    # PR-Fix-ForceInclude-Domain-Expand: (총무) 도메인 — 인감·인장·도장
    # 도용/위조 query 에 (총무) 인감 관리지침 force_include 보장.
    "total_affairs": (
        "인감 관리",   # (총무) 인감 관리지침 / 인감 관리 지침 매칭
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
    # PR-Fix-Domain-Synth: 성희롱/괴롭힘 은 사건사고 보고 절차 (일반/중대 사건사고 보고지침) 적용 대상.
    "성희롱": "incident",
    "괴롭힘": "incident",
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
    # PR-Fix-ForceInclude-Domain-Expand: 환경/총무 도메인 nodes.
    # nexus_query_rewriter._NEXUS_NL_TO_INCIDENT_NODES 의 신규 trigger 와
    # L3_FALLBACK_BY_DOMAIN environment/total_affairs whitelist 연계.
    "환경사고": "environment",
    "환경위반": "environment",
    "환경경영": "environment",
    "비상시대비": "environment",
    "인감관리": "total_affairs",
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


# PR-Stage-A-2-Shadow-V2: 일반 단어 stop-word
# PR-Stage-A-2-Shadow 첫 운영 검증에서 발견된 false positive 원인 단어들.
# 거의 모든 사규에 공통 등장하여 매칭 신호 가치 0 (TF-IDF 의 IDF 매우 낮음).
# 차후 PR-Stage-A-2-StopWord-Auto 에서 DF 기반 자동 검출 시스템.
SHADOW_STOP_KEYWORDS: set[str] = {
    # PR-Stage-A-2-Shadow-V2: 거의 모든 사규에 공통 등장하는 일반 단어
    "이해관계자",
    "CSR",
    "관리",
    "경영",
    "환경",
    "안전관리",
    "리스크관리",
    # PR-Stage-A-2-Shadow-V3: 의미 혼동 단어 ("수수" received vs "수수료" commission)
    "수수료",
    "판매수수료",
    "수수료 조정",
}


def _score_keywords_against_query(
    keywords: list,
    combined_query: str,
    query_words: set,
    direct_weight: int,
    partial_weight: int,
) -> tuple:
    """keyword list 의 매칭 score + matched list 계산.

    direct_weight: 직접 매칭 (keyword in combined_query) 점수
    partial_weight: 부분 매칭 (query word in keyword) 점수
    3글자 미만 keyword + stop-word 제외.
    """
    score = 0
    matched: list = []
    for kw in keywords or []:
        if not isinstance(kw, str):
            continue
        kw_stripped = kw.strip()
        if len(kw_stripped) < 2 or kw_stripped in SHADOW_STOP_KEYWORDS:
            continue
        kw_lower = kw_stripped.lower()
        # (a) 직접 매칭 (keyword in query)
        if kw_lower in combined_query:
            score += direct_weight
            matched.append(kw_stripped)
            continue
        # (b) 부분 매칭 (query word in keyword)
        for word in query_words:
            if word in kw_lower:
                score += partial_weight
                matched.append(kw_stripped)
                break
    return score, matched


def _title_base(title: str) -> str:
    """사규명에서 도메인 prefix '(...)' 제거. '(안전) 법인카드 관리지침' → '법인카드 관리지침'."""
    if not title:
        return ""
    m = re.match(r"^\(([^)]+)\)\s*(.+)$", title.strip())
    return (m.group(2).strip() if m else title.strip())


def _compute_title_direct_matches(supabase: Any, question: str) -> list[str]:
    """PR-Title-Direct-Match: 사규명 base 와 query 의 직접 매칭 doc id 반환.

    3 매칭 방식:
    1. title_compact in query_compact (사규명이 query 에 등장)
    2. query_compact in title_compact (query 가 사규명에 등장)
    3. token 공통 3개+ (사규명 token 과 query token 교집합 >= 3)
    """
    try:
        if supabase is None:
            return []
        docs_result = (
            supabase.table("nexus_documents")
            .select("id, title")
            .eq("status", "active")
            .execute()
        )
        docs = docs_result.data or []

        q = question or ""
        q_compact = "".join(q.split()).lower()
        q_tokens = {t.lower() for t in q.split() if len(t) >= 2}

        matched_ids: list[str] = []
        for doc in docs:
            base = _title_base(doc.get("title") or "")
            if not base:
                continue
            t_compact = "".join(base.split()).lower()
            if len(t_compact) < 4:
                continue  # 너무 짧은 사규명은 trivial 매칭 위험 — skip
            t_tokens = {t.lower() for t in base.split() if len(t) >= 2}

            hit = False
            # 1. 사규명이 query 에 등장
            if t_compact in q_compact:
                hit = True
            # 2. query 가 사규명에 등장
            elif q_compact and q_compact in t_compact:
                hit = True
            # 3. token 공통 3개 이상
            elif len(q_tokens & t_tokens) >= 3:
                hit = True

            if hit:
                matched_ids.append(doc.get("id"))

        return matched_ids
    except Exception as e:
        print(
            f"[_compute_title_direct_matches] FAILED: {type(e).__name__}: {e}",
            file=sys.stderr, flush=True,
        )
        return []


def _compute_v3_matches(
    supabase: Any,
    question: str,
    retrieval_query_text: str,
) -> list:
    """V3 매칭 candidates 계산 + return (PR-Stage-A-2-Production).

    shadow log 함수와 동일 매칭 로직 — 다만 return list 만, log 없음.
    Production force_include 에서 호출 + 별도 shadow log 함수가 모니터링 유지.

    Returns: [{id, title, total, doc_score, chunk_score, top_chunk_idxs}, ...]
    """
    try:
        if supabase is None:
            return []

        docs_result = (
            supabase.table("nexus_documents")
            .select("id, title, auto_keywords")
            .eq("status", "active")
            .execute()
        )
        docs = docs_result.data or []
        docs_by_id = {d.get("id"): d for d in docs}

        chunks_result = (
            supabase.table("nexus_chunks")
            .select("id, document_id, chunk_idx, auto_keywords")
            .execute()
        )
        all_chunks = chunks_result.data or []
        chunks = [c for c in all_chunks if c.get("document_id") in docs_by_id]

        combined = ((question or "") + " " + (retrieval_query_text or "")).lower()

        query_words: set = set()
        for token in combined.replace("?", " ").replace(".", " ").replace(",", " ").split():
            if len(token) >= 3 and token not in SHADOW_STOP_KEYWORDS:
                query_words.add(token)

        doc_scores: dict = {}
        for doc in docs:
            doc_id = doc.get("id")
            score, _matched = _score_keywords_against_query(
                doc.get("auto_keywords") or [],
                combined, query_words,
                direct_weight=2, partial_weight=1,
            )
            doc_scores[doc_id] = {
                "title": doc.get("title") or "",
                "doc_score": score,
                "chunk_score": 0,
                "top_chunks": [],
            }

        for chunk in chunks:
            doc_id = chunk.get("document_id")
            if doc_id not in doc_scores:
                continue
            score, _matched = _score_keywords_against_query(
                chunk.get("auto_keywords") or [],
                combined, query_words,
                direct_weight=3, partial_weight=2,
            )
            if score > 0:
                doc_scores[doc_id]["chunk_score"] += score
                doc_scores[doc_id]["top_chunks"].append({
                    "chunk_idx": chunk.get("chunk_idx"),
                    "score": score,
                })

        scored = []
        for doc_id, info in doc_scores.items():
            total = info["doc_score"] + info["chunk_score"]
            if total >= 3:
                info["top_chunks"].sort(key=lambda c: -c["score"])
                scored.append({
                    "id": doc_id,
                    "title": info["title"],
                    "total": total,
                    "doc_score": info["doc_score"],
                    "chunk_score": info["chunk_score"],
                    "top_chunk_idxs": [c["chunk_idx"] for c in info["top_chunks"]],
                })

        scored.sort(key=lambda d: -d["total"])
        return scored
    except Exception as e:
        print(
            f"[_compute_v3_matches] FAILED: {type(e).__name__}: {e}",
            file=sys.stderr, flush=True,
        )
        return []


def _shadow_log_auto_keywords_match(
    supabase: Any,
    question: str,
    retrieval_query_text: str,
    log_prefix: str = "",
) -> None:
    """L2.5_AUTO_KEYWORDS shadow log V3 (PR-Stage-A-2-Shadow-V3).

    docs.auto_keywords + chunks.auto_keywords (PR-Stage-A-1-Chunk) 통합 매칭.
    실제 retrieve 결과 영향 0 — log only.

    V3 개선:
    - chunk-level 매칭 추가 (doc-level 의 본질적 한계 해결)
    - 점수: doc 직접 2점/부분 1점, chunk 직접 3점/부분 2점 (chunk 가 더 specific)
    - 부분 매칭 길이 임계값 3글자 이상 (V2 의 "수수/수수료" false positive fix)
    - 추가 stop-word (수수료/판매수수료 등 의미 혼동)
    - 임계값 total >= 3 (정확성 ↑)
    - log 보강 (chunk_idx + matched 상세)
    """
    try:
        if supabase is None:
            return

        # doc-level fetch
        docs_result = (
            supabase.table("nexus_documents")
            .select("id, title, auto_keywords")
            .eq("status", "active")
            .execute()
        )
        docs = docs_result.data or []
        docs_by_id = {d.get("id"): d for d in docs}

        # chunk-level fetch (PR-Stage-A-1-Chunk 의 nexus_chunks.auto_keywords)
        chunks_result = (
            supabase.table("nexus_chunks")
            .select("id, document_id, chunk_idx, auto_keywords")
            .execute()
        )
        all_chunks = chunks_result.data or []
        # active doc 의 chunk 만 필터
        chunks = [c for c in all_chunks if c.get("document_id") in docs_by_id]

        # query normalization
        combined = ((question or "") + " " + (retrieval_query_text or "")).lower()

        # query 의 의미 단어 (3글자 이상 — V3 fix, stop-word 제외)
        query_words: set = set()
        for token in combined.replace("?", " ").replace(".", " ").replace(",", " ").split():
            if len(token) >= 3 and token not in SHADOW_STOP_KEYWORDS:
                query_words.add(token)

        # doc 별 score 누적 (doc-level + chunk-level 통합)
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
                "doc_matched": matched,
                "chunk_score": 0,
                "chunk_matched": [],
            }

        # chunk-level scoring (점수 가중: doc + 1)
        for chunk in chunks:
            doc_id = chunk.get("document_id")
            if doc_id not in doc_scores:
                continue
            score, matched = _score_keywords_against_query(
                chunk.get("auto_keywords") or [],
                combined, query_words,
                direct_weight=3, partial_weight=2,
            )
            if score > 0:
                doc_scores[doc_id]["chunk_score"] += score
                doc_scores[doc_id]["chunk_matched"].append({
                    "chunk_idx": chunk.get("chunk_idx"),
                    "score": score,
                    "matched": matched[:3],
                })

        # 임계값: total >= 3 만 후보
        scored: list = []
        for doc_id, info in doc_scores.items():
            total = info["doc_score"] + info["chunk_score"]
            if total >= 3:
                info["chunk_matched"].sort(key=lambda c: -c["score"])
                scored.append({
                    "id": doc_id,
                    "title": info["title"],
                    "total": total,
                    "doc_score": info["doc_score"],
                    "chunk_score": info["chunk_score"],
                    "doc_matched": info["doc_matched"][:5],
                    "top_chunks": info["chunk_matched"][:3],
                })

        # total 내림차순 정렬
        scored.sort(key=lambda d: -d["total"])

        # log: top-5 상세
        top5 = scored[:5]
        details = []
        for d in top5:
            chunk_summary = [
                f"ch{c['chunk_idx']}({c['score']})"
                for c in d["top_chunks"]
            ]
            details.append(
                f"{{doc: '{d['title'][:30]}', "
                f"total: {d['total']} (doc={d['doc_score']}+chunk={d['chunk_score']}), "
                f"doc_kws: {d['doc_matched'][:3]}, "
                f"chunks: [{','.join(chunk_summary)}]}}"
            )
        print(
            f"[retriever:L2.5_shadow_v3]{log_prefix} "
            f"q_head='{(question or '')[:50]}' "
            f"candidates={len(scored)} "
            f"top5=[{', '.join(details)}]",
            flush=True,
        )
    except Exception as e:
        print(
            f"[retriever:L2.5_shadow_v3] FAILED: {type(e).__name__}: {e}",
            file=sys.stderr, flush=True,
        )


def hybrid_search(
    supabase: Any,
    *,
    question: str,
    categories: list[str] | None,
    doc_kinds: list[str] | None = None,
    top_k: int | None = None,
    progress_callback=None,
) -> list[dict]:
    """PR-UI-Sub-Stage-Visualization: progress_callback(stage, payload).
    각 sub-stage 의 elapsed_ms / metadata 를 emit 하여 UI 의 sub-message
    표시. None 인 경우 emit 무시 (회귀 안전).
    """
    import time as _t_subprog
    def _emit_sub(stage: str, payload: dict | None = None) -> None:
        if progress_callback is None:
            return
        try:
            progress_callback(stage, payload or {})
        except Exception:
            pass
    s = settings()
    if USE_HYBRID_SEARCH:
        # Tier 1 — 사규 용어 확장. 실패 시 원문 반환 (raise 안 함).
        from .nexus_query_rewriter import (
            rewrite_query_for_retrieval,
            nexus_build_keyword_tsquery,
            nexus_classify_to_incident_nodes,
        )
        _t_rewrite0 = _t_subprog.perf_counter()
        # PR-Disable-Rewriter-Default: production retrieval 의 rewriter 비활성화
        if USE_REWRITER:
            retrieval_query_text = rewrite_query_for_retrieval(question)
        else:
            retrieval_query_text = question
        _emit_sub("search_rewrite_done", {
            "elapsed_ms": int((_t_subprog.perf_counter() - _t_rewrite0) * 1000),
            "rewritten_preview": (retrieval_query_text or "")[:60],
            "enabled": USE_REWRITER,
        })

        _t_embed0 = _t_subprog.perf_counter()
        retrieval_embedding = embed_one(
            retrieval_query_text, task_type="RETRIEVAL_QUERY",
        )
        _emit_sub("search_embed_done", {
            "elapsed_ms": int((_t_subprog.perf_counter() - _t_embed0) * 1000),
        })
        # Tier 2 보조: 한국어 조사 제거 + prefix tsquery 빌더. RPC v3 가
        # to_tsquery('simple', …) 로 받기 때문에 plainto_tsquery 형식이 아닌
        # 정식 tsquery 표현식("토큰:* | 토큰:*") 을 넘긴다.
        ts_query = nexus_build_keyword_tsquery(retrieval_query_text, original=question)
        # ── pgroonga variant 분기 (2026-05-13 추가)
        # NEXUS_HYBRID_SEARCH_VARIANT 환경변수로 v2/v3 토글.
        # - "v2" (기본): 기존 tsvector + to_tsquery 경로
        # - "v3_pgroonga": pgroonga &@~ TokenMecab 한국어 형태소 매칭
        from .config import get_secret
        _hs_variant = (get_secret("NEXUS_HYBRID_SEARCH_VARIANT", "v2") or "v2").lower().strip()
        if _hs_variant == "v3_pgroonga":
            from .nexus_query_rewriter import nexus_build_pgroonga_query
            _kw_query = nexus_build_pgroonga_query(retrieval_query_text, original=question)
            _rpc_name = "nexus_hybrid_search_v3_pgroonga"
        else:
            _kw_query = ts_query
            _rpc_name = "nexus_hybrid_search_v2"
        match_count = top_k or s.top_k
        # Incident-aware rerank: 사용자 질문 + rewritten 양쪽에서 incident
        # 노드 분류 후 RPC top-15 로 풀을 확대해 receive → meta.incident_nodes
        # 매칭 시 rrf_score +INCIDENT_BOOST 가산 → 재정렬 후 match_count 컷.
        rpc_match_count = max(match_count, 15)
        payload = {
            "query_embedding": retrieval_embedding,
            "query_text": _kw_query,
            "match_count": rpc_match_count,
            "rrf_k": 60,
            "pool_size": max(30, rpc_match_count * 6),
        }
        _t_rpc0 = _t_subprog.perf_counter()
        res = supabase.rpc(_rpc_name, payload).execute()
        raw_chunks = res.data or []
        _emit_sub("search_rpc_done", {
            "elapsed_ms": int((_t_subprog.perf_counter() - _t_rpc0) * 1000),
            "matched": len(raw_chunks),
            "variant": _hs_variant,
        })


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

            # ── Layer 1.5 (PR-Fix-DocKind-Enrich): L1 RPC 결과 doc_kind 보강 ─
            # L1 RPC schema (db/migrations/20260511_nexus_force_include_rpc_v2.sql)
            # 가 doc_kind 미반환. L1 성공 분기에선 _doc_meta_enrich 가 비어있어
            # union 단계의 raw_chunks 의 doc_kind 가 None 으로 채워짐.
            # _balance_by_doc_kind 의 by_kind 분류 + _FORCE_KIND_MAX 보존
            # 분기가 None doc_kind 를 모두 무시 → penalty 사규 누락 회귀
            # (query '횡령' 답변의 ⚖️ 징계 기준 섹션 공란).
            # 별도 nexus_documents query 1회로 _doc_meta_enrich 채워 정상화.
            if force_chunks_raw and force_include_source == "rpc":
                _enrich_doc_ids = list({
                    fc.get("document_id") for fc in force_chunks_raw
                    if fc.get("document_id")
                })
                if _enrich_doc_ids:
                    try:
                        _enrich_resp = (
                            supabase.table("nexus_documents")
                            .select("id, title, doc_kind, meta")
                            .in_("id", _enrich_doc_ids)
                            .execute()
                        )
                        for _d in (_enrich_resp.data or []):
                            _doc_meta_enrich[_d["id"]] = _d
                        print(
                            f"[retriever:force_include:L1_ENRICH] "
                            f"doc_ids={len(_enrich_doc_ids)} "
                            f"enriched={len(_doc_meta_enrich)}",
                            file=sys.stderr, flush=True,
                        )
                    except Exception as e:
                        print(
                            f"[retriever:force_include:L1_ENRICH] FAILED: "
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

            # ── Layer 2.0: Title-direct matching (UNION) ──────────
            # PR-Title-Direct-Match: 사규명 base (prefix 제거) 와 query 직접 매칭.
            # "법인카드 관리지침 알려줘" 같이 사규명 자체가 query 에 등장하는 case.
            # L2.5_AUTO 보다 먼저 — 사규명 직접 매칭이 가장 강한 신호.
            # dedup 으로 L1/L2 가 이미 잡은 doc 제외.
            try:
                title_doc_ids = _compute_title_direct_matches(supabase, question)
                if title_doc_ids:
                    existing_doc_ids = {c.get("document_id") for c in force_chunks_raw}
                    new_title_ids = [d for d in title_doc_ids if d not in existing_doc_ids]
                    if new_title_ids:
                        chunks_resp = (
                            supabase.table("nexus_chunks")
                            .select("id, document_id, chunk_idx, article_no, text")
                            .in_("document_id", new_title_ids)
                            .execute()
                        )
                        new_chunks = chunks_resp.data or []
                        force_chunks_raw.extend(new_chunks)
                        if force_include_source and force_include_source != "none":
                            force_include_source = f"{force_include_source}+title_direct"
                        else:
                            force_include_source = "title_direct"
                        print(
                            f"[retriever:force_include:L2.0_TITLE_DIRECT] "
                            f"matched_docs={len(title_doc_ids)} "
                            f"new_docs={len(new_title_ids)} "
                            f"chunks_added={len(new_chunks)}",
                            file=sys.stderr, flush=True,
                        )
            except Exception as e:
                print(
                    f"[retriever:force_include:L2.0_TITLE_DIRECT] FAILED: "
                    f"{type(e).__name__}: {e}",
                    file=sys.stderr, flush=True,
                )

            # ── Layer 2.5: Auto-keywords matching (UNION) ──────────
            # PR-Stage-A-2-Production-Union: L1/L2 와 항상 union (회귀 안전).
            # L1_RPC 의 incident_nodes 잘못 분류 case 보호.
            # chunks.auto_keywords (Auto-Fixer 보강 데이터) 활용.
            # dedup 으로 L1/L2 가 이미 잡은 doc 제외.
            try:
                v3_candidates = _compute_v3_matches(
                    supabase=supabase,
                    question=question,
                    retrieval_query_text=retrieval_query_text,
                )
                # 보수적 임계값 + top N
                qualified = [c for c in v3_candidates if c.get("total", 0) >= 5][:5]

                if qualified:
                    # 기존 force_chunks_raw 의 doc_ids 와 dedup
                    existing_doc_ids = {c.get("document_id") for c in force_chunks_raw}
                    new_qualified = [c for c in qualified if c["id"] not in existing_doc_ids]
                    new_doc_ids = [c["id"] for c in new_qualified]

                    if new_doc_ids:
                        chunks_resp = (
                            supabase.table("nexus_chunks")
                            .select("id, document_id, chunk_idx, article_no, text")
                            .in_("document_id", new_doc_ids)
                            .execute()
                        )
                        new_chunks = chunks_resp.data or []
                        force_chunks_raw.extend(new_chunks)
                        # source 누적 (multi-layer 매칭 표시)
                        if force_include_source:
                            force_include_source = f"{force_include_source}+auto_kw"
                        else:
                            force_include_source = "auto_keywords"
                        print(
                            f"[retriever:force_include:L2.5_AUTO_KEYWORDS] "
                            f"qualified={len(qualified)} new_docs={len(new_doc_ids)} "
                            f"top_new={[c['title'][:30] for c in new_qualified[:3]]} "
                            f"chunks_added={len(new_chunks)}",
                            file=sys.stderr, flush=True,
                        )
                    else:
                        print(
                            f"[retriever:force_include:L2.5_AUTO_KEYWORDS] "
                            f"qualified={len(qualified)} all already in force (no new)",
                            file=sys.stderr, flush=True,
                        )
                else:
                    print(
                        f"[retriever:force_include:L2.5_AUTO_KEYWORDS] "
                        f"no candidates >= 5 (total: {len(v3_candidates)})",
                        file=sys.stderr, flush=True,
                    )
            except Exception as e:
                print(
                    f"[retriever:force_include:L2.5_AUTO_KEYWORDS] FAILED: "
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

            # ═══ L2.5_AUTO_KEYWORDS shadow log ═══ (PR-Stage-A-2-Shadow)
            # 회귀 위험 0: 실제 force_include / raw_chunks 에 영향 X.
            # docs.auto_keywords 활용 시 어떤 doc 매칭되는지 데이터 수집.
            # 1주일 운영 후 PR-Stage-A-2-Production 결정.
            try:
                _shadow_log_auto_keywords_match(
                    supabase,
                    question=question,
                    retrieval_query_text=retrieval_query_text,
                    log_prefix="",
                )
            except Exception:
                pass  # shadow 실패가 retriever 정상 흐름 방해 안 함

            # ── Union into raw_chunks (dedup by chunk id) ───
            # PR-Fix-Force-Include-Dup-Flag: chunks dict map — 중복 chunks 의
            # force_included_by_intent flag 보장. Vector + BM25 단계에서 이미
            # raw_chunks 에 있는 chunks (낮은 score) 가 L3 force_include 매칭
            # 시 단순 skip 했던 bug → best_chunk_per_doc 누락 → 답변 인용
            # 못 함 회귀 차단. 예: 거래처 명절 선물 query 의 (CSR) 클린뱅크
            # 운영 지침 chunks 가 vector 단계에 낮은 score 로 진입 → L3 매칭
            # 됐어도 flag update 안 돼 final top_k 진입 못 함.
            existing_chunks_by_id: dict = {
                c.get("id"): c for c in raw_chunks if c.get("id")
            }
            existing_chunk_ids = set(existing_chunks_by_id.keys())
            added_count = 0
            skipped_count = 0
            for fc in force_chunks_raw:
                _fc_id = fc.get("id")
                if _fc_id in existing_chunk_ids:
                    # 중복 chunks 도 force_included_by_intent + source 보장
                    _existing = existing_chunks_by_id.get(_fc_id)
                    if _existing is not None:
                        _existing["force_included_by_intent"] = True
                        _existing["force_include_source"] = force_include_source
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
        # 정렬: rrf_score 내림차순 + query_keyword_overlap 내림차순
        #     + procedure_keyword_count 내림차순 + chunk_id 사전순 (결정적).
        MAX_CHUNKS_PER_DOC = 2
        # PR-Fix-Domain-Bias: 단일 도메인 (예 (안전) 26.5% chunk share) 이
        # 비도메인 query (휴가/출장비 등) top_k 를 점유하는 bias 차단.
        # force_include guaranteed_chunks 는 본 cap 면제 — 4-2 에서 무조건 추가.
        MAX_CHUNKS_PER_DOMAIN = 3
        # PR-Fix-TopK-Cap-Root-Cause: TOP_K=10 → 12 (matched_docs 보존 강화)
        # 근거: 5/15 검증에서 Q2 경쟁사 가격 matched_docs=11 → 1 drop 확인.
        # guaranteed_chunks[:TOP_K] cap 으로 (공정거래) doc drop → 답변 본문 인용 누락.
        # TOP_K=12 로 matched_docs ≤ 12 까지 모두 보존 (1-Doc 도메인 자동 보존).
        # 비용: chunks +20%, input tokens +4%, cost +$0.001/query (무시 가능).
        TOP_K = 12

        # === PR-Fix-Query-Aware-Ranking ===
        # 기존 'procedure_keyword_count' tiebreaker 만으로는 도입부/총칙 청크가
        # 구체 부정행위 표 청크보다 우선 선택되는 회귀가 있음.
        # 예: query '팀장이 회사 돈 횡령한것 같음' 답변의 ⚖️ 징계 기준 섹션에
        # 임직원 징계기준 chunk_idx=0 (도입부 '징계권 행사 목적') 만 인용되고
        # chunk_idx=5 (14. 회사 공금 횡령 본문 + 단순/일회성, 고의/반복 표) 가
        # 누락. 두 청크 모두 rrf_score 동률 (force_include) 인 상태에서
        # procedure_keyword_count 가 chunk_idx=0 에 유리하기 때문.
        # query 어휘 일치 횟수를 정렬 키에 추가하여 의미 가까운 청크 우선.
        import re as _re_qk
        _q_str = (question or "") + " " + (retrieval_query_text or "")
        _q_tokens = {
            _t for _t in _re_qk.findall(r"[가-힣A-Za-z0-9]+", _q_str.lower())
            if len(_t) >= 2  # 1-char 토큰 노이즈 제거
        }
        for _c in raw_chunks:
            _txt_lower = (_c.get("text") or "").lower()
            _c["_query_keyword_overlap"] = sum(
                1 for _t in _q_tokens if _t and _t in _txt_lower
            )

        raw_chunks.sort(
            key=lambda c: (
                -(c.get("rrf_score") or 0.0),
                -(c.get("_query_keyword_overlap") or 0),
                -(c.get("procedure_keyword_count") or 0),
                str(c.get("id") or ""),
            )
        )

        # === PR-P2A-Reranker: Gemini Flash-Lite 의미 기반 reranker ===
        # RRF + 어휘 매칭의 구조적 한계 (도입부/총칙이 구체 정보 청크보다
        # 우선) 를 LLM 의미 매칭으로 보완. top-N (기본 30) 만 LLM 통과.
        # 실패 시 raw_chunks 그대로 반환 (회귀 위험 0).
        # 입력 query 는 사용자 원문 — rewriter 출력은 키워드 확장이라 의미
        # 평가에 부적합.
        try:
            from .nexus_reranker import rerank_chunks
            _t_rerank0 = _t_subprog.perf_counter()
            raw_chunks = rerank_chunks(query=question or "", raw_chunks=raw_chunks)
            _emit_sub("search_rerank_done", {
                "elapsed_ms": int((_t_subprog.perf_counter() - _t_rerank0) * 1000),
                "top_titles": [
                    c.get("doc_title", "") for c in raw_chunks[:3]
                    if c.get("doc_title")
                ],
            })
        except Exception as _rerank_e:
            print(
                f"[reranker] FAILED (outer): {type(_rerank_e).__name__}: {_rerank_e}",
                file=sys.stderr, flush=True,
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
        # guaranteed_chunks 도 동일 결정적 정렬.
        guaranteed_chunks.sort(
            key=lambda c: (
                -(c.get("rrf_score") or 0.0),
                -(c.get("_query_keyword_overlap") or 0),
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
        domain_count_in_final: dict = {}
        for c in final_rows:
            doc_id = c.get("document_id") or ""
            doc_count_in_final[doc_id] = doc_count_in_final.get(doc_id, 0) + 1
            d = _chunk_domain(c)
            if d:
                domain_count_in_final[d] = domain_count_in_final.get(d, 0) + 1

        # 4-3) 남은 슬롯을 일반 chunk 로 채움 (diversity cap 적용).
        # PR-Fix-Domain-Bias: per-domain cap (MAX_CHUNKS_PER_DOMAIN) 추가.
        # 단일 도메인 over-saturation 방지 — guaranteed_chunks 는 cap 면제.
        for chunk in raw_chunks:
            if len(final_rows) >= TOP_K:
                break
            if chunk.get("id") in final_chunk_ids:
                continue
            doc_id = chunk.get("document_id") or ""
            if doc_count_in_final.get(doc_id, 0) >= MAX_CHUNKS_PER_DOC:
                continue
            domain = _chunk_domain(chunk)
            if domain and domain_count_in_final.get(domain, 0) >= MAX_CHUNKS_PER_DOMAIN:
                continue
            final_rows.append(chunk)
            final_chunk_ids.add(chunk.get("id"))
            doc_count_in_final[doc_id] = doc_count_in_final.get(doc_id, 0) + 1
            if domain:
                domain_count_in_final[domain] = domain_count_in_final.get(domain, 0) + 1

        # 4-3.5) PR-Fix-Penalty-All-Chunks: penalty doc 청크 강제 보존.
        # 사규 답변 quality 보장 위해 임직원 징계기준 같은 penalty doc 의 모든
        # 청크 (도입부 + 구체 부정행위 표) 가 LLM 컨텍스트에 들어가야 함.
        # F-G8 (query keyword overlap) 만으론 도입부가 일반 어휘 ('회사',
        # '징계') 매칭 多 로 우선되어 구체 표 청크 (예: chunk_idx=5 의 14번
        # 회사 공금 횡령) 누락. TOP_K + MAX_CHUNKS_PER_DOC cap 무시하여
        # penalty force_include 청크 전부 추가. input tokens +~1500 추정
        # (Gemini 200K context 의 1% 미만, 무시 가능).
        for chunk in raw_chunks:
            if chunk.get("id") in final_chunk_ids:
                continue
            if (chunk.get("doc_kind") or "") != "penalty":
                continue
            if not chunk.get("force_included_by_intent"):
                continue
            final_rows.append(chunk)
            final_chunk_ids.add(chunk.get("id"))
            doc_id = chunk.get("document_id") or ""
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
