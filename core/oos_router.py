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
    "· IT 지원 (VPN / 네트워크 / PC / 시스템 오류)  → AX시스템팀\n"
    "· 인사 행정 (휴가 / 인사평가 / 연봉 / 인사기록)  → 인사교육팀\n"
    "· 일반 행정 (회의실 / 명함 / 비품)            → 총무팀\n"
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


# ── 구조화 OOS 라우팅 데이터 (카드 렌더용) ──────────────────────────
_OOS_ROUTING_ROWS: tuple[dict[str, str], ...] = (
    {"icon": "it",  "label": "IT 지원",  "examples": "VPN / 네트워크 / PC / 시스템 오류", "team": "AX시스템팀"},
    {"icon": "hr",  "label": "인사 행정", "examples": "휴가 / 인사평가 / 연봉 / 인사기록", "team": "인사교육팀"},
    {"icon": "ga",  "label": "일반 행정", "examples": "회의실 / 명함 / 비품",            "team": "총무팀"},
    {"icon": "ext", "label": "타사 사규", "examples": "신세계디에프 사규 전용 챗봇입니다", "team": ""},
)

_OOS_CRITICAL_NOTE: str = (
    "긴급 사안(폭행 · 성희롱 · 중대재해 · 정보유출 · 강력범죄)은 즉시 핫라인 또는 "
    "SHRS 로 신고해 주세요. 잘못 안내됐다고 판단되면 '신고/보고/피해' 등 명시적 "
    "용어를 포함해 다시 질문해 주세요."
)


def oos_routing_rows(supabase: Any | None = None) -> dict[str, Any]:
    """카드 렌더용 구조화 OOS 데이터. 인사 행은 hr_routing_line(hotlines)으로
    구동 — hr_chatbot_url 채우면 url 동반(버튼), 비면 hr_contact_text 문구.
    예외는 빈 url + 기본 문구로 안전 폴백."""
    from .config import load_hotlines, hr_routing_line
    try:
        hotlines = load_hotlines(supabase)
    except Exception:
        hotlines = {}
    rows: list[dict[str, str]] = []
    for r in _OOS_ROUTING_ROWS:
        row = dict(r)
        if r["icon"] == "hr":
            row["target_text"] = hr_routing_line(hotlines)
            row["url"] = (hotlines.get("hr_chatbot_url") or "").strip()
        else:
            row["target_text"] = r["team"]
            row["url"] = ""
        rows.append(row)
    return {"rows": rows, "critical_note": _OOS_CRITICAL_NOTE}


# ── PR-OOS-Gate: Retrieval-gated OOS (Reranker-as-judge) ─────────────────
# RRF 점수는 rank-fusion+boost 오염이라 임계치 부적합 → judge_relevance 사용.
# ⚙ 임계치 — 🚦 회귀 콘솔(라이브)로 보정 필요. 시작값 0.6:
#   "택시" 통과 / "회의실 예약"·"점심 메뉴" 차단 되도록 콘솔 돌려 조정.
_OOS_OVERRIDE_THRESHOLD: float = 0.85  # 0.6→0.85 (2026-06-05): judge_relevance 가 스치는/편재 문서를 0.8 로 과대평가 → OOS 오취소(회사주차장·VPN). 관측 데이터상 진짜 in-scope=0.9~1.0, 스치는 토픽=0.8 로 갈려 0.85 로 경계 보정. 콘솔 35/35 검증.


def gated_oos_decision(supabase: Any, question: str) -> bool:
    """분류기 out_of_scope 의 최종 게이트.
    True = OOS 유지(라우팅) / False = OOS 취소(정상 in-scope override).
      1) infer_categories 가 도메인 잡으면(무료 1차) -> in-scope(False)
      2) hybrid_search(top_k=2) 프로브 -> 청크 0 이면 OOS 유지(True)
      3) judge_relevance >= 임계치 -> in-scope(False), 미달 -> OOS 유지(True)
    예외는 fail-open(False) -> 정상 파이프라인(기존 안전관 정합)."""
    try:  # lazy import — chatbot<->oos_router 순환 회피
        from .chatbot import infer_categories
        # PR-Fix(인사-제외): '인사' 단독 매칭은 in-scope override 에서 제외.
        #   인사 행정(휴가/근태/인사평가/퇴사)은 분류기가 OOS 로 보냈는데 여기서
        #   override 되면 정상 파이프라인→무관 문서 오답(휴가→인감). 인사를 빼면
        #   probe/judge 로 진행 → HR 문서 없으면 OOS 카드. 컴플라이언스 인사
        #   (괴롭힘/징계)는 ① 분류기가 애초에 OOS 아님 + ② 문서 존재시 probe 가
        #   in-scope 판정 → 이중 보호로 안전.
        _cats = infer_categories(question)
        if _cats and any(c != "인사" for c in _cats):
            return False
    except Exception:
        pass
    # PR-Doc-Router: 카탈로그 기반 의미 판정 — probe/judge(0.85) 이전 실행.
    # 기존 구제 경로의 구조적 결함: probe 청크 관련도(judge)로 scope 를 판정
    # → 검색 어휘 gap = OOS 오판 (검색 실패와 범위 밖은 다른 문제). 라우터는
    # 사규 카탈로그를 보면서 질문 의도로 직접 판정하므로 이 결합이 끊긴다.
    # paraphrase 5/6 오차단 사례("중국 리서치 인터뷰 사례") 의 구조적 fix.
    # fail-open(ok=False) 또는 in+선택 0개(애매) 는 기존 probe/judge 로 폴백.
    try:
        from .doc_router import ENABLE_DOC_ROUTER, route_docs
        if ENABLE_DOC_ROUTER:
            _route = route_docs(supabase, question)
            if _route.get("ok"):
                if _route.get("doc_ids"):
                    return False  # 관련 사규 존재 → OOS 취소 (in-scope)
                if _route.get("scope") == "out":
                    return True   # 카탈로그 무관 + 행정 카테고리 명확 → OOS 유지
    except Exception:
        pass
    try:
        from .retriever import hybrid_search
        from .nexus_reranker import judge_relevance
        probe = hybrid_search(
            supabase, question=question, raw_question=question,
            categories=None, top_k=2,
        ) or []
        if not probe:
            return True
        return judge_relevance(question, probe) < _OOS_OVERRIDE_THRESHOLD
    except Exception:
        return False
