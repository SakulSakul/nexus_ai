"""Audit log 저장 helper — silent fail policy.

라이브 chat / regression 흐름이 audit 실패로 깨지면 안 됨. 모든 함수가
exception 흡수 후 stderr 로깅 + 빈 결과 반환.
"""

from __future__ import annotations

import sys
from typing import Any, Optional

from .schemas import AuditLogEntry


def _get_supabase() -> Any:
    """service_role 우선 supabase client 생성 (RLS 우회 INSERT)."""
    try:
        from supabase import create_client
        from core.config import settings
        s = settings()
        if not s.supabase_url:
            return None
        key = s.supabase_service_role_key or s.supabase_key
        if not key:
            return None
        return create_client(s.supabase_url, key)
    except Exception as e:
        print(
            f"[audit] supabase client 가져오기 실패: "
            f"{type(e).__name__}: {e}",
            file=sys.stderr, flush=True,
        )
        return None


def log_query(entry: AuditLogEntry) -> bool:
    """Audit log 1건 nexus_audit_logs 테이블에 저장.

    Silent fail — audit 실패가 main 흐름 (라이브 chat / regression) 을
    깨면 안 됨.
    """
    try:
        sb = _get_supabase()
        if sb is None:
            print("[audit] supabase client unavailable", file=sys.stderr, flush=True)
            return False
        payload = entry.to_payload()
        result = sb.table("nexus_audit_logs").insert(payload).execute()
        return bool(getattr(result, "data", None))
    except Exception as e:
        print(
            f"[audit] log_query failed: {type(e).__name__}: {e}",
            file=sys.stderr, flush=True,
        )
        return False


def fetch_recent_logs(
    limit: int = 50,
    source: Optional[str] = None,
    verdict: Optional[str] = None,
) -> list:
    """최근 audit log 조회 — admin 패널용."""
    try:
        sb = _get_supabase()
        if sb is None:
            return []
        query = sb.table("nexus_audit_logs").select("*")
        if source:
            query = query.eq("source", source)
        if verdict:
            query = query.eq("claude_verdict", verdict)
        result = query.order("created_at", desc=True).limit(limit).execute()
        return result.data or []
    except Exception as e:
        print(
            f"[audit] fetch_recent_logs failed: {type(e).__name__}: {e}",
            file=sys.stderr, flush=True,
        )
        return []
