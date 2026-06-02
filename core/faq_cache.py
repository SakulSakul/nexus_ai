"""PR-Phase-18.1: FAQ Cache — Modular RAG 의 Fast Path 캐시 계층.

큐레이션 가능한 FAQ 답변 캐시 (Supabase nexus_faq_cache).
선례 미러링: core/auto/cache.py (nexus_classification_cache 패턴).

설계 결정 (사쿨님 확정):
- TEXT UNIQUE 직접 키 — SHA-256 hash 미도입 (선례 정합, 디버깅 용이).
- 정규화 = 공백 + lowercase 만 — suffix(방법/절차/안내) 정규화 금지
  ("성희롱 신고 방법"(standard) vs "성희롱 피해"(critical) 의미 붕괴 방지,
   Sprint 17 분류 정확도 보호).
- ENABLE_FAST_PATH 기본 OFF — 18.1 에서는 미사용. 18.2 에서 ask/ask_stream
  진입부에 gate 주입 (classifier 앞 → 진정한 0-latency).

안전:
- 모든 함수 실패 흡수 (silent fail 금지 원칙: stderr 로그 후 None/[] 반환).
- critical(is_critical=true)·미승인(approved=false) 항목은 get 에서 제외 →
  핫라인 우회 차단 + 미검토 답변 노출 차단.
"""
from __future__ import annotations

import datetime
import sys
from typing import Any, Optional

from .config import get_secret, settings


# ── Feature flag (18.1 미사용, 18.2 활성화) ──────────────────
ENABLE_FAST_PATH: bool = (
    get_secret("ENABLE_FAST_PATH", "false").lower() == "true"
)


def _get_sb() -> Any:
    """service_role 우선 client (선례 core/auto/cache.py:_get_sb 미러링)."""
    try:
        from supabase import create_client
        s = settings()
        if not s.supabase_url:
            return None
        key = s.supabase_service_role_key or s.supabase_key
        if not key:
            return None
        return create_client(s.supabase_url, key)
    except Exception as e:
        print(
            f"[faq_cache] supabase client 가져오기 실패: {type(e).__name__}: {e}",
            file=sys.stderr, flush=True,
        )
        return None


def normalize_query(q: str) -> str:
    """공백 + lowercase 정규화 (선례 동일). suffix 정규화 없음."""
    return " ".join((q or "").strip().lower().split())


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def faq_cache_peek(query: str) -> Optional[dict]:
    """Read-only 조회 — hit_count 를 증가시키지 않는다 (faq_cache_get 과 차이).

    Admin stress test / 검증 도구 전용. 프로덕션 응답 경로(Fast Path)는
    faq_cache_get 을 써서 hit_count 가 정상 누적되어야 하므로, latency 반복
    측정 시 통계 오염을 피하려고 부작용 없는 이 함수를 사용한다.
    """
    sb = _get_sb()
    if not sb:
        return None
    try:
        normalized = normalize_query(query)
        if not normalized:
            return None
        r = (
            sb.table("nexus_faq_cache")
            .select("id,answer_text,category,incident_nodes,hit_count")
            .eq("query_normalized", normalized)
            .eq("approved", True)
            .eq("is_critical", False)
            .limit(1)
            .execute()
        )
        if not r.data:
            return None
        row = r.data[0]
        if not (row.get("answer_text") or "").strip():
            return None
        return row
    except Exception as e:
        print(f"[faq_cache] peek failed: {type(e).__name__}: {e}",
              file=sys.stderr, flush=True)
    return None


def faq_cache_get(query: str) -> Optional[dict]:
    """승인된 비-critical FAQ 만 조회. hit 시 hit_count++ / last_hit_at 갱신.

    Returns: {answer_text, category, incident_nodes, id, hit_count} 또는 None.
    18.2 Fast Path 가 응답 경로에서 호출 (18.1 에서는 Admin Test 버튼만).
    """
    sb = _get_sb()
    if not sb:
        return None
    try:
        normalized = normalize_query(query)
        if not normalized:
            return None
        r = (
            sb.table("nexus_faq_cache")
            .select("id,answer_text,category,incident_nodes,hit_count")
            .eq("query_normalized", normalized)
            .eq("approved", True)
            .eq("is_critical", False)
            .limit(1)
            .execute()
        )
        if not r.data:
            return None
        row = r.data[0]
        if not (row.get("answer_text") or "").strip():
            return None
        try:
            sb.table("nexus_faq_cache").update({
                "hit_count": (row.get("hit_count") or 0) + 1,
                "last_hit_at": _now_iso(),
            }).eq("id", row["id"]).execute()
        except Exception:
            pass
        return row
    except Exception as e:
        print(f"[faq_cache] get failed: {type(e).__name__}: {e}",
              file=sys.stderr, flush=True)
    return None


def faq_cache_upsert(
    query_display: str,
    *,
    answer_text: str = "",
    category: str | None = None,
    is_critical: bool = False,
    incident_nodes: list | None = None,
    source: str = "manual",
) -> bool:
    """큐레이션용 upsert (Admin 패널). query_normalized 자동 생성.

    answer_text 갱신 시 approved 는 건드리지 않는다 (재검토는 Admin 에서 명시).
    """
    sb = _get_sb()
    if not sb:
        return False
    normalized = normalize_query(query_display)
    if not normalized:
        return False
    try:
        payload: dict = {
            "query_normalized": normalized,
            "query_display": query_display,
            "answer_text": answer_text or "",
            "is_critical": bool(is_critical),
            "incident_nodes": incident_nodes or [],
            "source": source,
            "updated_at": _now_iso(),
        }
        if category:
            payload["category"] = category
        sb.table("nexus_faq_cache").upsert(
            payload, on_conflict="query_normalized",
        ).execute()
        return True
    except Exception as e:
        print(f"[faq_cache] upsert failed: {type(e).__name__}: {e}",
              file=sys.stderr, flush=True)
        return False


def faq_cache_list(
    limit: int = 100, offset: int = 0, approved_only: bool = False,
) -> list[dict]:
    """Admin display 용. approved 우선 → hit_count 내림차순 정렬."""
    sb = _get_sb()
    if not sb:
        return []
    try:
        q = sb.table("nexus_faq_cache").select(
            "id,query_display,answer_text,category,is_critical,"
            "approved,approved_by,approved_at,hit_count,last_hit_at,"
            "source,created_at,updated_at,"
            "show_on_home,home_label,home_order"
        )
        if approved_only:
            q = q.eq("approved", True)
        r = (
            q.order("approved", desc=True)
             .order("hit_count", desc=True)
             .range(offset, offset + limit - 1)
             .execute()
        )
        return r.data or []
    except Exception as e:
        print(f"[faq_cache] list failed: {type(e).__name__}: {e}",
              file=sys.stderr, flush=True)
        return []


def faq_cache_approve(faq_id: str, approved_by: str) -> bool:
    """컴플라이언스 게이트: approved=true. answer_text 비어있으면 거부."""
    sb = _get_sb()
    if not sb:
        return False
    try:
        cur = (
            sb.table("nexus_faq_cache")
            .select("answer_text")
            .eq("id", faq_id)
            .limit(1)
            .execute()
        )
        if not cur.data or not (cur.data[0].get("answer_text") or "").strip():
            return False
        sb.table("nexus_faq_cache").update({
            "approved": True,
            "approved_by": approved_by,
            "approved_at": _now_iso(),
            "updated_at": _now_iso(),
        }).eq("id", faq_id).execute()
        return True
    except Exception as e:
        print(f"[faq_cache] approve failed: {type(e).__name__}: {e}",
              file=sys.stderr, flush=True)
        return False


def faq_cache_delete(faq_id: str) -> bool:
    sb = _get_sb()
    if not sb:
        return False
    try:
        sb.table("nexus_faq_cache").delete().eq("id", faq_id).execute()
        return True
    except Exception as e:
        print(f"[faq_cache] delete failed: {type(e).__name__}: {e}",
              file=sys.stderr, flush=True)
        return False


def faq_cache_stats() -> dict:
    """상단 통계 panel 용: 총/승인/총 hit/최다 hit FAQ."""
    rows = faq_cache_list(limit=1000)
    total = len(rows)
    approved = sum(1 for r in rows if r.get("approved"))
    total_hits = sum((r.get("hit_count") or 0) for r in rows)
    top = max(rows, key=lambda r: (r.get("hit_count") or 0), default=None)
    return {
        "total": total,
        "approved": approved,
        "total_hits": total_hits,
        "top": top,
    }


def faq_cache_home_chips(limit: int = 3) -> list[dict]:
    """홈 칩용: approved AND NOT is_critical AND show_on_home, home_order 오름차순 상위 N.

    실패/빈 결과 시 [] (홈 렌더 측 하드코딩 fallback). query_display/home_label/home_order 반환.
    """
    sb = _get_sb()
    if not sb:
        return []
    try:
        r = (
            sb.table("nexus_faq_cache")
            .select("query_display,home_label,home_order")
            .eq("approved", True)
            .eq("is_critical", False)
            .eq("show_on_home", True)
            .order("home_order", desc=False)
            .order("hit_count", desc=True)
            .limit(limit)
            .execute()
        )
        return r.data or []
    except Exception as e:
        print(f"[faq_cache] home_chips failed: {type(e).__name__}: {e}",
              file=sys.stderr, flush=True)
        return []


def faq_cache_set_home(
    faq_id: str, *, show_on_home: bool, home_label: str = "", home_order: int = 0,
) -> bool:
    """홈 칩 노출 설정 (Admin). approved/is_critical/answer_text 는 건드리지 않음."""
    sb = _get_sb()
    if not sb:
        return False
    try:
        sb.table("nexus_faq_cache").update({
            "show_on_home": bool(show_on_home),
            "home_label": ((home_label or "").strip() or None),
            "home_order": int(home_order or 0),
            "updated_at": _now_iso(),
        }).eq("id", faq_id).execute()
        return True
    except Exception as e:
        print(f"[faq_cache] set_home failed: {type(e).__name__}: {e}",
              file=sys.stderr, flush=True)
        return False


# ── Phase 2 Hook (베타 단계 미활성화) ────────────────────────
def top_from_query_logs(n: int = 20) -> list:
    """Phase 2: query_logs 빈도 기반 FAQ 자동 선정.

    베타 단계 부적합(테스터의 시스템 검증 query 위주) → 운영 배포 후 활성화.
    현재는 코드 골격만 유지 (Admin 버튼 disabled).
    """
    raise NotImplementedError("Phase 2: 운영 배포 후 활성화")
