"""Auto-Fixer — PR-Stage-C-Auto-Fixer.

PR-Stage-B-Auto-Testset 의 weak query 를 Claude Opus 4.7 로 분석.
chunk 본문 검색 + keyword 보강 제안. 사쿨 vision (Self-Healing) 완성.
"""

from __future__ import annotations

import datetime
import json
import re
import sys
import time
from typing import Callable, Optional

from .cache import _get_sb


AUTO_FIXER_SYSTEM_PROMPT = """\
사규 keyword 보강 전문가. weak query (매칭 실패) 의 원인 분석 + chunk 의 auto_keywords 보강 제안.

[조건]
- 제안 keyword 는 chunk 본문에 실제 등장하는 단어만
- 해당 chunk 의 현재 auto_keywords 와 중복 X
- 5 카테고리 우선: 절차·제도 / 시스템·메뉴·채널 / 부서명 / 시간 기한 / 도메인 용어
- stop-word 제외: 이해관계자, CSR, 관리, 경영, 환경, 안전관리, 리스크관리
- 2글자 이상

[작업]
1. query 의 핵심 명사 추출
2. 어느 chunk 본문에 그 명사가 등장하는지 식별
3. 가장 매칭 strong 한 chunk 선택
4. 그 chunk 의 auto_keywords 에 누락된 핵심 명사 보강 제안

strict JSON 만:
{{"target_chunk_idx": int|null, "suggested_keywords": ["...", ...], "reasoning": "한 줄 명사형 평어체", "confidence": "high|medium|low"}}

매칭 chunk 없으면: {{"target_chunk_idx": null, "suggested_keywords": [], "reasoning": "chunk 본문 매칭 없음", "confidence": "low"}}
"""


def _build_chunks_block(chunks: list) -> str:
    """chunks 본문 + current keywords 를 LLM input 으로 포맷."""
    lines = []
    for c in chunks:
        idx = c.get("chunk_idx")
        text_preview = (c.get("text") or "")[:800]
        current_kws = c.get("auto_keywords") or []
        lines.append(f"[chunk {idx}]")
        lines.append(f"  현재 keywords: {current_kws}")
        lines.append(f"  본문: {text_preview}")
        lines.append("")
    return "\n".join(lines)


def analyze_weak_query(
    weak_query: str,
    expected_doc_id: str,
    expected_doc_title: str,
    chunks: list,
) -> Optional[dict]:
    """한 weak query 분석 + 보강 제안 생성.

    Returns:
        {"target_chunk_id", "target_chunk_idx", "current_keywords",
         "suggested_keywords", "reasoning", "confidence"} or None
    """
    try:
        import anthropic
        from core.config import settings
    except Exception as e:
        print(f"[auto_fixer] SDK import: {e}", file=sys.stderr, flush=True)
        return None
    s = settings()
    if not s.anthropic_api_key or not chunks:
        return None

    client = anthropic.Anthropic(api_key=s.anthropic_api_key)

    chunks_block = _build_chunks_block(chunks)
    user_msg = (
        f"weak query: \"{weak_query}\"\n"
        f"정답 사규: {expected_doc_title}\n\n"
        f"이 사규의 chunks:\n{chunks_block}\n\n"
        f"strict JSON 으로 분석."
    )

    try:
        response = client.messages.create(
            model="claude-opus-4-7",
            max_tokens=600,
            system=AUTO_FIXER_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_msg}],
        )
        raw = response.content[0].text if response.content else "{}"
        if "```" in raw:
            m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
            if m:
                raw = m.group(1)
        result = json.loads(raw)

        target_chunk_idx = result.get("target_chunk_idx")
        suggested = result.get("suggested_keywords") or []
        reasoning = result.get("reasoning") or ""
        confidence = result.get("confidence") or "low"

        # 안전 정제
        clean_suggested = [
            k.strip() for k in suggested
            if isinstance(k, str) and len(k.strip()) >= 2
        ]

        # target chunk 찾기
        target_chunk_id = None
        current_keywords = []
        if target_chunk_idx is not None:
            for c in chunks:
                if c.get("chunk_idx") == target_chunk_idx:
                    target_chunk_id = c.get("id")
                    current_keywords = c.get("auto_keywords") or []
                    break

        # 중복 제거 (현재 keywords 와 비교)
        final_suggested = [k for k in clean_suggested if k not in current_keywords]

        return {
            "target_chunk_id": target_chunk_id,
            "target_chunk_idx": target_chunk_idx,
            "current_keywords": current_keywords,
            "suggested_keywords": final_suggested[:10],
            "reasoning": reasoning,
            "confidence": confidence,
        }
    except Exception as e:
        print(f"[auto_fixer] analyze error: {type(e).__name__}: {e}", file=sys.stderr, flush=True)
        return None


def run_auto_fixer_for_run(
    run_id: str,
    *,
    progress_callback: Optional[Callable] = None,
) -> dict:
    """주어진 testset_run 의 모든 weak query 분석 + 제안 저장.

    Returns: {"total_weak", "analyzed", "proposals_created", "errors"}
    """
    sb = _get_sb()
    if sb is None:
        return {"error": "Supabase 연결 실패"}

    # 1. weak queries fetch (expected_rank IS NULL)
    try:
        weak_result = (
            sb.table("testset_results")
            .select("query_text, expected_doc_id, expected_doc_title")
            .eq("run_id", run_id)
            .is_("expected_rank", "null")
            .execute()
        )
        weak_queries = weak_result.data or []
    except Exception as e:
        return {"error": f"weak queries fetch: {e}"}

    if not weak_queries:
        return {"total_weak": 0, "analyzed": 0, "proposals_created": 0, "errors": 0,
                "note": "weak queries 없음 (모든 query 정답 진입)"}

    # 2. 각 weak doc 의 chunks 한 번에 fetch (캐싱)
    doc_ids = list({q["expected_doc_id"] for q in weak_queries})
    chunks_by_doc: dict = {}
    try:
        for doc_id in doc_ids:
            chunks_result = (
                sb.table("nexus_chunks")
                .select("id, chunk_idx, text, auto_keywords")
                .eq("document_id", doc_id)
                .order("chunk_idx")
                .execute()
            )
            chunks_by_doc[doc_id] = chunks_result.data or []
    except Exception as e:
        return {"error": f"chunks fetch: {e}"}

    # 3. 각 weak query 분석
    total = len(weak_queries)
    analyzed = 0
    proposals_created = 0
    errors = 0

    for idx, wq in enumerate(weak_queries, 1):
        weak_query = wq["query_text"]
        doc_id = wq["expected_doc_id"]
        doc_title = wq.get("expected_doc_title") or ""
        chunks = chunks_by_doc.get(doc_id, [])

        if progress_callback:
            try:
                progress_callback(idx, total, {
                    "query": weak_query[:30],
                    "doc": doc_title[:30],
                })
            except Exception:
                pass

        result = analyze_weak_query(
            weak_query=weak_query,
            expected_doc_id=doc_id,
            expected_doc_title=doc_title,
            chunks=chunks,
        )

        if result is None:
            errors += 1
            continue

        analyzed += 1

        # 4. proposal 저장
        if result.get("target_chunk_id") and result.get("suggested_keywords"):
            try:
                sb.table("auto_fixer_proposals").insert({
                    "run_id": run_id,
                    "weak_query": weak_query,
                    "expected_doc_id": doc_id,
                    "expected_doc_title": doc_title,
                    "target_chunk_id": result["target_chunk_id"],
                    "target_chunk_idx": result["target_chunk_idx"],
                    "current_keywords": result["current_keywords"],
                    "suggested_keywords": result["suggested_keywords"],
                    "reasoning": result["reasoning"],
                    "confidence": result["confidence"],
                    "status": "pending",
                }).execute()
                proposals_created += 1
            except Exception as e:
                errors += 1
                print(f"[auto_fixer] proposal insert: {e}", file=sys.stderr, flush=True)

        time.sleep(0.3)  # rate limit

    return {
        "total_weak": total,
        "analyzed": analyzed,
        "proposals_created": proposals_created,
        "errors": errors,
    }


def apply_proposal(proposal_id: str) -> dict:
    """승인된 제안 적용 — chunk.auto_keywords 업데이트.

    Returns: {"applied": bool, "note": str}
    """
    sb = _get_sb()
    if sb is None:
        return {"applied": False, "note": "Supabase 연결 실패"}

    # proposal fetch
    try:
        prop_result = (
            sb.table("auto_fixer_proposals")
            .select("*")
            .eq("id", proposal_id)
            .execute()
        )
        if not prop_result.data:
            return {"applied": False, "note": "proposal 없음"}
        prop = prop_result.data[0]
    except Exception as e:
        return {"applied": False, "note": f"fetch 실패: {e}"}

    if prop.get("status") != "pending":
        return {"applied": False, "note": f"이미 {prop.get('status')} 상태"}

    chunk_id = prop.get("target_chunk_id")
    suggested = prop.get("suggested_keywords") or []
    if not chunk_id or not suggested:
        return {"applied": False, "note": "target_chunk_id 또는 suggested 없음"}

    # 현재 chunk 의 auto_keywords fetch
    try:
        chunk_result = (
            sb.table("nexus_chunks")
            .select("auto_keywords")
            .eq("id", chunk_id)
            .execute()
        )
        if not chunk_result.data:
            return {"applied": False, "note": "chunk 없음"}
        current = chunk_result.data[0].get("auto_keywords") or []
    except Exception as e:
        return {"applied": False, "note": f"chunk fetch: {e}"}

    # 보강 keywords merge (중복 제거)
    merged = list(current)
    for kw in suggested:
        if kw not in merged:
            merged.append(kw)

    # chunk update
    try:
        sb.table("nexus_chunks").update({
            "auto_keywords": merged,
        }).eq("id", chunk_id).execute()
    except Exception as e:
        return {"applied": False, "note": f"chunk update: {e}"}

    # proposal status update
    try:
        sb.table("auto_fixer_proposals").update({
            "status": "applied",
            "applied_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }).eq("id", proposal_id).execute()
    except Exception as e:
        print(f"[auto_fixer] status update: {e}", file=sys.stderr, flush=True)

    return {"applied": True, "note": f"chunk {chunk_id[:8]} 에 {len(suggested)}개 추가"}


def reject_proposal(proposal_id: str) -> dict:
    """제안 거절."""
    sb = _get_sb()
    if sb is None:
        return {"rejected": False, "note": "Supabase 연결 실패"}
    try:
        sb.table("auto_fixer_proposals").update({
            "status": "rejected",
        }).eq("id", proposal_id).execute()
        return {"rejected": True}
    except Exception as e:
        return {"rejected": False, "note": str(e)}
