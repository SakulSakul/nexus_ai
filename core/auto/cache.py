"""Supabase cache helpers — classification / golden."""

from __future__ import annotations

import datetime
import sys
from typing import Any


def _get_sb() -> Any:
    """Settings 기반 service_role 우선 client."""
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
            f"[cache] supabase client 가져오기 실패: {type(e).__name__}: {e}",
            file=sys.stderr, flush=True,
        )
        return None


def normalize_query(q: str) -> str:
    return " ".join((q or "").strip().lower().split())


def incident_signature(nodes: list) -> str:
    return "|".join(sorted(set(nodes or [])))


def classification_cache_get(query: str):
    sb = _get_sb()
    if not sb:
        return None
    try:
        normalized = normalize_query(query)
        r = (
            sb.table("nexus_classification_cache")
            .select("incident_nodes,id,hit_count")
            .eq("query_normalized", normalized)
            .limit(1)
            .execute()
        )
        if r.data:
            row = r.data[0]
            try:
                sb.table("nexus_classification_cache").update({
                    "hit_count": (row.get("hit_count") or 0) + 1,
                    "last_used_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                }).eq("id", row["id"]).execute()
            except Exception:
                pass
            return row["incident_nodes"]
    except Exception as e:
        print(f"[cache] cls get failed: {e}", file=sys.stderr, flush=True)
    return None


def classification_cache_set(query: str, nodes: list, model_id: str) -> None:
    sb = _get_sb()
    if not sb:
        return
    try:
        sb.table("nexus_classification_cache").upsert({
            "query_normalized": normalize_query(query),
            "incident_nodes": nodes,
            "model_id": model_id,
        }, on_conflict="query_normalized").execute()
    except Exception as e:
        print(f"[cache] cls set failed: {e}", file=sys.stderr, flush=True)


def golden_cache_get(incident_nodes: list):
    sb = _get_sb()
    if not sb:
        return None
    try:
        sig = incident_signature(incident_nodes)
        r = (
            sb.table("nexus_golden_cache")
            .select("expected_clauses,required_docs,id,hit_count")
            .eq("incident_signature", sig)
            .limit(1)
            .execute()
        )
        if r.data:
            row = r.data[0]
            try:
                sb.table("nexus_golden_cache").update({
                    "hit_count": (row.get("hit_count") or 0) + 1,
                    "last_used_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                }).eq("id", row["id"]).execute()
            except Exception:
                pass
            return {
                "expected_clauses": row.get("expected_clauses") or [],
                "required_docs": row.get("required_docs") or [],
            }
    except Exception as e:
        print(f"[cache] golden get failed: {e}", file=sys.stderr, flush=True)
    return None


def golden_cache_set(incident_nodes: list, golden: dict, model_id: str) -> None:
    sb = _get_sb()
    if not sb:
        return
    try:
        sb.table("nexus_golden_cache").upsert({
            "incident_signature": incident_signature(incident_nodes),
            "expected_clauses": golden.get("expected_clauses") or [],
            "required_docs": golden.get("required_docs") or [],
            "model_id": model_id,
        }, on_conflict="incident_signature").execute()
    except Exception as e:
        print(f"[cache] golden set failed: {e}", file=sys.stderr, flush=True)
