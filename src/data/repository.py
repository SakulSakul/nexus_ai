"""Supabase repository — nexus_documents/nexus_chunks/query_logs 접근."""
from __future__ import annotations

import re
from typing import Optional

from supabase import Client, create_client

from src.ai.base import LLMClient
from src.config.settings import Settings
from src.data.schemas import chunk_from_row
from src.service.models import Answer, Chunk


_POOL_MULTIPLIER: int = 4
_MIN_POOL: int = 30


class DocumentRepository:
    def __init__(self, settings: Settings, llm: LLMClient):
        self._settings = settings
        self._llm = llm
        self._client: Client = create_client(
            settings.supabase_url,
            settings.supabase_service_role_key,
        )

    def search(
        self,
        query: str,
        categories: list[str] | None = None,
        top_k: int = 8,
    ) -> list[Chunk]:
        query_embedding = self._llm.embed(query, task_type="RETRIEVAL_QUERY")
        ts_query = self._build_tsquery(query)
        pool_size = max(_MIN_POOL, top_k * _POOL_MULTIPLIER)
        payload = {
            "query_embedding": query_embedding,
            "query_text": ts_query,
            "match_count": top_k,
            "rrf_k": 60,
            "pool_size": pool_size,
        }
        try:
            res = self._client.rpc("nexus_hybrid_search_v2", payload).execute()
            rows = res.data or []
        except Exception as e:
            raise RuntimeError(f"Supabase RPC error: {e}") from e

        chunks = [chunk_from_row(r) for r in rows if r.get("id") or r.get("chunk_id")]
        chunks.sort(key=lambda c: c.score, reverse=True)
        return chunks[:top_k]

    def log_query(
        self,
        query_masked: str,
        answer: Answer,
        category: str = "공통",
        user_id_hash: Optional[str] = None,
        chat_model_version: Optional[str] = None,
    ) -> None:
        if not self._settings.log_queries:
            return

        hit_chunk_ids = [c.chunk_id for c in answer.citations]
        used_fallback = (answer.status.value != "ok")

        row = {
            "category": category,
            "query_masked": query_masked,
            "is_critical": False,
            "critical_kind": None,
            "hit_chunk_ids": hit_chunk_ids,
            "chat_provider": "gemini",
            "chat_model_version": chat_model_version or self._settings.gemini_synth_model,
            "env": self._settings.app_env,
            "user_id_hash": user_id_hash,
            "access_level": "employee",
            "embed_model_version": self._settings.gemini_embed_model,
            "elapsed_ms": answer.elapsed_ms,
            "used_fallback": used_fallback,
            "hit_categories": [],
            "is_reroll": False,
        }
        try:
            self._client.table("query_logs").insert(row).execute()
        except Exception:
            pass

    @staticmethod
    def _build_tsquery(query: str) -> str:
        tokens = re.findall(r"[가-힣A-Za-z0-9]+", query)
        tokens = [t for t in tokens if len(t) >= 2]
        if not tokens:
            return ""
        return " | ".join(f"{t}:*" for t in tokens[:8])
