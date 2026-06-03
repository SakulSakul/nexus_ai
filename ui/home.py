"""DF COMPASS 빈 홈(첫 진입) 렌더 — app.py 에서 분리(동작 무변경).

에디토리얼 히어로 + 중앙 입력 + 추천 칩(FAQ show_on_home, 없으면 폴백).
"""

import streamlit as st


_HERO_PILLS_FALLBACK = [
    ("선물 받았어요", "거래처에서 선물을 받아도 되나요?"),
    ("동료 부상", "동료가 다쳤어요. 긴급 보고는 어떻게 하나요?"),
    ("법인카드", "법인카드를 개인 용도로 사용해도 되나요?"),
]


@st.cache_data(ttl=300, show_spinner=False)
def _home_chip_items() -> list:
    """FAQ 캐시(show_on_home) 기반 홈 칩 [(label, query)]. 실패/빈 결과 시 []."""
    try:
        from core.faq_cache import faq_cache_home_chips
        out = []
        for _r in faq_cache_home_chips(limit=3):
            _q = (_r.get("query_display") or "").strip()
            if not _q:
                continue
            _label = (_r.get("home_label") or "").strip() or (
                _q[:12] + ("\u2026" if len(_q) > 12 else "")
            )
            out.append((_label, _q))
        return out
    except Exception:
        return []


def _render_empty_state(sb) -> None:
    """첫 진입(빈 홈) — 목업 정렬: 상단 바 + 히어로 + 중앙 입력 + 트러스트 + 그룹 칩.

    옛 날씨·인사 카드와 평면 SAMPLE_QUESTIONS 는 빈 홈 렌더에서 제외(목업 일치).
    `_cached_dynamic_greeting` / `get_daily_tip` / `_show_example_questions` 등
    함수·로직은 코드에 보존 — 미래 재배치 여지.
    """
    # 빈 홈 한정 CSS: 본문 880px 가운데 정렬(전 요소 정렬) + 하단 chat_input 숨김
    # (중앙 입력과 중복 방지). 답변 화면에선 본 함수 미호출 → 자동 원복.
    st.markdown(
        """
        <style>
        [data-testid="stMainBlockContainer"], .block-container{max-width:960px !important;margin-left:3rem !important;margin-right:auto !important;}
        [data-testid="stChatInput"]{display:none !important;}
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        """
        <div class="nx-topbar2">
          <div class="nx-topbar2-brand">
            <span class="nx-compass"></span>
            <span class="nx-topbar2-name">DF COMPASS</span>
            <span class="nx-topbar2-tag">사규의 나침반</span>
          </div>
          <span class="nx-topbar2-beta">베타 · 입력 내용 학습 안 함</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        """
        <div class="nx-hero2">
          <p class="nx-hero2-eyebrow">사규의 나침반 · Compliance Compass</p>
          <h1 class="nx-hero2-title">무엇을 확인해 드릴까요<span class="nx-hero2-q">?</span></h1>
        </div>
        """,
        unsafe_allow_html=True,
    )

    def _hero_submit() -> None:
        _v = (st.session_state.get("hero_ask_input") or "").strip()
        if _v:
            st.session_state["clicked_q"] = _v

    st.markdown(  # 히어로 입력창 확대 — st-key 스코프(빈 홈 전용)
        "<style>"
        '.st-key-hero_ask_input div[data-baseweb="input"]{border-radius:14px !important;border:1.5px solid var(--c-border) !important;background:#fff !important;box-shadow:0 2px 12px rgba(31,30,29,0.06) !important;min-height:58px !important;display:flex !important;align-items:center !important;}'
        '.st-key-hero_ask_input div[data-baseweb="input"]:focus-within{border-color:var(--c-accent) !important;box-shadow:0 0 0 3px rgba(200,16,46,0.12) !important;}'
        '.st-key-hero_ask_input div[data-baseweb="base-input"]{height:100% !important;background:transparent !important;}'
        '.st-key-hero_ask_input input{height:56px !important;font-size:17px !important;padding:0 22px !important;color:var(--c-primary) !important;}'
        '.st-key-hero_ask_input input::placeholder{font-size:15.5px !important;color:#9A968D !important;}'
        '.st-key-hero_send_btn button{height:58px !important;min-height:58px !important;border-radius:14px !important;font-size:28px !important;font-weight:700 !important;line-height:1 !important;}'
        '[class*="st-key-hchip_"] button{min-height:60px !important;display:flex !important;align-items:center !important;justify-content:center !important;text-align:center !important;white-space:normal !important;line-height:1.45 !important;padding:8px 14px !important;}'
        "</style>",
        unsafe_allow_html=True,
    )
    _ic1, _ic2 = st.columns([20, 3], vertical_alignment="center")
    with _ic1:
        st.text_input(
            "질문 입력",
            key="hero_ask_input",
            label_visibility="collapsed",
            placeholder="사규·윤리 관련 무엇이든 물어보세요…",
            on_change=_hero_submit,
        )
    with _ic2:
        if st.button("↑", key="hero_send_btn", type="primary", use_container_width=True):
            _v = (st.session_state.get("hero_ask_input") or "").strip()
            if _v:
                st.session_state["clicked_q"] = _v
                st.rerun()

    # 목업 미니멀: 입력창 아래 작은 칩 3개만 (그룹·트러스트 제거).
    # 라벨은 짧게, 실제 질의는 full question 으로 매핑.
    st.markdown(
        '<style>'
        '[class*="st-key-hpill_"] button{min-height:36px !important;border-radius:999px !important;'
        'border:1px solid var(--c-border) !important;background:#fff !important;color:#6B6760 !important;'
        'font-size:13px !important;font-weight:500 !important;padding:6px 12px !important;'
        'box-shadow:none !important;white-space:nowrap !important;}'
        '[class*="st-key-hpill_"] button:hover{border-color:var(--c-accent) !important;color:var(--c-accent) !important;}'
        '</style>',
        unsafe_allow_html=True,
    )
    _hero_pills = _home_chip_items() or _HERO_PILLS_FALLBACK
    _pcols = st.columns(len(_hero_pills))
    for _pi, (_plabel, _pq) in enumerate(_hero_pills):
        if _pcols[_pi].button(_plabel, key="hpill_" + str(_pi), use_container_width=True):
            st.session_state["clicked_q"] = _pq
            st.rerun()
