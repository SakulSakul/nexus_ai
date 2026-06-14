"""Gemini Explicit Cache (CAG — Cache-Augmented Generation) Manager.

SYSTEM_PROMPT + 전체 사규 corpus 를 server-side cache 에 저장. 매 request 시
cached_content 만 reference → input token 비용 ~95% 절감 (cached 토큰 = 1/4 가격).

설계 원칙:
- 기본 OFF (NEXUS_CAG_ENABLED=false) — 명시적 활성 시에만 cache path 작동.
- TTL 1 hour (NEXUS_CAG_TTL_HOURS), 만료 임박 (50min, NEXUS_CAG_REFRESH_THRESHOLD_MINUTES)
  시 자동 refresh.
- NEXUS_CAG_INVALIDATE_TOKEN 변경 시 cache drop + rebuild (사규 update 후 수동 invalidation).
- App boot 시 pre-warming (ensure_warm) — Streamlit rerun 마다 호출해도 idempotent.
- Validator / Critical mode / Force-include 모두 100% 유지 — cache 는 canonical
  SYSTEM_PROMPT 가 system 인자로 들어올 때만 활성. critical/low-confidence 변형
  prompt 는 cache 우회 (안전망).

회귀 위험 0:
- 기본 OFF → 기존 동작 그대로.
- enable 후에도 cache build 실패 시 None 반환 → 기존 path fallback.
- thread-safe (Lock) — Streamlit rerun 동시 호출 안전.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from threading import Lock
from typing import Callable, Optional

from .config import get_secret, settings


# ──────────────────────────────────────────────────────────
# Env helpers
# ──────────────────────────────────────────────────────────
def is_cag_enabled() -> bool:
    val = (get_secret("NEXUS_CAG_ENABLED", "false") or "false").strip().lower()
    return val in ("true", "1", "yes", "on")


def _ttl_hours() -> int:
    try:
        return max(1, int(get_secret("NEXUS_CAG_TTL_HOURS", "1") or "1"))
    except Exception:
        return 1


def _refresh_threshold_minutes() -> int:
    try:
        return max(5, int(get_secret("NEXUS_CAG_REFRESH_THRESHOLD_MINUTES", "50") or "50"))
    except Exception:
        return 50


def _invalidate_token() -> str:
    return (get_secret("NEXUS_CAG_INVALIDATE_TOKEN", "") or "").strip()


# ──────────────────────────────────────────────────────────
# State singleton (per-process)
# ──────────────────────────────────────────────────────────
class _CagState:
    def __init__(self) -> None:
        self.cache_name: Optional[str] = None
        self.created_at: Optional[datetime] = None
        self.invalidate_token: str = ""
        self.lock: Lock = Lock()

    def age_minutes(self) -> float:
        if not self.created_at:
            return float("inf")
        return (datetime.now(timezone.utc) - self.created_at).total_seconds() / 60.0


_state = _CagState()


# ──────────────────────────────────────────────────────────
# Gemini SDK helpers
# ──────────────────────────────────────────────────────────
def _gemini_client():
    """Lazy Gemini client. None on missing API key / SDK."""
    try:
        from google import genai
    except Exception:
        return None
    s = settings()
    if not s.gemini_api_key:
        return None
    return genai.Client(api_key=s.gemini_api_key)


def _create_cache(system_instruction: str, corpus_text: str) -> Optional[str]:
    """Gemini caches.create — returns cache name or None on failure."""
    cli = _gemini_client()
    if cli is None:
        return None
    try:
        from google.genai import types
        s = settings()
        ttl_seconds = _ttl_hours() * 3600
        cache = cli.caches.create(
            model=s.chat_model,
            config=types.CreateCachedContentConfig(
                system_instruction=system_instruction,
                contents=[corpus_text],
                ttl=f"{ttl_seconds}s",
            ),
        )
        name = getattr(cache, "name", None)
        print(
            f"[cag] cache created: name={name} ttl={ttl_seconds}s "
            f"model={s.chat_model} corpus_chars={len(corpus_text)}",
            file=sys.stderr, flush=True,
        )
        return name
    except Exception as e:
        print(
            f"[cag] FAILED to create cache: {type(e).__name__}: {e}",
            file=sys.stderr, flush=True,
        )
        return None


def _delete_cache(cache_name: str) -> None:
    """Gemini caches.delete — best-effort."""
    cli = _gemini_client()
    if cli is None or not cache_name:
        return
    try:
        cli.caches.delete(name=cache_name)
        print(f"[cag] cache deleted: {cache_name}", file=sys.stderr, flush=True)
    except Exception as e:
        print(
            f"[cag] WARN cache delete failed: {type(e).__name__}: {e}",
            file=sys.stderr, flush=True,
        )


# ──────────────────────────────────────────────────────────
# Default content builder — supabase 전체 사규 corpus
# ──────────────────────────────────────────────────────────
def _default_content_builder() -> tuple[str, str]:
    """SYSTEM_PROMPT + 전체 사규 corpus 빌드.

    Active 사규 (`status='active'`) 의 모든 chunks 를 chunk_idx 순으로 정렬
    하여 doc title + article_no 헤더와 함께 단일 텍스트로 concat.
    Returns: (system_instruction, regulation_corpus). 빌드 실패 시 (SYSTEM_PROMPT, "").
    """
    from .prompts import SYSTEM_PROMPT
    try:
        from supabase import create_client
        s = settings()
        if not s.supabase_url or not s.supabase_key:
            return (SYSTEM_PROMPT, "")
        cli = create_client(s.supabase_url, s.supabase_key)
        docs_resp = (
            cli.table("nexus_documents")
            .select("id, title, doc_kind, status")
            .eq("status", "active")
            .execute()
        )
        docs = docs_resp.data or []
        doc_map: dict = {d["id"]: d for d in docs}
        if not doc_map:
            return (SYSTEM_PROMPT, "")
        chunks_resp = (
            cli.table("nexus_chunks")
            .select("document_id, chunk_idx, article_no, text")
            .in_("document_id", list(doc_map.keys()))
            .execute()
        )
        chunks = chunks_resp.data or []
        by_doc: dict = {}
        for c in chunks:
            by_doc.setdefault(c["document_id"], []).append(c)
        for did in by_doc:
            by_doc[did].sort(key=lambda x: x.get("chunk_idx") or 0)
        out_parts: list[str] = ["# 사규 전체 corpus (CAG cached content)"]
        for did, dchunks in by_doc.items():
            title = doc_map[did].get("title") or did
            kind = doc_map[did].get("doc_kind") or ""
            out_parts.append(f"\n\n## {title}" + (f" [{kind}]" if kind else ""))
            for c in dchunks:
                art = c.get("article_no")
                head = f"[제{art}조]" if art else f"[chunk {c.get('chunk_idx')}]"
                txt = c.get("text") or ""
                out_parts.append(f"\n{head}\n{txt}")
        corpus = "".join(out_parts)
        print(
            f"[cag] content built: docs={len(doc_map)} chunks={len(chunks)} "
            f"corpus_chars={len(corpus)}",
            file=sys.stderr, flush=True,
        )
        return (SYSTEM_PROMPT, corpus)
    except Exception as e:
        print(
            f"[cag] FAILED content builder: {type(e).__name__}: {e}",
            file=sys.stderr, flush=True,
        )
        return (SYSTEM_PROMPT, "")


# ──────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────
def get_cache_name(
    content_builder: Optional[Callable[[], tuple[str, str]]] = None,
) -> Optional[str]:
    """현재 cache 이름 반환. 만료 임박 또는 invalidate token 변경 시 refresh.

    실패 시 None 반환 (호출자는 graceful fallback).
    """
    if not is_cag_enabled():
        return None
    cur_token = _invalidate_token()
    with _state.lock:
        # 1) Invalidate token mismatch → drop + reset
        if _state.invalidate_token != cur_token:
            if _state.cache_name:
                _delete_cache(_state.cache_name)
            _state.cache_name = None
            _state.created_at = None
            _state.invalidate_token = cur_token
        # 2) TTL/refresh check — fresh 면 그대로
        threshold = _refresh_threshold_minutes()
        if _state.cache_name and _state.age_minutes() < threshold:
            return _state.cache_name
        # 3) (Re)build
        builder = content_builder or _default_content_builder
        try:
            sys_text, corpus_text = builder()
            if not corpus_text:
                print(
                    "[cag] WARN empty corpus — skipping cache build",
                    file=sys.stderr, flush=True,
                )
                return None
            new_name = _create_cache(sys_text, corpus_text)
            if new_name:
                if _state.cache_name and _state.cache_name != new_name:
                    _delete_cache(_state.cache_name)
                _state.cache_name = new_name
                _state.created_at = datetime.now(timezone.utc)
            return _state.cache_name
        except Exception as e:
            print(
                f"[cag] FAILED (re)build cache: {type(e).__name__}: {e}",
                file=sys.stderr, flush=True,
            )
            return None


def ensure_warm(
    content_builder: Optional[Callable[[], tuple[str, str]]] = None,
) -> Optional[str]:
    """Boot pre-warming. NEXUS_CAG_ENABLED=false 면 no-op (None 반환)."""
    if not is_cag_enabled():
        return None
    return get_cache_name(content_builder)


def invalidate() -> None:
    """Manual cache drop. 다음 get_cache_name() 호출 시 rebuild."""
    with _state.lock:
        if _state.cache_name:
            _delete_cache(_state.cache_name)
        _state.cache_name = None
        _state.created_at = None
