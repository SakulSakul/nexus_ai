"""환경 설정 통합. .streamlit/secrets.toml + env vars 양쪽 지원."""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

try:
    import streamlit as st
    _HAS_STREAMLIT = True
except ImportError:
    _HAS_STREAMLIT = False
    st = None  # type: ignore


def _read(key: str, default: Optional[str] = None) -> Optional[str]:
    if _HAS_STREAMLIT:
        try:
            val = st.secrets.get(key)
            if val:
                return str(val)
        except (KeyError, FileNotFoundError, AttributeError):
            pass
    return os.environ.get(key, default)


@dataclass(frozen=True)
class Settings:
    supabase_url: str
    supabase_service_role_key: str
    supabase_anon_key: Optional[str]
    gemini_api_key: str
    gemini_synth_model: str
    gemini_classify_model: str
    gemini_embed_model: str
    app_env: str
    log_queries: bool

    @classmethod
    def load(cls) -> "Settings":
        url = _read("SUPABASE_URL") or _read("NEXUS_SUPABASE_URL")
        srk = _read("SUPABASE_SERVICE_ROLE_KEY") or _read("NEXUS_SUPABASE_SERVICE_ROLE_KEY")
        ank = _read("SUPABASE_KEY") or _read("SUPABASE_ANON_KEY") or _read("NEXUS_SUPABASE_ANON_KEY")
        gem = _read("GOOGLE_API_KEY") or _read("GEMINI_API_KEY") or _read("NEXUS_GEMINI_API_KEY")

        if not url:
            raise RuntimeError("SUPABASE_URL not configured")
        if not srk:
            raise RuntimeError("SUPABASE_SERVICE_ROLE_KEY not configured")
        if not gem:
            raise RuntimeError("GOOGLE_API_KEY not configured")

        return cls(
            supabase_url=url,
            supabase_service_role_key=srk,
            supabase_anon_key=ank,
            gemini_api_key=gem,
            gemini_synth_model=_read("NEXUS_CHAT_MODEL", "gemini-2.5-pro") or "gemini-2.5-pro",
            gemini_classify_model=_read("NEXUS_CLASSIFY_MODEL", "gemini-2.5-flash") or "gemini-2.5-flash",
            gemini_embed_model=_read("NEXUS_EMBED_MODEL", "gemini-embedding-001") or "gemini-embedding-001",
            app_env=_read("APP_ENV", "beta") or "beta",
            log_queries=(_read("LOG_QUERIES", "true") or "true").lower() == "true",
        )


_settings: Optional[Settings] = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings.load()
    return _settings
