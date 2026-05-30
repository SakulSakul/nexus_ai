"""PR-Phase-18.5.2: OOS (Out of Scope) Fast Skip — 사규 범위 밖 query 즉시 라우팅.

선례 미러링: core/faq_cache.py (flag 패턴) + core/config.py:load_hotlines
(DB 우선 + fallback 패턴).

설계 결정 (사쿨님 확정):
- ENABLE_OOS_ROUTING 기본 OFF — 머지 시 회귀 0, 활성화는 secrets 변경 1단계.
- DB(hotline_config.oos_routing_text) 우선 + _DEFAULT_OOS_MESSAGE fallback.
- 빈 값/공백 DB 값은 default 를 덮어쓰지 않음 (load_hotlines 패턴 정합 —
  admin 실수로 메시지가 빈 채로 사용자에게 노출되는 사고 방지).
- 메시지 끝 self-correction 문단(4문단째) = 가드 1~3 가 모두 뚫린 최악 경우
  사용자가 명시 키워드로 재질의하도록 유도하는 4차 안전망 ⭐.
"""
from __future__ import annotations

from typing import Any

from .config import get_secret


# ── Feature flag (기본 OFF, secrets 의 ENABLE_OOS_ROUTING="true" 로 활성화) ──
ENABLE_OOS_ROUTING: bool = (
    get_secret("ENABLE_OOS_ROUTING", "false").lower() == "true"
)


# ── 코드 fallback (DB 부재/실패/빈값 시) ──────────────────────────
_DEFAULT_OOS_MESSAGE: str = (
    "요청하신 내용은 사규 챗봇의 범위를 벗어납니다. 담당 창구로 안내드립니다.\n\n"
    "· IT 지원 (VPN / 네트워크 / PC / 시스템 오류)  → IT팀\n"
    "· 인사 행정 (휴가 / 평가 / 연봉 / 인사기록)    → 인사교육팀\n"
    "· 일반 행정 (회의실 / 카드 / 출장 / 비품)      → 총무팀\n"
    "· 타사 사규                                    → "
    "본 챗봇은 신세계디에프 사규 전용입니다.\n\n"
    "※ 긴급 사안(폭행 · 성희롱 · 중대재해 · 정보유출 · 강력범죄)은 즉시 핫라인 또는\n"
    "   SHRS 로 신고해 주세요 — 본 안내가 잘못 나왔다고 판단되면 채팅창에 그 사안의\n"
    "   '신고/보고/피해' 등 명시적 용어를 포함해 다시 질문해 주세요."
)


def oos_routing_message(supabase: Any | None = None) -> str:
    """OOS 라우팅 메시지 — hotline_config_public view 의 oos_routing_text 우선,
    DB 부재·실패·빈값 시 _DEFAULT_OOS_MESSAGE fallback.

    선례 load_hotlines (core/config.py:137) 패턴 동일. anon 키로 view 만 조회
    하므로 권한 안전 (description/updated_at 누설 차단).
    """
    if supabase is None:
        return _DEFAULT_OOS_MESSAGE
    try:
        rows = (
            supabase.table("hotline_config_public")
            .select("key,value")
            .eq("key", "oos_routing_text")
            .limit(1)
            .execute()
            .data
            or []
        )
        if rows:
            v = rows[0].get("value")
            if v and str(v).strip():
                return str(v)
    except Exception:
        pass
    return _DEFAULT_OOS_MESSAGE
