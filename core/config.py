"""환경 설정 및 핫라인 문구 중앙 관리.

Streamlit secrets → 환경변수 → 기본값 순으로 조회한다.
배포 형태(Phase 5) 결정 전까지 코드 수정 없이 운영 변경이 가능하도록
모든 외부값은 본 모듈을 경유한다.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Any


CATEGORIES: tuple[str, ...] = (
    "공통", "CSR", "공정거래", "정보보안", "안전",
    "재무", "영업", "총무", "환경",
)


def get_secret(key: str, default: str = "") -> str:
    try:
        import streamlit as st  # type: ignore
        if key in st.secrets:
            return str(st.secrets[key])
    except Exception:
        pass
    return os.environ.get(key, default)


@dataclass(frozen=True)
class Settings:
    supabase_url: str
    supabase_key: str
    # service_role 키는 RLS 를 우회한다. 반드시 비밀번호 게이트 뒤(관리자
    # 영역)에서만 사용해야 하며, 절대 일반 사용자 응답 경로에서 호출하지
    # 말 것. st.secrets / 환경변수로만 주입하고 리포지토리에 하드코딩 금지.
    supabase_service_role_key: str
    gemini_api_key: str
    chat_model: str
    embed_model: str
    embed_dim: int
    top_k: int
    temperature: float
    top_p: float
    # ── 베타/운영 환경 분기 ─────────────────────────────────
    # env_tag: query_logs.env 컬럼에 저장. 회사 이관 시 'beta-corp' → 'prod' 로 승격.
    # show_thinking: Gemini thinking parts 를 사용자 UI 에 노출할지. 베타 ON / 운영 OFF.
    # daily_query_limit: 1세션당 일일 질의 한도 (베타 비용 가드).
    env_tag: str
    show_thinking: bool
    daily_query_limit: int
    # consent_version: 동의서 문구를 변경하면 이 값을 올려서 참가자에게 재동의 강제.
    consent_version: str
    # ── 챗봇 멀티 provider (Gemini primary / Claude fallback) ──────
    # primary 가 503/429 등 transient 실패하면 fallback provider 로 1회 자동 전환.
    # 비용/품질 비교용 데이터는 query_logs.chat_provider 에 매 호출마다 기록.
    anthropic_api_key: str
    chat_provider: str           # 'gemini' | 'claude'
    chat_fallback_provider: str  # 'gemini' | 'claude' | '' (empty = no fallback)
    claude_model: str            # 기본 'claude-opus-4-7'
    claude_effort: str           # 'low' | 'medium' | 'high' | 'xhigh' | 'max' (max 는 Opus 전용)


@lru_cache(maxsize=1)
def settings() -> Settings:
    return Settings(
        supabase_url=get_secret("SUPABASE_URL"),
        supabase_key=get_secret("SUPABASE_KEY"),
        supabase_service_role_key=get_secret("SUPABASE_SERVICE_ROLE_KEY"),
        gemini_api_key=get_secret("GEMINI_API_KEY"),
        # 모델 버전은 운영 시점 최신 안정본으로 외부에서 갱신.
        chat_model=get_secret("NEXUS_CHAT_MODEL", "gemini-2.5-pro"),
        embed_model=get_secret("NEXUS_EMBED_MODEL", "gemini-embedding-001"),
        embed_dim=int(get_secret("NEXUS_EMBED_DIM", "768")),
        top_k=int(get_secret("NEXUS_TOP_K", "3")),
        temperature=float(get_secret("NEXUS_TEMPERATURE", "0")),
        top_p=float(get_secret("NEXUS_TOP_P", "0.1")),
        env_tag=get_secret("NEXUS_ENV", "beta-personal"),
        show_thinking=get_secret("NEXUS_SHOW_THINKING", "true").lower() in ("1", "true", "yes", "y"),
        daily_query_limit=int(get_secret("NEXUS_DAILY_QUERY_LIMIT", "100")),
        consent_version=get_secret("NEXUS_CONSENT_VERSION", "v1"),
        anthropic_api_key=get_secret("ANTHROPIC_API_KEY"),
        chat_provider=get_secret("NEXUS_CHAT_PROVIDER", "gemini").lower(),
        chat_fallback_provider=get_secret("NEXUS_CHAT_FALLBACK", "claude").lower(),
        claude_model=get_secret("NEXUS_CLAUDE_MODEL", "claude-opus-4-7"),
        claude_effort=get_secret("NEXUS_CLAUDE_EFFORT", "medium").lower(),
    )


# ── Hotline / 안내 문구 (DB 우선, fallback default) ──────────
_DEFAULT_HOTLINES: dict[str, str] = {
    "internal_report_url": "https://example.invalid/report",
    "external_hotline":    "고용노동부 1350",
    "ethics_hotline_url":  "https://example.invalid/ethics",
    "hr_contact_text":     "인사 규정·복리후생 등 인사 행정 사항은 인사팀에 문의해 주시기 바랍니다.",
    "hr_chatbot_url":      "",
}


def load_hotlines(supabase: Any | None = None) -> dict[str, str]:
    # 사용자(anon) 측 read 는 hotline_config_public view 를 통해서만 한다.
    # view 는 key/value 두 컬럼만 노출하므로 description / updated_at 같은
    # 운영 메타데이터는 anon 에 누설되지 않는다. 원본 hotline_config 테이블
    # 은 RLS 로 anon 차단을 유지하고, write 는 admin(service_role)이 원본
    # 테이블에 직접 수행한다.
    out = dict(_DEFAULT_HOTLINES)
    if supabase is None:
        return out
    try:
        rows = supabase.table("hotline_config_public").select("key,value").execute().data or []
        for r in rows:
            k = r.get("key"); v = r.get("value")
            if k and v is not None:
                out[k] = v
    except Exception:
        pass
    return out


def hr_routing_line(hotlines: dict[str, str]) -> str:
    """인사 챗봇 오픈 시 자연스러운 전환을 위한 단일 문구 빌더."""
    url = (hotlines.get("hr_chatbot_url") or "").strip()
    if url:
        return f"인사 챗봇으로 이동: {url}"
    return hotlines.get("hr_contact_text") or _DEFAULT_HOTLINES["hr_contact_text"]
