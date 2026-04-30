"""NEXUS AI · 임직원용 Streamlit 프론트엔드 (PoC)."""

from __future__ import annotations

import streamlit as st
from streamlit.components.v1 import html as _components_html

from core.chatbot import ask
from core.config import CATEGORIES, get_secret, load_hotlines, settings


st.set_page_config(page_title="NEXUS AI", page_icon="🛡️", layout="wide")

# ──────────────────────────────────────────────────────────────────────────────
#  Design System: Shinsegae Newsroom Editorial
#  - Monochrome: #1A1A1A / #333 / #767 / #AEAEAE / #E0E0E0 / #F7F7F7 / #FFF
#  - Font: Pretendard
#  - No gradients · No shadows · No border-radius · No color accents
#  - 4px black top frame · 1px #E0E0E0 borders · 4px #1A1A1A card accents
# ──────────────────────────────────────────────────────────────────────────────
_CSS = """
<style>
@import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.min.css');
@import url('https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:opsz,wght,FILL,GRAD@20..48,100..700,0..1,-50..200');
@import url('https://fonts.googleapis.com/css2?family=Material+Symbols+Rounded:opsz,wght,FILL,GRAD@20..48,100..700,0..1,-50..200');

/* Material icons fallback — hide leaking icon names if font fails to load */
[data-testid="stSidebarCollapseButton"] *,
[data-testid="stSidebarCollapsedControl"] *,
[data-testid="stIconMaterial"] {
  font-family: 'Material Symbols Rounded','Material Symbols Outlined', sans-serif !important;
  font-feature-settings: 'liga' !important;
  -webkit-font-feature-settings: 'liga' !important;
}

/* Sidebar collapse/expand button — solid black square, no tooltip */
[data-testid="stSidebarCollapseButton"],
[data-testid="stSidebarCollapsedControl"] {
  background: var(--c-bg) !important;
  border: 1px solid var(--c-border) !important;
}
[data-testid="stSidebarCollapseButton"] button,
[data-testid="stSidebarCollapsedControl"] button {
  color: var(--c-primary) !important;
  background: transparent !important;
  border: none !important;
  width: 32px !important;
  height: 32px !important;
}
[data-testid="stSidebarCollapseButton"] button:hover,
[data-testid="stSidebarCollapsedControl"] button:hover {
  background: var(--c-surface) !important;
}

/* Floating sidebar expand control — sits above the 4px top frame so the
   button is reachable when the sidebar is collapsed. */
[data-testid="stSidebarCollapsedControl"] {
  position: fixed !important;
  top: 12px !important;
  left: 12px !important;
  z-index: 10000 !important;
  width: 36px !important;
  height: 36px !important;
  display: flex !important;
  align-items: center !important;
  justify-content: center !important;
  background: var(--c-primary) !important;
  border: 1px solid var(--c-primary) !important;
}
[data-testid="stSidebarCollapsedControl"] button,
[data-testid="stSidebarCollapsedControl"] svg {
  color: #FFFFFF !important;
  fill: #FFFFFF !important;
}
[data-testid="stSidebarCollapsedControl"] button:hover {
  background: #333333 !important;
}

/* Hide all tooltips (the gray hover labels that show button title text) */
[data-baseweb="tooltip"],
[role="tooltip"],
.stTooltipIcon,
.stTooltipContent {
  display: none !important;
}
button[title]:hover::after,
button[aria-label]:hover::after {
  display: none !important;
}

:root {
  --c-primary:  #1A1A1A;
  --c-text:     #333333;
  --c-caption:  #767676;
  --c-muted:    #AEAEAE;
  --c-border:   #E0E0E0;
  --c-surface:  #F7F7F7;
  --c-bg:       #FFFFFF;
  --font: 'Pretendard', -apple-system, 'Apple SD Gothic Neo', 'Noto Sans KR', sans-serif;
}

/* ── Reset ── */
html, body, .stApp {
  font-family: var(--font) !important;
  background: var(--c-bg) !important;
  color: var(--c-text) !important;
}
#MainMenu, footer { visibility: hidden; }
[data-testid="stHeader"] {
  background: transparent !important;
  height: auto !important;
  visibility: visible !important;
}
[data-testid="stHeader"] [data-testid="stToolbar"],
[data-testid="stHeader"] [data-testid="stDecoration"],
[data-testid="stHeader"] [data-testid="stStatusWidget"] {
  display: none !important;
}
[data-testid="stSidebarCollapsedControl"] {
  visibility: visible !important;
  display: flex !important;
  opacity: 1 !important;
  pointer-events: auto !important;
}
[data-testid="stSidebarCollapseButton"]   { visibility: visible !important; }
[data-testid="stToolbar"] { display: none !important; }
[data-testid="stDecoration"] { display: none !important; }
* { box-sizing: border-box; }

/* ── 4px top frame ── */
.nx-topbar {
  position: fixed;
  top: 0; left: 0; right: 0;
  height: 4px;
  background: var(--c-primary);
  z-index: 1;
  pointer-events: none;
}

/* ── Sidebar ── */
[data-testid="stSidebar"] {
  background: var(--c-surface) !important;
  border-right: 1px solid var(--c-border) !important;
}
[data-testid="stSidebar"] > div { background: transparent !important; }
[data-testid="stSidebar"] p,
[data-testid="stSidebar"] span,
[data-testid="stSidebar"] label,
[data-testid="stSidebar"] .stMarkdown,
[data-testid="stSidebar"] .stCaption {
  font-family: var(--font) !important;
  color: var(--c-caption) !important;
}
[data-testid="stSidebar"] h1,
[data-testid="stSidebar"] h2,
[data-testid="stSidebar"] h3 { color: var(--c-primary) !important; }
[data-testid="stSidebar"] hr {
  border: none !important;
  border-top: 1px solid var(--c-border) !important;
  margin: 20px 0 !important;
}

/* Sidebar selectbox */
[data-testid="stSidebar"] [data-testid="stSelectbox"] > div > div {
  background: var(--c-bg) !important;
  border: 1px solid var(--c-border) !important;
  border-radius: 0 !important;
  color: var(--c-primary) !important;
  font-family: var(--font) !important;
  font-size: 13px !important;
  box-shadow: none !important;
}
[data-testid="stSidebar"] [data-testid="stSelectbox"] > div > div:focus-within {
  border-color: var(--c-primary) !important;
}

/* Sidebar buttons */
[data-testid="stSidebar"] .stButton > button {
  background: var(--c-bg) !important;
  border: 1px solid var(--c-border) !important;
  border-radius: 0 !important;
  color: var(--c-primary) !important;
  font-family: var(--font) !important;
  font-size: 12px !important;
  font-weight: 500 !important;
  box-shadow: none !important;
  letter-spacing: 0.03em !important;
}
[data-testid="stSidebar"] .stButton > button:hover {
  background: var(--c-surface) !important;
  border-color: var(--c-primary) !important;
  box-shadow: none !important;
  transform: none !important;
}
[data-testid="stSidebar"] input,
[data-testid="stSidebar"] input[type="password"] {
  background: var(--c-bg) !important;
  border: 0 !important;
  border-bottom: 1px solid var(--c-border) !important;
  border-radius: 0 !important;
  color: var(--c-primary) !important;
  font-family: var(--font) !important;
  font-size: 13px !important;
  box-shadow: none !important;
}
[data-testid="stSidebar"] input:focus {
  border-bottom: 2px solid var(--c-primary) !important;
}

/* ── Main area ── */
[data-testid="stMain"] { background: var(--c-bg) !important; }
[data-testid="block-container"] { padding-top: 2rem !important; }

/* ── All buttons (default) ── */
.stButton > button {
  font-family: var(--font) !important;
  background: var(--c-bg) !important;
  border: 1px solid var(--c-border) !important;
  border-radius: 0 !important;
  color: var(--c-primary) !important;
  font-size: 13px !important;
  font-weight: 500 !important;
  padding: 0.75rem 1rem !important;
  text-align: left !important;
  white-space: normal !important;
  height: auto !important;
  line-height: 1.6 !important;
  box-shadow: none !important;
  transition: background 0.12s ease, border-color 0.12s ease !important;
}
.stButton > button:hover {
  background: var(--c-surface) !important;
  border-color: var(--c-primary) !important;
  box-shadow: none !important;
  transform: none !important;
}

/* Primary button */
.stButton > button[kind="primary"] {
  background: var(--c-primary) !important;
  border: 1px solid var(--c-primary) !important;
  color: #FFFFFF !important;
  font-weight: 600 !important;
  letter-spacing: 0.03em !important;
  box-shadow: none !important;
}
.stButton > button[kind="primary"]:hover {
  background: #333333 !important;
  border-color: #333333 !important;
  box-shadow: none !important;
  transform: none !important;
}

/* ── Chat messages ── */
[data-testid="stChatMessage"] {
  border: 1px solid var(--c-border) !important;
  border-radius: 0 !important;
  padding: 1.25rem 1.5rem !important;
  margin-bottom: 2px !important;
  background: var(--c-bg) !important;
  box-shadow: none !important;
}

/* ── Chat input ── */
[data-testid="stChatInput"] textarea {
  font-family: var(--font) !important;
  border: 0 !important;
  border-top: 1px solid var(--c-border) !important;
  border-radius: 0 !important;
  background: var(--c-bg) !important;
  font-size: 13px !important;
  color: var(--c-text) !important;
  box-shadow: none !important;
  resize: none !important;
}
[data-testid="stChatInput"] textarea:focus {
  border-top: 2px solid var(--c-primary) !important;
  box-shadow: none !important;
}
[data-testid="stChatInput"] {
  border: 0 !important;
  border-top: 1px solid var(--c-border) !important;
  border-radius: 0 !important;
  box-shadow: none !important;
  background: var(--c-bg) !important;
}

/* ── Expander ── */
[data-testid="stExpander"] {
  border: 1px solid var(--c-border) !important;
  border-radius: 0 !important;
  background: var(--c-bg) !important;
  box-shadow: none !important;
  margin-top: 12px !important;
}
[data-testid="stExpander"] summary {
  font-family: var(--font) !important;
  font-size: 11px !important;
  font-weight: 700 !important;
  letter-spacing: 0.12em !important;
  text-transform: uppercase !important;
  color: var(--c-caption) !important;
}

/* ── Alert ── */
[data-testid="stAlert"] {
  border-radius: 0 !important;
  box-shadow: none !important;
  font-family: var(--font) !important;
}

/* ── Link button (hotline) ── */
[data-testid="stLinkButton"] > a {
  font-family: var(--font) !important;
  background: var(--c-primary) !important;
  border: 1px solid var(--c-primary) !important;
  border-radius: 0 !important;
  color: #FFFFFF !important;
  font-size: 12px !important;
  font-weight: 600 !important;
  letter-spacing: 0.05em !important;
  box-shadow: none !important;
}
[data-testid="stLinkButton"] > a:hover {
  background: #333333 !important;
  border-color: #333333 !important;
}

/* ── Caption ── */
.stCaption {
  font-family: var(--font) !important;
  font-size: 11px !important;
  color: var(--c-caption) !important;
  letter-spacing: 0.05em !important;
}

/* ────────────────────────────────────────
   Custom HTML component styles
──────────────────────────────────────── */

/* Section label with 2px underline accent */
.nx-label {
  font-family: var(--font);
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.15em;
  text-transform: uppercase;
  color: #767676;
  padding-bottom: 10px;
  margin-bottom: 20px;
  border-bottom: 2px solid #1A1A1A;
  display: inline-block;
}

/* Hero */
.nx-hero {
  padding: 48px 0 40px;
  border-bottom: 1px solid #E0E0E0;
  margin-bottom: 40px;
}
.nx-hero-eyebrow {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.3em;
  text-transform: uppercase;
  color: #767676;
  margin: 0 0 16px;
}
.nx-hero-title {
  font-size: 36px;
  font-weight: 700;
  color: #1A1A1A;
  letter-spacing: -0.02em;
  line-height: 1.15;
  margin: 0 0 14px;
}
.nx-hero-sub {
  font-size: 14px;
  color: #767676;
  line-height: 1.7;
  margin: 0;
  font-weight: 400;
}

/* Example Q section header */
.nx-eq-header {
  padding-bottom: 10px;
  margin-bottom: 0;
  border-bottom: 2px solid #1A1A1A;
  display: flex;
  align-items: baseline;
  gap: 12px;
}
.nx-eq-title {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.15em;
  text-transform: uppercase;
  color: #767676;
  margin: 0;
}
.nx-eq-sub {
  font-size: 11px;
  color: #AEAEAE;
  margin: 0;
}

/* Doc reference card */
.nx-doc-card {
  border: 1px solid #E0E0E0;
  border-top: 4px solid #1A1A1A;
  padding: 16px;
  margin-bottom: 4px;
  background: #FFFFFF;
}
.nx-doc-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
}
.nx-doc-badge {
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  background: #1A1A1A;
  color: #FFFFFF;
  padding: 2px 7px;
  flex-shrink: 0;
}
.nx-doc-title {
  font-size: 13px;
  font-weight: 700;
  color: #1A1A1A;
}
.nx-doc-cite {
  font-size: 11px;
  color: #767676;
  margin-left: auto;
  flex-shrink: 0;
}
.nx-doc-text {
  font-size: 12px;
  color: #767676;
  line-height: 1.65;
  margin: 0;
}

/* Critical alert — inverted block */
.nx-critical {
  background: #1A1A1A;
  color: #FFFFFF;
  padding: 12px 18px;
  margin-bottom: 16px;
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.06em;
}
.nx-critical-label {
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.2em;
  background: #FFFFFF;
  color: #1A1A1A;
  padding: 2px 6px;
  flex-shrink: 0;
}

/* Elapsed time */
.nx-elapsed {
  font-size: 11px;
  color: #AEAEAE;
  letter-spacing: 0.05em;
  margin-top: 10px;
}

/* Sidebar brand block */
.nx-brand {
  padding: 28px 0 20px;
  border-bottom: 2px solid #1A1A1A;
  margin-bottom: 24px;
}
.nx-brand-eyebrow {
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.3em;
  text-transform: uppercase;
  color: #AEAEAE;
  margin: 0 0 6px;
}
.nx-brand-title {
  font-size: 20px;
  font-weight: 700;
  color: #1A1A1A;
  letter-spacing: -0.01em;
  margin: 0;
}

/* Sidebar section label */
.nx-sidebar-label {
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.15em;
  text-transform: uppercase;
  color: #AEAEAE;
  margin: 0 0 10px;
}

/* Sidebar disclaimer */
.nx-disclaimer {
  font-size: 11px;
  color: #AEAEAE;
  line-height: 1.65;
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
    "ethics_hotline_url":  "신세계면세점 핫라인 제보하기 URL",
    "hr_contact_text":     "인사팀 문의 안내 문구",
    "hr_chatbot_url":      "인사 챗봇 URL",
}

_KIND_BADGE_TEXT = {
    "rule":    "사규",
    "case":    "사례",
    "penalty": "징계기준",
}


def _supabase():
    """매 스크립트 실행마다 새 클라이언트 생성. 캐시·session_state 어디에도 보관하지 않음.
    httpx 연결이 다른 사용자 세션에서 닫혀 공유 객체가 망가지는 문제를 원천 차단."""
    from supabase import create_client
    s = settings()
    if not s.supabase_url or not s.supabase_key:
        return None
    return create_client(s.supabase_url, s.supabase_key)


def _admin_panel(sb, hotlines: dict) -> None:
    with st.expander("ADMIN"):
        admin_pw = get_secret("ADMIN_PASSWORD")
        if not admin_pw:
            st.info("ADMIN_PASSWORD secret을 설정하면 관리자 기능이 활성화됩니다.")
            return

        if not st.session_state.get("admin_authenticated"):
            with st.form("sidebar_admin_login"):
                pw = st.text_input("비밀번호", type="password")
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
        st.page_link("pages/admin.py", label="Admin 대시보드 열기", use_container_width=True)
        st.markdown("---")

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
            <div class="nx-brand">
              <p class="nx-brand-eyebrow">Compliance Assistant</p>
              <p class="nx-brand-title">NEXUS AI</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.markdown(
            '<p class="nx-sidebar-label">질의 범위</p>',
            unsafe_allow_html=True,
        )
        cat = st.selectbox(
            "카테고리",
            options=("전체",) + CATEGORIES,
            index=0,
            label_visibility="collapsed",
        )
        st.markdown("---")
        st.markdown(
            '<p class="nx-disclaimer">'
            '본 챗봇은 사규·윤리강령·사례집 기반 답변을 제공합니다.<br>'
            '인사 행정·신고 절차는 인사팀으로 문의하세요.'
            '</p>',
            unsafe_allow_html=True,
        )
        st.markdown("---")
        _admin_panel(sb, hotlines)
        return cat


def _hotline_button(hotlines: dict[str, str]) -> None:
    url = hotlines.get("ethics_hotline_url") or hotlines.get("internal_report_url")
    if url:
        st.link_button("신세계면세점 핫라인 제보하기", url, use_container_width=True)


def _render_contexts(contexts: list[dict]) -> None:
    if not contexts:
        return
    with st.expander("REFERENCE DOCUMENTS", expanded=False):
        for c in contexts:
            badge = _KIND_BADGE_TEXT.get(c.get("doc_kind", ""), "DOC")
            title = c.get("doc_title") or "문서"
            cite = ""
            if c.get("article_no"):
                cite = c["article_no"]
            elif c.get("case_no"):
                cite = f"#{c['case_no']}"
            cite_html = f'<span class="nx-doc-cite">{cite}</span>' if cite else ""
            text = (c.get("text") or "")[:480]
            st.markdown(
                f"""
                <div class="nx-doc-card">
                  <div class="nx-doc-header">
                    <span class="nx-doc-badge">{badge}</span>
                    <span class="nx-doc-title">{title}</span>
                    {cite_html}
                  </div>
                  <p class="nx-doc-text">{text}</p>
                </div>
                """,
                unsafe_allow_html=True,
            )


def _show_example_questions() -> str | None:
    st.markdown(
        """
        <div class="nx-eq-header">
          <p class="nx-eq-title">Sample Questions</p>
          <p class="nx-eq-sub">클릭하면 바로 질문됩니다</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown("<div style='margin-top:16px'></div>", unsafe_allow_html=True)
    cols = st.columns(2)
    for i, q in enumerate(_EXAMPLE_QUESTIONS):
        if cols[i % 2].button(q, key=f"eq_{i}", use_container_width=True):
            return q
    return None


def _render_critical_banner() -> None:
    st.markdown(
        """
        <div class="nx-critical">
          <span class="nx-critical-label">ALERT</span>
          본 사안은 심각 사안 응답 모드로 처리되었습니다
        </div>
        """,
        unsafe_allow_html=True,
    )


def _run_ask(sb, q: str, cat: str, hotlines: dict) -> None:
    import sys
    import traceback
    st.session_state["history"].append(("user", q, {}))
    with st.chat_message("user"):
        st.markdown(q)

    ans = None
    last_err: Exception | None = None
    tb_str = ""
    friendly_msg = ""
    with st.chat_message("assistant"):
        with st.spinner("문서 검색 및 답변 생성 중..."):
            for attempt in range(3):
                try:
                    if attempt > 0:
                        sb = _supabase()
                    ans = ask(sb, question=q, category=cat)
                    break
                except Exception as e:
                    last_err = e
                    tb_str = traceback.format_exc()
                    print(f"\n=== ASK ERROR (attempt {attempt}) ===\n{tb_str}", file=sys.stderr, flush=True)
                    if "client has been closed" in str(e).lower() and attempt < 2:
                        continue
                    break

        if ans is None:
            err_text = str(last_err or "")
            if "double precision" in err_text or "structure of query" in err_text:
                friendly_msg = (
                    "⚠️ 데이터베이스의 검색 함수 버전이 코드와 일치하지 않습니다.\n\n"
                    "관리자에게 다음 SQL 마이그레이션 실행을 요청해 주세요:\n"
                    "`db/02_hybrid_search.sql` 최신 버전 재실행"
                )
            elif "Could not find the function" in err_text or "PGRST202" in err_text:
                friendly_msg = (
                    "⚠️ 데이터베이스의 검색 함수가 설치되지 않았습니다.\n\n"
                    "관리자에게 `db/02_hybrid_search.sql` 실행을 요청해 주세요."
                )
            elif "no rows" in err_text.lower() or "검색 결과 없음" in err_text:
                friendly_msg = (
                    "ℹ️ 아직 사규·사례 등 문서가 업로드되지 않았습니다.\n\n"
                    "관리자가 문서를 적재한 뒤 다시 시도해 주세요."
                )
            else:
                friendly_msg = "⚠️ 일시적인 오류가 발생했습니다. 잠시 후 다시 시도해 주세요."
            st.markdown(friendly_msg)
            with st.expander("🔧 기술 세부정보 (관리자용)", expanded=False):
                st.code(tb_str or str(last_err) or "(no traceback)", language="python")
        else:
            if ans.thinking:
                with st.expander("THINKING PROCESS", expanded=False):
                    st.markdown(ans.thinking)
            if ans.is_critical:
                _render_critical_banner()
            st.markdown(ans.text)
            st.markdown(
                f'<p class="nx-elapsed">{ans.elapsed:.1f}s</p>',
                unsafe_allow_html=True,
            )
            _render_contexts(ans.contexts)
            _hotline_button(hotlines)

    if ans is None:
        st.session_state["history"].append((
            "assistant", friendly_msg,
            {"contexts": [], "critical": False, "kind": None, "thinking": "", "elapsed": 0.0},
        ))
        return

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


_SIDEBAR_TOGGLE_JS = """
<div></div>
<script>
(function () {
  let doc;
  try { doc = window.parent.document; }
  catch (e) { console.error('[nx-expand] cannot reach parent doc', e); return; }

  function makeBtn() {
    const btn = doc.createElement('button');
    btn.id = 'nx-expand-btn';
    btn.type = 'button';
    btn.setAttribute('aria-label', '사이드바 펼치기');
    btn.innerHTML = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="square"><line x1="4" y1="6" x2="20" y2="6"/><line x1="4" y1="12" x2="20" y2="12"/><line x1="4" y1="18" x2="20" y2="18"/></svg>';
    Object.assign(btn.style, {
      position: 'fixed', top: '12px', left: '12px',
      width: '40px', height: '40px',
      background: '#1A1A1A', color: '#FFFFFF',
      border: 'none', borderRadius: '0',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      cursor: 'pointer', zIndex: '2147483647', padding: '0',
      boxShadow: 'none',
    });
    btn.addEventListener('mouseenter', () => { btn.style.background = '#333333'; });
    btn.addEventListener('mouseleave', () => { btn.style.background = '#1A1A1A'; });
    btn.addEventListener('click', () => {
      const selectors = [
        '[data-testid="stSidebarCollapsedControl"] button',
        '[data-testid="collapsedControl"] button',
        '[data-testid="stSidebarCollapseButton"] button',
        'button[kind="header"]',
        'button[aria-label*="sidebar" i]',
      ];
      for (const sel of selectors) {
        const el = doc.querySelector(sel);
        if (el) { el.click(); return; }
      }
      console.warn('[nx-expand] no streamlit toggle found');
    });
    return btn;
  }

  function isSidebarVisible() {
    const sb = doc.querySelector('[data-testid="stSidebar"]');
    if (!sb) return false;
    const cs = getComputedStyle(sb);
    if (cs.display === 'none' || cs.visibility === 'hidden') return false;
    const r = sb.getBoundingClientRect();
    return r.width > 100 && r.right > 50;
  }

  function ensure() {
    let btn = doc.getElementById('nx-expand-btn');
    if (!btn) {
      btn = makeBtn();
      doc.body.appendChild(btn);
      console.log('[nx-expand] button injected');
    }
    btn.style.display = isSidebarVisible() ? 'none' : 'flex';
  }

  ensure();
  const obs = new MutationObserver(ensure);
  obs.observe(doc.body, { attributes: true, subtree: true, childList: true,
    attributeFilter: ['aria-expanded', 'style', 'class'] });
  window.addEventListener('resize', ensure);
  setInterval(ensure, 1000);
})();
</script>
"""


def main():
    st.markdown(_CSS, unsafe_allow_html=True)
    # 4px top frame line
    st.markdown('<div class="nx-topbar"></div>', unsafe_allow_html=True)
    # Custom sidebar expand button (visible only when sidebar is collapsed)
    _components_html(_SIDEBAR_TOGGLE_JS, height=0)

    sb = _supabase()
    if sb is None:
        st.error("Supabase 설정이 없습니다. SUPABASE_URL / SUPABASE_KEY 를 secrets에 추가하세요.")
        st.stop()

    if "history" not in st.session_state:
        st.session_state["history"] = []

    hotlines = load_hotlines(sb)
    cat = _sidebar(sb, hotlines)

    # Hero section
    st.markdown(
        """
        <div class="nx-hero">
          <p class="nx-hero-eyebrow">NEXUS AI · Compliance Intelligence</p>
          <h1 class="nx-hero-title">무엇을 도와드릴까요?</h1>
          <p class="nx-hero-sub">
            사규 · 윤리강령 · 사건사고 사례 · 징계규정을 통합 검색합니다.<br>
            이름 · 부서 등 식별정보는 자동 마스킹됩니다.
          </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Chat history replay
    for role, content, meta in st.session_state["history"]:
        with st.chat_message(role):
            if role == "assistant" and meta.get("thinking"):
                with st.expander("THINKING PROCESS", expanded=False):
                    st.markdown(meta["thinking"])
            if role == "assistant" and meta.get("critical"):
                _render_critical_banner()
            st.markdown(content)
            if role == "assistant" and meta.get("elapsed"):
                st.markdown(
                    f'<p class="nx-elapsed">{meta["elapsed"]:.1f}s</p>',
                    unsafe_allow_html=True,
                )
            if role == "assistant" and meta.get("contexts"):
                _render_contexts(meta["contexts"])
            if role == "assistant":
                _hotline_button(hotlines)

    # Example questions (empty state only)
    clicked_q: str | None = None
    if not st.session_state["history"]:
        clicked_q = _show_example_questions()

    q = st.chat_input("질문을 입력하세요…") or clicked_q
    if not q:
        return

    _run_ask(sb, q, cat, hotlines)


if __name__ == "__main__":
    main()
