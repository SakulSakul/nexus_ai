"""NEXUS AI · 임직원용 Streamlit 프론트엔드 (PoC)."""

from __future__ import annotations

import streamlit as st

from core.chatbot import ask
from core.config import CATEGORIES, get_secret, load_hotlines, settings


st.set_page_config(page_title="NEXUS AI", page_icon="🛡️", layout="wide")

# ──────────────────────────────────────────────────────────────────────────────
#  Global CSS
# ──────────────────────────────────────────────────────────────────────────────
_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

html, body, .stApp {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
}
#MainMenu, footer, header { visibility: hidden; }

/* ── Sidebar ── */
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #0f172a 0%, #1a2744 100%) !important;
}
[data-testid="stSidebar"] > div { background: transparent !important; }
[data-testid="stSidebar"] p,
[data-testid="stSidebar"] span,
[data-testid="stSidebar"] label,
[data-testid="stSidebar"] .stMarkdown { color: #94a3b8 !important; }
[data-testid="stSidebar"] h3 { color: #f1f5f9 !important; }
[data-testid="stSidebar"] hr { border-color: rgba(255,255,255,0.07) !important; }
[data-testid="stSidebar"] [data-testid="stSelectbox"] > div > div {
    background: rgba(255,255,255,0.07) !important;
    border: 1px solid rgba(255,255,255,0.12) !important;
    color: #f1f5f9 !important;
    border-radius: 8px !important;
}
[data-testid="stSidebar"] .stSelectbox svg { fill: #94a3b8 !important; }
[data-testid="stSidebar"] .stButton > button {
    background: rgba(255,255,255,0.07) !important;
    border: 1px solid rgba(255,255,255,0.13) !important;
    color: #e2e8f0 !important;
    border-radius: 8px !important;
    font-size: 0.85rem !important;
}
[data-testid="stSidebar"] .stButton > button:hover {
    background: rgba(255,255,255,0.13) !important;
    border-color: rgba(255,255,255,0.22) !important;
}
[data-testid="stSidebar"] input[type="password"] {
    background: rgba(255,255,255,0.07) !important;
    border: 1px solid rgba(255,255,255,0.12) !important;
    color: #f1f5f9 !important;
    border-radius: 8px !important;
}

/* ── Main area background ── */
[data-testid="stMain"] { background: #f1f5f9; }
[data-testid="block-container"] { padding-top: 1.5rem !important; }

/* ── All default buttons (example Qs, etc.) ── */
.stButton > button {
    text-align: left !important;
    white-space: normal !important;
    height: auto !important;
    padding: 0.8rem 1rem !important;
    border-radius: 10px !important;
    border: 1px solid #e2e8f0 !important;
    background: #ffffff !important;
    color: #334155 !important;
    font-size: 0.875rem !important;
    font-weight: 500 !important;
    box-shadow: 0 1px 3px rgba(0,0,0,0.06) !important;
    transition: all 0.15s ease !important;
    line-height: 1.45 !important;
}
.stButton > button:hover {
    border-color: #3b82f6 !important;
    color: #1d4ed8 !important;
    background: #eff6ff !important;
    box-shadow: 0 4px 14px rgba(59,130,246,0.18) !important;
    transform: translateY(-1px) !important;
}
.stButton > button[kind="primary"] {
    background: linear-gradient(135deg, #1d4ed8, #3b82f6) !important;
    border: none !important;
    color: #ffffff !important;
    font-weight: 600 !important;
    box-shadow: 0 2px 8px rgba(59,130,246,0.38) !important;
}
.stButton > button[kind="primary"]:hover {
    background: linear-gradient(135deg, #1e40af, #2563eb) !important;
    color: #ffffff !important;
    box-shadow: 0 4px 16px rgba(59,130,246,0.46) !important;
}

/* ── Chat messages ── */
[data-testid="stChatMessage"] {
    border-radius: 14px !important;
    padding: 1rem 1.25rem !important;
    margin-bottom: 0.75rem !important;
    border: 1px solid #e2e8f0 !important;
    background: #ffffff !important;
    box-shadow: 0 1px 4px rgba(0,0,0,0.04) !important;
}

/* ── Chat input ── */
[data-testid="stChatInput"] textarea {
    border-radius: 12px !important;
    border: 1.5px solid #e2e8f0 !important;
    background: #ffffff !important;
    font-family: inherit !important;
    font-size: 0.93rem !important;
    box-shadow: 0 2px 12px rgba(0,0,0,0.07) !important;
    transition: border-color 0.15s ease, box-shadow 0.15s ease !important;
}
[data-testid="stChatInput"] textarea:focus {
    border-color: #3b82f6 !important;
    box-shadow: 0 2px 16px rgba(59,130,246,0.14) !important;
}

/* ── Expander ── */
[data-testid="stExpander"] {
    border: 1px solid #e2e8f0 !important;
    border-radius: 10px !important;
    background: #ffffff !important;
    box-shadow: none !important;
    margin-top: 0.5rem !important;
}
[data-testid="stExpander"] summary {
    font-size: 0.82rem !important;
    color: #64748b !important;
    font-weight: 500 !important;
}

/* ── Alert ── */
[data-testid="stAlert"] { border-radius: 10px !important; }

/* ── Link button ── */
[data-testid="stLinkButton"] > a {
    border-radius: 10px !important;
    border: 1.5px solid #e2e8f0 !important;
    background: #ffffff !important;
    color: #1d4ed8 !important;
    font-weight: 500 !important;
    font-size: 0.875rem !important;
    transition: all 0.15s ease !important;
}
[data-testid="stLinkButton"] > a:hover {
    background: #eff6ff !important;
    border-color: #3b82f6 !important;
}

/* ── Caption ── */
.stCaption { color: #94a3b8 !important; font-size: 0.78rem !important; }

/* ── Custom HTML components ── */
.nexus-section-label {
    font-size: 0.78rem;
    font-weight: 600;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: #94a3b8;
    margin-bottom: 0.65rem;
}
.doc-ref-card {
    border: 1px solid #e2e8f0;
    border-radius: 10px;
    padding: 0.75rem 1rem;
    background: #f8fafc;
    margin-bottom: 0.5rem;
}
.doc-ref-title {
    font-size: 0.85rem;
    font-weight: 600;
    color: #1e293b;
    margin-bottom: 0.3rem;
    display: flex;
    align-items: center;
    gap: 6px;
}
.doc-ref-text {
    font-size: 0.8rem;
    color: #64748b;
    line-height: 1.5;
    margin: 0;
}
.badge {
    display: inline-block;
    font-size: 0.67rem;
    font-weight: 700;
    padding: 2px 7px;
    border-radius: 5px;
    letter-spacing: 0.04em;
    vertical-align: middle;
    flex-shrink: 0;
}
.badge-rule    { background: #dbeafe; color: #1d4ed8; }
.badge-case    { background: #dcfce7; color: #166534; }
.badge-penalty { background: #fef3c7; color: #92400e; }
.critical-banner {
    display: flex;
    align-items: center;
    gap: 10px;
    background: linear-gradient(135deg, #fef2f2, #fee2e2);
    border: 1.5px solid #fca5a5;
    border-left: 4px solid #ef4444;
    border-radius: 10px;
    padding: 0.7rem 1rem;
    margin-bottom: 0.75rem;
    color: #991b1b;
    font-weight: 600;
    font-size: 0.875rem;
}
.nexus-hero {
    padding: 0.5rem 0 1.5rem;
}
.nexus-hero-title {
    font-size: 1.85rem;
    font-weight: 700;
    color: #0f172a;
    letter-spacing: -0.025em;
    margin: 0 0 0.3rem;
    line-height: 1.2;
}
.nexus-hero-sub {
    font-size: 0.92rem;
    color: #64748b;
    margin: 0;
}
</style>
"""

_EXAMPLE_QUESTIONS = [
    "거래처로부터 선물을 받아도 되나요?",
    "직장 내 괴롭힘 신고는 어떻게 하나요?",
    "부서 회식 중 음주 관련 사규는 어떻게 되나요?",
    "재무 결재 기준이 어떻게 되나요?",
    "정보보안 위반 시 어떤 처분을 받나요?",
    "공정거래 관련 주의사항이 무엇인가요?",
]

_HOTLINE_LABELS = {
    "internal_report_url": "사내 익명 제보채널 URL",
    "external_hotline":    "외부 상담채널",
    "ethics_hotline_url":  "윤리팀 익명 제보채널 URL",
    "hr_contact_text":     "인사팀 문의 안내 문구",
    "hr_chatbot_url":      "인사 챗봇 URL",
}

_KIND_BADGE = {
    "rule":    ('<span class="badge badge-rule">사규</span>', "사규"),
    "case":    ('<span class="badge badge-case">사례</span>', "사례"),
    "penalty": ('<span class="badge badge-penalty">징계기준</span>', "징계기준"),
}


@st.cache_resource(show_spinner=False)
def _supabase():
    from supabase import create_client
    s = settings()
    if not s.supabase_url or not s.supabase_key:
        return None
    return create_client(s.supabase_url, s.supabase_key)


def _admin_panel(sb, hotlines: dict) -> None:
    with st.expander("🔐 관리자 설정"):
        admin_pw = get_secret("ADMIN_PASSWORD")
        if not admin_pw:
            st.info("ADMIN_PASSWORD secret을 설정하면 관리자 기능이 활성화됩니다.")
            return

        if not st.session_state.get("admin_authenticated"):
            with st.form("sidebar_admin_login"):
                pw = st.text_input("관리자 비밀번호", type="password")
                submitted = st.form_submit_button("로그인", type="primary")
            if submitted:
                if pw == admin_pw:
                    st.session_state["admin_authenticated"] = True
                    st.rerun()
                else:
                    st.error("비밀번호가 틀렸습니다.")
            return

        st.success("인증 완료")
        col_logout, _ = st.columns([1, 2])
        if col_logout.button("로그아웃", key="sidebar_logout"):
            st.session_state["admin_authenticated"] = False
            st.rerun()

        st.markdown("---")
        st.page_link("pages/admin.py", label="🛠️ Admin 대시보드 열기", use_container_width=True)
        st.markdown("---")
        st.markdown("**안내 문구 / URL 설정**")

        updated: dict[str, str] = {}
        for key, label in _HOTLINE_LABELS.items():
            updated[key] = st.text_input(
                label, value=hotlines.get(key, ""), key=f"admin_{key}"
            )
        if st.button("저장", key="admin_save"):
            if sb is None:
                st.error("Supabase 연결 없음")
                return
            try:
                for k, v in updated.items():
                    sb.table("hotline_config").upsert(
                        {"key": k, "value": v}, on_conflict="key"
                    ).execute()
                st.success("저장 완료. 새로고침 후 반영됩니다.")
            except Exception as e:
                st.error(f"저장 실패: {e}")


def _sidebar(sb, hotlines: dict) -> str:
    with st.sidebar:
        st.markdown(
            """
            <div style="padding:1.25rem 0 0.5rem">
              <div style="display:flex;align-items:center;gap:10px;margin-bottom:4px">
                <span style="font-size:1.5rem">🛡️</span>
                <span style="font-size:1.2rem;font-weight:700;color:#f1f5f9;letter-spacing:-0.01em">NEXUS AI</span>
              </div>
              <p style="font-size:0.78rem;color:#64748b;margin:0;padding-left:2px">
                전사 컴플라이언스 어시스턴트
              </p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.markdown("---")
        st.markdown(
            '<p class="nexus-section-label">질의 범위</p>',
            unsafe_allow_html=True,
        )
        cat = st.selectbox(
            "카테고리",
            options=("전체",) + CATEGORIES,
            index=0,
            label_visibility="collapsed",
        )
        st.markdown("---")
        st.caption(
            "본 챗봇은 사규·윤리강령·사례집 기반 답변을 제공합니다. "
            "인사 행정·신고 절차는 인사팀으로 문의하세요."
        )
        st.markdown("---")
        _admin_panel(sb, hotlines)
        return cat


def _hotline_button(hotlines: dict[str, str]) -> None:
    url = hotlines.get("ethics_hotline_url") or hotlines.get("internal_report_url")
    if url:
        st.link_button("🔔 윤리팀 익명 제보 채널로 연결", url, use_container_width=True)


def _render_contexts(contexts: list[dict]) -> None:
    if not contexts:
        return
    with st.expander("📎 참조 문서 보기", expanded=False):
        for c in contexts:
            kind = c.get("doc_kind", "")
            badge_html, _ = _KIND_BADGE.get(kind, ("", ""))
            title = c.get("doc_title") or "문서"
            cite = ""
            if c.get("article_no"):
                cite = c["article_no"]
            elif c.get("case_no"):
                cite = f"사례집 #{c['case_no']}"
            cite_html = f'<span style="color:#94a3b8;font-size:0.78rem;margin-left:4px">{cite}</span>' if cite else ""
            text = (c.get("text") or "")[:500]
            st.markdown(
                f"""
                <div class="doc-ref-card">
                  <div class="doc-ref-title">{badge_html}{title}{cite_html}</div>
                  <p class="doc-ref-text">{text}</p>
                </div>
                """,
                unsafe_allow_html=True,
            )


def _show_example_questions() -> str | None:
    st.markdown(
        '<p class="nexus-section-label" style="margin-top:1rem">이런 질문을 해보세요</p>',
        unsafe_allow_html=True,
    )
    cols = st.columns(2)
    for i, q in enumerate(_EXAMPLE_QUESTIONS):
        if cols[i % 2].button(q, key=f"eq_{i}", use_container_width=True):
            return q
    return None


def _run_ask(sb, q: str, cat: str, hotlines: dict) -> None:
    st.session_state["history"].append(("user", q, {}))
    with st.chat_message("user"):
        st.markdown(q)

    with st.chat_message("assistant"):
        with st.spinner("관련 문서 검색 및 답변 생성 중..."):
            try:
                ans = ask(sb, question=q, category=cat)
            except Exception as e:
                st.error(f"오류가 발생했습니다: {e}")
                return

        if ans.thinking:
            with st.expander("💭 생각 과정 보기", expanded=False):
                st.markdown(ans.thinking)

        if ans.is_critical:
            st.markdown(
                '<div class="critical-banner">'
                '⚠️&nbsp; 본 사안은 <strong>심각 사안 응답 모드</strong>로 처리되었습니다.'
                '</div>',
                unsafe_allow_html=True,
            )

        st.markdown(ans.text)
        st.caption(f"⏱ {ans.elapsed:.1f}s")
        _render_contexts(ans.contexts)
        _hotline_button(hotlines)

    st.session_state["history"].append((
        "assistant", ans.text,
        {
            "contexts": ans.contexts,
            "critical": ans.is_critical,
            "kind": ans.critical_kind,
            "thinking": ans.thinking,
            "elapsed": ans.elapsed,
        },
    ))


def main():
    st.markdown(_CSS, unsafe_allow_html=True)

    sb = _supabase()
    if sb is None:
        st.error("⚠️ Supabase 설정이 없습니다. SUPABASE_URL / SUPABASE_KEY 를 secrets 에 추가하세요.")
        st.stop()

    if "history" not in st.session_state:
        st.session_state["history"] = []

    hotlines = load_hotlines(sb)
    cat = _sidebar(sb, hotlines)

    # Hero
    st.markdown(
        """
        <div class="nexus-hero">
          <p class="nexus-hero-title">무엇을 도와드릴까요?</p>
          <p class="nexus-hero-sub">
            사규 · 윤리강령 · 사례집 · 징계규정을 통합 검색합니다.
            &nbsp;|&nbsp; 이름·부서 등 식별정보는 자동 마스킹됩니다.
          </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Chat history replay
    for role, content, meta in st.session_state["history"]:
        with st.chat_message(role):
            if role == "assistant" and meta.get("thinking"):
                with st.expander("💭 생각 과정 보기", expanded=False):
                    st.markdown(meta["thinking"])
            if role == "assistant" and meta.get("critical"):
                st.markdown(
                    '<div class="critical-banner">'
                    '⚠️&nbsp; 본 사안은 <strong>심각 사안 응답 모드</strong>로 처리되었습니다.'
                    '</div>',
                    unsafe_allow_html=True,
                )
            st.markdown(content)
            if role == "assistant" and meta.get("elapsed"):
                st.caption(f"⏱ {meta['elapsed']:.1f}s")
            if role == "assistant" and meta.get("contexts"):
                _render_contexts(meta["contexts"])
            if role == "assistant":
                _hotline_button(hotlines)

    # Example questions (shown only when no history)
    clicked_q: str | None = None
    if not st.session_state["history"]:
        clicked_q = _show_example_questions()

    q = st.chat_input("질문을 입력하세요…") or clicked_q
    if not q:
        return

    _run_ask(sb, q, cat, hotlines)


if __name__ == "__main__":
    main()
