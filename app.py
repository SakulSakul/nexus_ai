"""DF COMPASS · 임직원용 Streamlit 프론트엔드 (PoC)."""

from __future__ import annotations

import streamlit as st
import streamlit.components.v1 as components

import datetime as _dt
import time as _time

from core.chatbot import ask, ask_stream, get_avg_latency_seconds
from core.config import CATEGORIES, get_secret, load_hotlines, settings, validate_settings


st.set_page_config(
    page_title="DF COMPASS",
    page_icon="🧭",
    layout="wide",
    initial_sidebar_state="expanded",
)

# PR-CAG: cache pre-warming hook. NEXUS_CAG_ENABLED=false (default) 면 no-op.
# 활성 시 첫 user request 전에 SYSTEM_PROMPT + 전체 사규 corpus 를 server-side
# cache 로 빌드 → 매 request input token 비용 ~95% 절감.
# Streamlit rerun 마다 호출되지만 idempotent (state singleton, TTL 체크).
try:
    from core.nexus_cag_manager import ensure_warm as _cag_ensure_warm
    _cag_ensure_warm()
except Exception:
    pass

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

/* 사이드바 close X 만 숨겨 사용자가 능동적으로 사이드바를 닫지 못하게 함.
   Streamlit 일부 버전에서 사이드바를 닫으면 [data-testid="stSidebar"]
   컨테이너가 DOM 에서 제거되고 그 상태가 브라우저 localStorage 에
   저장되어 새로고침해도 복구되지 않는 시나리오를 차단. 모바일에서
   자동으로 collapsed 되는 경우는 막을 수 없으므로, 그때 reopen 용
   prominent 토글(아래 stSidebarCollapsedControl 등) 이 좌상단에 떠서
   사용자가 다시 열 수 있도록 함. 즉 *닫기 버튼만* 숨기고 *열기 버튼*
   셀렉터는 절대 여기 추가하지 말 것. */
[data-testid="stSidebarCollapseButton"] {
    display: none !important;
}

/* 사이드바 닫힘 상태에서 표시되는 reopen 토글을 prominent 하게 강화.
   Streamlit 기본 토글은 작고 회색이라 사용자가 못 찾는 경우가 많아,
   화면 좌상단 고정 + 흰 배경/검정 테두리/햄버거 아이콘으로 시인성을 높임.
   사이드바가 열려 있을 땐 Streamlit이 이 컨트롤을 렌더링하지 않으므로
   별도 hide 규칙은 불필요. selector 는 Streamlit 버전 호환을 위해
   세 가지(stSidebarCollapsedControl / collapsedControl / stExpandSidebarButton)
   를 모두 커버. */
[data-testid="stSidebarCollapsedControl"],
[data-testid="collapsedControl"],
[data-testid="stExpandSidebarButton"] {
    display: flex !important;
    visibility: visible !important;
    opacity: 1 !important;
    position: fixed !important;
    top: 12px !important;
    left: 12px !important;
    z-index: 999999 !important;
    width: 44px !important;
    height: 44px !important;
    min-width: 44px !important;
    min-height: 44px !important;
    padding: 0 !important;
    background: #ffffff !important;
    border: 1.5px solid #1A1A1A !important;
    border-radius: 6px !important;
    box-shadow: 0 2px 6px rgba(0, 0, 0, 0.08) !important;
    align-items: center !important;
    justify-content: center !important;
    cursor: pointer !important;
    transition: background-color 0.15s ease, color 0.15s ease !important;
}
[data-testid="stSidebarCollapsedControl"]:hover,
[data-testid="collapsedControl"]:hover,
[data-testid="stExpandSidebarButton"]:hover {
    background: #1A1A1A !important;
}
[data-testid="stSidebarCollapsedControl"] svg,
[data-testid="collapsedControl"] svg,
[data-testid="stExpandSidebarButton"] svg {
    width: 22px !important;
    height: 22px !important;
    color: #1A1A1A !important;
    fill: #1A1A1A !important;
}
[data-testid="stSidebarCollapsedControl"]:hover svg,
[data-testid="collapsedControl"]:hover svg,
[data-testid="stExpandSidebarButton"]:hover svg {
    color: #ffffff !important;
    fill: #ffffff !important;
}

/* 모바일: 동일 위치·크기 유지하되 터치 영역을 살짝 더 확보 */
@media (max-width: 768px) {
    [data-testid="stSidebarCollapsedControl"],
    [data-testid="collapsedControl"],
    [data-testid="stExpandSidebarButton"] {
        width: 48px !important;
        height: 48px !important;
        min-width: 48px !important;
        min-height: 48px !important;
        top: 10px !important;
        left: 10px !important;
    }
}

/* Material Symbols 폰트가 Streamlit Cloud에서 로드 실패할 경우 ligature
   이름(arrow_forward, keyboard_double_arrow_left, expand_more 등)이 raw
   텍스트로 노출됨. 모든 Material 아이콘 컨테이너를 숨겨 누수를 차단. */
[data-testid="stIconMaterial"],
[data-testid="stPageLink"] [data-testid="stIconMaterial"],
.material-symbols-outlined,
.material-symbols-rounded,
.material-icons,
[class*="material-symbols"],
[class*="material-icons"] {
    display: none !important;
}

/* 사이드바 자체 overflow 차단 (안전망) */
section[data-testid="stSidebar"] {
    overflow-x: hidden !important;
}

/* Hide Streamlit's auto-generated multipage navigation ("app" / "admin"
   links at the top of the sidebar) — users reach admin via the in-app
   ADMIN expander, not this nav. */
[data-testid="stSidebarNav"],
[data-testid="stSidebarNavItems"],
[data-testid="stSidebarNavSeparator"] {
  display: none !important;
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

/* Streamlit이 헤더(h1~h6) 옆에 자동 생성하는 anchor 링크/클립 아이콘 제거.
   st.title / st.header / st.subheader 와 st.markdown 내 # 헤더, 그리고
   raw <h1> HTML 모두에 적용. */
[data-testid="stHeaderActionElements"],
[data-testid="StyledLinkIconContainer"],
.stMarkdown h1 > a,
.stMarkdown h2 > a,
.stMarkdown h3 > a,
.stMarkdown h4 > a,
.stMarkdown h5 > a,
.stMarkdown h6 > a,
h1 > a.anchor-link,
h2 > a.anchor-link,
h3 > a.anchor-link,
h4 > a.anchor-link,
h5 > a.anchor-link,
h6 > a.anchor-link {
  display: none !important;
}

:root {
  /* warm editorial (Claude 시스템) — accent 레드·font Pretendard 만 유지, 뉴트럴은 웜 톤 */
  --c-primary:    #1F1E1D;   /* 웜 near-black (구조) */
  --c-accent:     #C8102E;   /* 신세계 시그니처 레드 — 유지 (액센트 전용) */
  --c-accent-dark:#9A0C24;   /* 호버 — 유지 */
  --c-accent-bg:  #FCEBEE;   /* 레드 계열 하이라이트 배경 — 유지 */
  --c-text:     #3D3C38;     /* 웜 그레이 본문 (황갈 언더톤) */
  --c-caption:  #87867F;     /* 웜 그레이 캡션/메타 */
  --c-muted:    #B5B3A9;     /* 웜 뉴트럴 */
  --c-border:   #E8E6DC;     /* 크림 보더 */
  --c-surface:  #FAF9F5;     /* 카드/표면 — 옅은 크림 */
  --c-bg:       #F5F4ED;     /* Parchment — 웜 크림 배경 (editorial 핵심) */
  --font: 'Pretendard', -apple-system, 'Apple SD Gothic Neo', 'Noto Sans KR', sans-serif;
}

/* ── 탭(Tabs) 활성 인디케이터 — 신세계 레드 ── */
[data-baseweb="tab-highlight"] {
  background-color: var(--c-accent) !important;
}
[data-baseweb="tab-border"] {
  background-color: var(--c-border) !important;
}

/* ── 본문 링크 hover/focus underline — 신세계 레드 ── */
.stMarkdown a:hover,
.stMarkdown a:focus,
[data-testid="stMain"] a:hover,
[data-testid="stMain"] a:focus {
  color: var(--c-accent) !important;
  text-decoration-color: var(--c-accent) !important;
}

/* ── Reset ── */
html, body, .stApp {
  font-family: var(--font) !important;
  background: var(--c-bg) !important;
  color: var(--c-text) !important;
}
#MainMenu, footer { visibility: hidden; }
[data-testid="stHeader"] { background: transparent !important; }
[data-testid="stToolbar"] { display: none !important; }
[data-testid="stDecoration"] { display: none !important; }
* { box-sizing: border-box; }

/* ── 4px top frame (신세계 시그니처 레드 액센트) ── */
.nx-topbar {
  position: fixed;
  top: 0; left: 0; right: 0;
  height: 4px;
  background: var(--c-accent);
  z-index: 9999;
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

/* Sidebar 안의 모든 버튼(stButton + stFormSubmitButton) 라벨이 회색
   상속을 받지 않도록 명시적으로 검정색 지정. Primary kind는 흰 텍스트. */
[data-testid="stSidebar"] .stButton > button p,
[data-testid="stSidebar"] .stButton > button span,
[data-testid="stSidebar"] .stFormSubmitButton > button,
[data-testid="stSidebar"] .stFormSubmitButton > button p,
[data-testid="stSidebar"] .stFormSubmitButton > button span {
  color: var(--c-primary) !important;
  font-weight: 600 !important;
}
[data-testid="stSidebar"] .stFormSubmitButton > button {
  background: var(--c-bg) !important;
  border: 1px solid var(--c-border) !important;
  border-radius: 0 !important;
  font-family: var(--font) !important;
  font-size: 12px !important;
  letter-spacing: 0.03em !important;
  box-shadow: none !important;
}
[data-testid="stSidebar"] .stFormSubmitButton > button[kind="primary"],
[data-testid="stSidebar"] .stFormSubmitButton > button[kind="primary"] p,
[data-testid="stSidebar"] .stFormSubmitButton > button[kind="primary"] span,
[data-testid="stSidebar"] .stButton > button[kind="primary"],
[data-testid="stSidebar"] .stButton > button[kind="primary"] p,
[data-testid="stSidebar"] .stButton > button[kind="primary"] span {
  background: var(--c-accent) !important;
  border-color: var(--c-accent) !important;
  color: #FFFFFF !important;
  font-weight: 700 !important;
}
[data-testid="stSidebar"] .stFormSubmitButton > button[kind="primary"]:hover,
[data-testid="stSidebar"] .stButton > button[kind="primary"]:hover {
  background: var(--c-accent-dark) !important;
  border-color: var(--c-accent-dark) !important;
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
/* ── PR-UI5: 채팅 아바타 — 기본 색박스 제거 + 뉴트럴 디스크 (testid 버전 양쪽) ── */
[data-testid="stChatMessageAvatarUser"],
[data-testid="stChatMessageAvatarAssistant"],
[data-testid="chatAvatarIcon-user"],
[data-testid="chatAvatarIcon-assistant"] {
    background-color: #f1f3f5 !important;
    border: 1px solid #e5e8eb !important;
}
[data-testid="block-container"] { padding-top: 2rem !important; }
/* ── PR-UI2: 답변 가독성 — 줄 길이(measure) 제한 ──────────────── */
/* layout=wide 라 답변이 화면 폭 전체로 흘러 한 줄이 과도하게 길다(가독성 저하).
   읽기 좋은 폭으로 제한 → 한 줄 ~40~50 한글자. stChatMessage 미사용 탭
   (대시보드/도서관/admin)은 영향 없음. */
[data-testid="stChatMessage"] { max-width: 880px; margin-left: auto; margin-right: auto; }
[data-testid="stChatMessage"] .stMarkdown { max-width: 840px; }

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

/* Primary button — 신세계 레드 액센트 */
.stButton > button[kind="primary"] {
  background: var(--c-accent) !important;
  border: 1px solid var(--c-accent) !important;
  color: #FFFFFF !important;
  font-weight: 600 !important;
  letter-spacing: 0.03em !important;
  box-shadow: none !important;
}
.stButton > button[kind="primary"]:hover {
  background: var(--c-accent-dark) !important;
  border-color: var(--c-accent-dark) !important;
  box-shadow: none !important;
  transform: none !important;
}

/* ── Chat messages (PR-UI7: warm 배경 위 가독성 — 흰 카드 부여) ── */
[data-testid="stChatMessage"] {
  border: 1px solid var(--c-border) !important;
  border-radius: 16px !important;
  padding: 1.25rem 1.5rem !important;
  margin-bottom: 0.6rem !important;
  background: #FFFFFF !important;
  box-shadow: 0 1px 3px rgba(31,30,29,0.05) !important;
}
/* user 질문 — 레드 계열 옅은 틴트로 구분 (Image 1 의 구분 버블) */
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) {
  background: var(--c-accent-bg) !important;
  border-color: #F1D5DB !important;
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
  color: var(--c-accent);
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
.nx-hero-title::after {
  content: ".";
  color: var(--c-accent);
  margin-left: 1px;
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

/* Critical alert — inverted block + 좌측 4px 레드 액센트 라인 */
.nx-critical {
  background: #1A1A1A;
  color: #FFFFFF;
  border-left: 4px solid var(--c-accent);
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

/* Material Symbols 아이콘 노드의 폰트를 ligature 변환 가능한 상태로 복구.
   전역 [data-testid="stSidebar"] span 등에 걸린 Pretendard !important 가
   stIconMaterial 의 font-family 를 덮어써서 'keyboard_double_arrow_left'
   같은 raw 텍스트가 노출되는 현상을 차단. 이 블록은 _CSS 의 마지막에
   위치해 같은 specificity 의 후행 규칙으로 우선 적용되도록 함. */
[data-testid="stIconMaterial"],
[data-testid="stIconMaterial"] *,
.material-symbols-outlined,
.material-symbols-rounded,
.material-symbols-sharp,
[class*="material-symbols"] {
    font-family: 'Material Symbols Outlined', 'Material Symbols Rounded', 'Material Symbols Sharp', 'Material Icons' !important;
    font-weight: normal !important;
    font-style: normal !important;
    font-size: 20px !important;
    line-height: 1 !important;
    letter-spacing: normal !important;
    text-transform: none !important;
    display: inline-block !important;
    white-space: nowrap !important;
    word-wrap: normal !important;
    direction: ltr !important;
    -webkit-font-feature-settings: 'liga' !important;
    -webkit-font-smoothing: antialiased !important;
    font-variation-settings: 'FILL' 0, 'wght' 400, 'GRAD' 0, 'opsz' 24 !important;
}

/* `html body ...` 셀렉터로 specificity 를 0,3,1 수준까지 끌어올려
   기존 `[data-testid="stSidebar"] span { font-family: Pretendard !important }`
   (0,2,1) 등 컨테이너 단위 폰트 강제를 명확히 이기도록 보강.
   이로써 사이드바 / chat input / 사이드바 토글 위치의 stIconMaterial
   노드가 Material Symbols 폰트를 실제로 적용받아 ligature 가 글리프로
   변환되고, 브라우저의 lazy 폰트 로드 트리거가 정상 발동됨. */
html body [data-testid="stIconMaterial"],
html body [data-testid="stSidebar"] [data-testid="stIconMaterial"],
html body [data-testid="stChatInput"] [data-testid="stIconMaterial"],
html body [data-testid="stSidebarCollapseButton"] [data-testid="stIconMaterial"],
html body [data-testid="stSidebarCollapsedControl"] [data-testid="stIconMaterial"] {
    font-family: 'Material Symbols Outlined', 'Material Symbols Rounded' !important;
    font-weight: normal !important;
    font-style: normal !important;
    line-height: 1 !important;
    letter-spacing: normal !important;
    text-transform: none !important;
    white-space: nowrap !important;
    word-wrap: normal !important;
    direction: ltr !important;
    -webkit-font-feature-settings: 'liga' !important;
    -webkit-font-smoothing: antialiased !important;
    font-variation-settings: 'FILL' 0, 'wght' 400, 'GRAD' 0, 'opsz' 24 !important;
}

/* caption 색 대비 보강 — WCAG 친화 */
div[data-testid="stCaptionContainer"] p,
.stCaption,
small {
    color: #555 !important;
}

/* PR-Fun1.8: 로딩 단계 emoji animation. spin / pulse 두 가지. */
@keyframes nx-spin {
    from { transform: rotate(0deg); }
    to   { transform: rotate(360deg); }
}
@keyframes nx-pulse {
    0%, 100% { opacity: 1;   transform: scale(1);    }
    50%      { opacity: 0.55; transform: scale(1.18); }
}
.nx-spin {
    animation: nx-spin 2s linear infinite;
    display: inline-block;
}
.nx-pulse {
    animation: nx-pulse 1.4s ease-in-out infinite;
    display: inline-block;
}
/* PR-Fun1.9: 답변 작성 단계 emoji cycling — 0.5초 간격 4개 순환.
   inline JS <script> 는 streamlit unsafe_allow_html sanitizer 가 차단하므로
   CSS-only ::before content 변경으로 동일 효과. modern 브라우저 (Chrome/
   Edge/Safari/FF 최근 버전) 지원. */
@keyframes nx-cycle {
    0%, 24%   { content: "🧠"; }
    25%, 49%  { content: "💭"; }
    50%, 74%  { content: "✍️"; }
    75%, 100% { content: "📝"; }
}
.nx-cycle {
    display: inline-block;
}
.nx-cycle::before {
    content: "🧠";
    animation: nx-cycle 2s linear infinite;
    display: inline-block;
}
/* ── PR-UI1: 답변 본문 서체 정규화 (답변 유형 간 일관성) ───────── */
[data-testid="stChatMessage"] .stMarkdown p,
[data-testid="stChatMessage"] .stMarkdown li {
    font-size: 0.95rem;
    line-height: 1.72;
}
[data-testid="stChatMessage"] .stMarkdown h1,
[data-testid="stChatMessage"] .stMarkdown h2,
[data-testid="stChatMessage"] .stMarkdown h3,
[data-testid="stChatMessage"] .stMarkdown h4,
[data-testid="stChatMessage"] .stMarkdown h5 {
    font-size: 1.03rem;
    font-weight: 700;
    line-height: 1.45;
    margin: 0.95em 0 0.35em;
}
[data-testid="stChatMessage"] .stMarkdown ul,
[data-testid="stChatMessage"] .stMarkdown ol {
    margin: 0.3em 0 0.65em;
    padding-left: 1.25em;
}
[data-testid="stChatMessage"] .stMarkdown strong { font-weight: 700; }

/* ── PR-UI2 (Stage 1): Empty-home hero 리디자인 — editorial + 나침반 마크 + 트러스트 스트립 ── */
.nx-hero2 { padding: 40px 0 24px; border-bottom: 1px solid var(--c-border); margin-bottom: 32px; }
.nx-hero2-mark { display: flex; align-items: center; gap: 9px; margin-bottom: 16px; }
.nx-compass { display: inline-block; width: 24px; height: 24px; flex: 0 0 24px; background: no-repeat center / contain; background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'%3E%3Ccircle cx='12' cy='12' r='10.3' fill='none' stroke='%231F1E1D' stroke-width='1.5'/%3E%3Cpolygon points='12,3.8 9.6,12 14.4,12' fill='%23C8102E'/%3E%3Cpolygon points='12,20.2 9.6,12 14.4,12' fill='%23B5B3A9'/%3E%3Ccircle cx='12' cy='12' r='1.4' fill='%231F1E1D'/%3E%3C/svg%3E"); }
.nx-hero2-eyebrow { font-size: 11px; font-weight: 700; letter-spacing: 0.26em; text-transform: uppercase; color: var(--c-accent); }
.nx-hero2-title { font-size: 32px; font-weight: 700; color: var(--c-primary); letter-spacing: -0.02em; line-height: 1.16; margin: 0 0 13px; }
.nx-hero2-q { color: var(--c-accent); }
.nx-hero2-sub { font-size: 14.5px; color: #4A483F; line-height: 1.7; margin: 0 0 7px; max-width: 640px; }
.nx-hero2-sub strong { color: var(--c-primary); font-weight: 700; }
.nx-hero2-scope { font-size: 12.5px; color: var(--c-caption); line-height: 1.6; margin: 0; }
.nx-trust { display: flex; flex-wrap: wrap; gap: 6px 18px; margin-top: 18px; font-size: 12px; color: #5F5E5A; }
.nx-trust > span { display: inline-flex; align-items: center; }
.nx-trust .nx-dot { display: inline-block; width: 7px; height: 7px; border-radius: 50%; margin-right: 6px; }
.nx-dot-g { background: #1f7a3a; }
.nx-dot-a { background: #C58A14; }
.nx-dot-r { background: #A93226; }

/* ── PR-UI3 (Stage 1-full): 상단 바 + 그룹 칩 + 중앙 입력 — 빈 홈 목업 정렬 ── */
.nx-topbar2 { display: flex; align-items: center; justify-content: space-between; padding: 6px 0 14px; border-bottom: 1px solid var(--c-border); margin-bottom: 4px; }
.nx-topbar2-brand { display: flex; align-items: center; gap: 9px; }
.nx-topbar2-name { font-size: 16px; font-weight: 700; color: var(--c-primary); letter-spacing: -0.01em; }
.nx-topbar2-tag { font-size: 12.5px; color: #A8654E; }
.nx-topbar2-beta { font-size: 11px; color: var(--c-caption); border: 1px solid var(--c-border); border-radius: 14px; padding: 4px 11px; }
.nx-hero2 { padding: 24px 0 0; border-bottom: none; margin-bottom: 18px; }
.nx-chips-top { height: 14px; border-top: 1px solid var(--c-border); margin-top: 22px; }
.nx-grp { font-size: 10.5px; font-weight: 700; letter-spacing: 0.13em; text-transform: uppercase; color: #A8654E; margin: 16px 0 8px; }
.nx-grp-urgent { color: #A93226; }
[data-testid="stTextInput"] input { border-radius: 10px !important; }
</style>
"""

_EXAMPLE_QUESTIONS = [
    "법인카드를 개인 용도로 사용해도 되나요?",
    "거래처에서 선물을 받아도 되나요?",
    "직장 내에서 괴롭힘을 당했어요. 어떻게 신고하나요?",
    "신세계그룹의 핵심 가치 CREDO는 무엇인가요?",
    "고객이 매장에 두고 간 물건은 어떻게 처리하나요?",
    "협력회사에 부당하게 비용을 요구하면 어떤 처벌을 받나요?",
    "매장 안전관리 책임자와 절차는 어떻게 되나요?",
    "회사의 녹색 구매 기준은 어떻게 되나요?",
]

_KIND_BADGE_TEXT = {
    "rule":    "사규",
    "case":    "사례",
    "penalty": "징계기준",
}


def _log_supabase_keys_debug(s) -> None:
    """PR-Beta-Hotfix-4: env + Settings + chosen key 진단 stderr dump.

    Streamlit Cloud Logs 에서 prefix `[NX_DEBUG]` grep 으로 즉시 추출.
    출력 항목:
      · 후보 env var 6종 (SUPABASE_KEY/_ANON_KEY/_SERVICE_ROLE_KEY +
        NEXUS_ prefix 변종) 의 존재 여부 + len + prefix/suffix 8/4 chars.
      · Settings.supabase_url / supabase_key / supabase_service_role_key
        bool 값.
      · _supabase() 가 실제 사용할 chosen key 의 prefix/suffix +
        match_service_role / match_anon 비교.
      · JWT payload 의 'role' claim — Supabase JWT 는 payload 에 role
        ('anon' | 'service_role' | 'authenticated') 명시 → 진짜 role 즉시
        확인. base64 decode 만 — 서명 검증 X (디버깅용).

    보안: full key 절대 출력 X — prefix 8 + suffix 4 만 (12 chars / 200+).
    """
    import sys
    import os as _os

    print("[NX_DEBUG] env keys present:", flush=True, file=sys.stderr)
    for env_name in (
        "SUPABASE_KEY", "SUPABASE_ANON_KEY", "SUPABASE_SERVICE_ROLE_KEY",
        "NEXUS_SUPABASE_KEY", "NEXUS_SUPABASE_ANON_KEY",
        "NEXUS_SUPABASE_SERVICE_ROLE_KEY",
    ):
        val = _os.environ.get(env_name)
        if val:
            print(
                f"  - {env_name}: ✓ len={len(val)} "
                f"prefix={val[:8]}... suffix=...{val[-4:]}",
                flush=True, file=sys.stderr,
            )
        else:
            print(f"  - {env_name}: ✗ missing", flush=True, file=sys.stderr)

    print("[NX_DEBUG] Settings:", flush=True, file=sys.stderr)
    print(f"  - supabase_url set: {bool(s.supabase_url)}",
          flush=True, file=sys.stderr)
    print(f"  - supabase_key (anon) set: {bool(s.supabase_key)}",
          flush=True, file=sys.stderr)
    print(f"  - supabase_service_role_key set: {bool(s.supabase_service_role_key)}",
          flush=True, file=sys.stderr)

    chosen = s.supabase_service_role_key or s.supabase_key
    if not chosen:
        print("[NX_DEBUG] _supabase() chosen key: (none — both None)",
              flush=True, file=sys.stderr)
        return

    is_service = chosen == s.supabase_service_role_key
    is_anon = chosen == s.supabase_key
    jwt_role = "?"
    try:
        import base64 as _b64, json as _json
        parts = chosen.split(".")
        if len(parts) >= 2:
            pad = parts[1] + "=" * (-len(parts[1]) % 4)
            payload = _json.loads(_b64.urlsafe_b64decode(pad).decode("utf-8"))
            jwt_role = payload.get("role", "?")
    except Exception as e:
        jwt_role = f"decode_err:{type(e).__name__}"

    print(
        f"[NX_DEBUG] _supabase() chosen key: "
        f"prefix={chosen[:8]}... suffix=...{chosen[-4:]} len={len(chosen)} "
        f"match_service_role={is_service} match_anon={is_anon} "
        f"jwt_role={jwt_role}",
        flush=True, file=sys.stderr,
    )


def _supabase():
    """챗봇 응답 경로용 Supabase client.

    매 스크립트 실행마다 새 클라이언트 생성. 캐시·session_state 어디에도
    보관하지 않음. httpx 연결이 다른 사용자 세션에서 닫혀 공유 객체가
    망가지는 문제를 원천 차단.

    PR-Beta-Hotfix-3 임시 우회:
      db/13~16 적용 + RLS DISABLE + table-level GRANT 시도 후에도 anon
      INSERT 가 'permission denied for table query_logs' (42501) 로 실패.
      Supabase 내부 layer issue 가 의심되며 베타 모집 차단 상태. 임시로
      service_role 키 사용 — RLS/GRANT bypass 로 즉시 작동. anon root
      cause 분석 + 정상 RLS 복귀는 별도 track.

      Service role 키가 설정돼 있으면 그것을 사용, 없으면 anon 키 fallback
      (기존 동작 호환). 베타 환경 가드: SUPABASE_SERVICE_ROLE_KEY 미설정
      시에도 dev 가 깨지지 않도록 graceful fallback.

    PR-Beta-Hotfix-4: 첫 호출 시점에 env + Settings + chosen key 진단을
    stderr 로 1회 dump. session_state guard 로 같은 session 내 spam 차단.
    """
    from supabase import create_client
    s = settings()
    if not st.session_state.get("_nx_supabase_debug_logged"):
        st.session_state["_nx_supabase_debug_logged"] = True
        try:
            _log_supabase_keys_debug(s)
        except Exception as _e:
            import sys as _sys
            print(f"[NX_DEBUG] log_supabase_keys_debug failed: {_e}",
                  flush=True, file=_sys.stderr)
    if not s.supabase_url:
        return None
    key = s.supabase_service_role_key or s.supabase_key
    if not key:
        return None
    return create_client(s.supabase_url, key)


def _validate_db_schema(sb) -> bool:
    """Critical .select() 컬럼이 실제 DB schema 와 일치하는지 startup 시 검증.

    PR-Coding-Policy-Defense: chunk_incident_nodes(부재 컬럼)를 select 해
    force-include 가 전체 silent fail 한 사고(17+시간, 9 PR 무력화) 재발 방지.
    한 번이라도 컬럼이 어긋나면 stderr + UI 에 즉시 가시화한다.
    """
    import sys as _sys
    checks = [
        ("nexus_chunks",
         "id, document_id, chunk_idx, article_no, text, categories"),
        ("nexus_documents",
         "id, title, doc_kind, meta, owning_department"),
    ]
    failures: list[str] = []
    for table, cols in checks:
        try:
            sb.table(table).select(cols).limit(1).execute()
        except Exception as e:
            msg = f"{table}: {str(e)[:300]}"
            failures.append(msg)
            print(f"[STARTUP_SCHEMA_CHECK] FAIL {msg}",
                  file=_sys.stderr, flush=True)
    if failures:
        print(f"[STARTUP_SCHEMA_CHECK] ⚠️ {len(failures)} mismatch(es)",
              file=_sys.stderr, flush=True)
        try:
            st.error(
                "⚠️ DB schema 불일치 (운영자 확인 필요):\n"
                + "\n".join(f"- {f}" for f in failures)
            )
        except Exception:
            pass
        return False
    print("[STARTUP_SCHEMA_CHECK] ✅ All checks OK",
          file=_sys.stderr, flush=True)
    return True


def _supabase_admin():
    """service_role 키 기반 클라이언트.

    ⚠️ RLS 를 우회하므로 반드시 비밀번호 게이트(`admin_authenticated`)
    뒤에서만 호출할 것. 일반 사용자 응답 경로에서는 절대 사용 금지.
    SUPABASE_SERVICE_ROLE_KEY secret 미설정 시 None 반환."""
    from supabase import create_client
    s = settings()
    if not s.supabase_url or not s.supabase_service_role_key:
        return None
    return create_client(s.supabase_url, s.supabase_service_role_key)


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
        if st.button("▶  Admin 대시보드 열기", use_container_width=True, key="admin_dashboard_link"):
            st.switch_page("pages/admin.py")

        # PR-Revert-Day2-Inline-Hotline-Panel: 인라인 panel 제거.
        # 핫라인 관리는 pages/admin.py 의 정식 panel 사용
        # (📞 핫라인 / 안내 문구 관리 — 더 풍부한 UI + 사용자 정의 키 추가 지원).


def _sidebar(sb, hotlines: dict) -> str:
    with st.sidebar:
        st.markdown(
            """
            <div class="nx-brand">
              <p class="nx-brand-eyebrow">윤리·컴플라이언스 AI 챗봇</p>
              <p class="nx-brand-title">🧭 DF COMPASS</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        with st.expander("ℹ️ DF COMPASS 안내", expanded=False):
            st.markdown("""
**DF COMPASS** — 디에프 컴파스

신세계디에프 사규·윤리강령·과거 사례를 학습한 AI 챗봇입니다. 일하다 마주치는 윤리·컴플라이언스 질문에 사규 근거와 함께 답해 드립니다.

"COMPASS(나침반)"라는 이름처럼, 임직원이 바른 방향을 잡을 수 있도록 곁에서 길을 안내하는 도구를 지향합니다. 신세계디에프의 정도경영을 일상에서 실천할 수 있도록 돕는 것이 본 챗봇의 소임입니다.

본 답변은 사규 해석 보조 도구이며 법적 효력은 없습니다. 인사 행정 사항은 인사교육팀에 직접 문의하세요.
            """)
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
            '본 답변은 사규 해석 보조 도구이며 법적 효력은 없습니다.<br>'
            '신고·조사 사항은 CSR팀 또는 신세계면세점 핫라인으로,<br>'
            '인사 규정·복리후생 등 인사 행정 사항은 인사교육팀으로 문의해 주시기 바랍니다.'
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


def _render_confidence_chip(confidence: str, contexts: list[dict] | None = None, answer_text: str | None = None) -> None:
    """PR-C1: 답변 본문 직후에 검색 신뢰도 chip 을 caption 톤으로 노출.

    confidence: 'high' | 'medium' | 'low'. 그 외 값은 표시 생략.
    contexts: 카테고리별 담당부서 매핑용. 미전달 시 일반 문구로 폴백.
    answer_text: PR-Fix-Confidence-Chip-Dept-Consistency — 답변 본문 인용
        prefix 기반 카테고리 결정 (PR #149 logic). 카테고리 chip 과 dept
        일치 보장.
    본문(ans.text) 의 [참조: ...] / 종결 멘트(💬...) 과 시각적으로 분리되되
    눈에 띄는 회색 caption + 색상 점.
    """
    # 카테고리 → 담당부서. contexts 가 없거나 카테고리 식별 불가면 fallback 문구.
    # PR-Fix-Confidence-Chip-Dept-Consistency: answer_text 전달로 PR #149 의
    # 답변 본문 인용 기반 카테고리 logic 사용 → 카테고리 chip 과 dept 일치.
    from core.nexus_category_owner import nexus_get_owner_dept
    cat_label = ""
    if contexts:
        try:
            from core.personality import category_visual
            _icon, _color, cat_label = category_visual(contexts, answer_text=answer_text)
        except Exception:
            cat_label = ""
    # PR-Universal-Routing-Cleanup: top doc 의 owning_department (사규 본문) 우선
    _top_owning_dept = None
    if contexts:
        for _c in contexts:
            _od = _c.get("owning_department")
            if _od and str(_od).strip():
                _top_owning_dept = str(_od).strip()
                break
    dept = nexus_get_owner_dept(cat_label, doc_owning_dept=_top_owning_dept)
    chip_map = {
        "high":   ("🟢", "높은 신뢰도", "#1f7a3a"),
        "medium": ("🟡", f"보조 참고 — 정확한 사항은 {dept} 확인", "#a07020"),
        "low":    ("🔴", f"검색 hit 부족 — {dept} 확인 권장", "#a93226"),
    }
    if confidence not in chip_map:
        return
    icon, label, color = chip_map[confidence]
    st.markdown(
        f"<div style='font-size:12px;color:{color};padding:4px 0 2px;"
        f"font-family:-apple-system,Pretendard,sans-serif;'>"
        f"{icon} <span style='color:{color};'>{label}</span></div>",
        unsafe_allow_html=True,
    )


def _render_answer_meta(
    elapsed: float | None, model: str = "", container=None,
) -> None:
    """답변 메타 가시성 (PR-Answer-Meta-Visibility + PR-Phase-18.7).

    응답 시간 + 모델명 표시. streaming 완료 + history replay 모두 일관 호출.
    미래 메트릭 (cache hit, token count) 추가 시 본 함수에 확장.

    PR-Phase-18.7 변경:
    - H1: elapsed=0 도 "⏱️ —" 로 표시 (#274 이전 OLD row 의 0 박힘 가시화).
    - H2: container 인자 → streaming 완료 시 timer_placeholder 를 그대로
      덮어써 시각 점프 / flicker 해소 (라이브 카운터 → 정적 meta 같은 자리).
    - Fix-3: 시인성 강화 (#555 13px + border-top — 답변 본문과 분리).
    """
    parts: list[str] = []
    if elapsed is not None:
        if elapsed >= 0.1:
            parts.append(f"⏱️ {elapsed:.1f}초")
        elif elapsed > 0:
            parts.append("⏱️ <0.1초")
        else:
            parts.append("⏱️ —")
    if model:
        parts.append(f"🤖 {model}")
    if not parts:
        return
    line = " · ".join(parts)
    html = (
        f"<div style='color:#555;font-size:13px;"
        f"padding:8px 0 6px;border-top:1px solid #eee;margin-top:6px;"
        f"font-family:-apple-system,Pretendard,sans-serif;'>"
        f"{line}</div>"
    )
    target = container if container is not None else st
    target.markdown(html, unsafe_allow_html=True)


def _render_category_chip(
    contexts: list[dict],
    answer_text: str | None = None,
) -> None:
    """PR-Fun1 작업 4: 답변 본문 직전에 카테고리 chip 한 줄 노출.

    PR-Fix-Category-Citation-Based: answer_text 전달 시 답변 본문 「📎 ((xxx)
    doc_title)」 인용 prefix 빈도 기반 카테고리 결정 (sloppy retrieval 영향
    차단). 미전달 시 contexts.categories 빈도 fallback (backwards-compat).

    contexts/answer 둘 다 카테고리 식별 불가면 표시 생략. 본문 헤더
    (📋 사규 기준 / ⚖️ 징계 기준 / 📂 사건사례) 는 LLM 출력 그대로 두고
    본 chip 만 카테고리별 색·아이콘으로 동적 변경 (가독성 유지).
    """
    if not contexts and not answer_text:
        return
    from core.personality import category_visual
    icon, color, label = category_visual(contexts, answer_text)
    if not label:
        return
    st.markdown(
        f"<div style='font-size:12px;color:{color};padding:2px 0 4px;"
        f"font-family:-apple-system,Pretendard,sans-serif;'>"
        f"{icon} <strong style='color:{color};'>{label}</strong> 카테고리"
        f"</div>",
        unsafe_allow_html=True,
    )


def _domain_from_contexts(contexts: list[dict] | None) -> str | None:
    """grounded 후속질문의 출처 도메인 — 첫 (도메인) prefix 보유 청크에서 추출.
    클릭 시 그 도메인으로 검색을 강제(category 바인딩)해 답변 보장."""
    if not contexts:
        return None
    import re as _re
    for _c in contexts:
        _m = _re.match(r"^\s*\(([^)]+)\)", _c.get("doc_title") or "")
        if _m:
            return _m.group(1).strip()
    return None


def _render_suggestion_cards(
    suggestions: list[str], *, is_critical: bool, msg_idx: int,
    ans_id: int | None = None,
    masked_question: str | None = None,
    source_category: str | None = None,
) -> None:
    """PR-Fun1 작업 3: 답변 끝의 후속 질문 카드 3개.

    critical 답변에서는 카드 자체를 비활성 (핵심 회귀 방어). LLM prompt
    에서도 [Critical Mode 답변 가이드] 7번에 의해 [SUGGESTIONS] 블록이
    생성되지 않으나, 이중 방어로 UI 단도 차단.

    클릭 시 session_state['clicked_q'] 적재 + st.rerun() → main 의
    입구 early exit 가 처리 (PR-Fun1.5 패턴, SAMPLE_QUESTIONS 와 통일).

    button key 안정화 (PR-Fun1.4 작업 7 + PR-Fun1.6):
      1순위: ans_id (query_log_id)
      2순위: masked_question 의 md5 hash 8자
             — RLS RETURNING 차단으로 query_log_id None 이어도
               live·replay·rerun 에서 동일 key 보장
      3순위: msg_idx (live=len(history), replay=idx)
    """
    if is_critical or not suggestions:
        return
    st.markdown(
        "<div style='font-size:12px;color:#475569;padding:8px 0 4px;"
        "font-family:-apple-system,Pretendard,sans-serif;'>"
        "💡 <strong>이런 질문도 해볼 수 있어요</strong></div>",
        unsafe_allow_html=True,
    )
    if ans_id is not None:
        key_id = str(ans_id)
    elif masked_question:
        import hashlib as _hashlib
        key_id = _hashlib.md5(masked_question.encode("utf-8")).hexdigest()[:8]
    else:
        key_id = str(msg_idx)
    cols = st.columns(min(3, len(suggestions)))
    for i, q in enumerate(suggestions[:3]):
        if cols[i].button(
            q, key=f"sugg_{key_id}_{i}", use_container_width=True,
        ):
            # PR-Fun1.5: clicked_q 매개체로 분리 (SAMPLE_QUESTIONS 와 통일).
            # main() 입구 early exit 가 처리 — query carry-over issue 회피.
            # PR-UI8: 출처 도메인 바인딩 — 클릭 시 그 도메인으로 검색 강제(답변 보장).
            st.session_state["clicked_q"] = q
            st.session_state["clicked_cat"] = source_category
            st.rerun()


def _render_clarify_choices(
    choices: list[dict], *, msg_idx: int,
    masked_question: str | None = None,
) -> None:
    """PR-Ambiguity-Askback: 의도 명확화 역질문 선택지 버튼.

    클릭 시 session_state['clicked_q'] = 선택지의 sub-intent query 적재 +
    st.rerun() → main 입구 early exit 가 정상 RAG 로 재질의 (suggestion cards
    와 동일 매개체). 라벨(label)과 재질의 query 분리 — 라벨은 친화 텍스트,
    query 는 정상 라우팅되는 구체 문구.

    button key 안정화: masked_question md5 8자(없으면 msg_idx) + msg_idx + i
    → live(msg_idx=len(history)) 와 replay(msg_idx=idx) 동일 key.
    """
    if not choices:
        return
    st.markdown(
        "<div style='font-size:12px;color:#475569;padding:8px 0 4px;"
        "font-family:-apple-system,Pretendard,sans-serif;'>"
        "💡 <strong>어느 쪽인지 선택해 주세요</strong></div>",
        unsafe_allow_html=True,
    )
    if masked_question:
        import hashlib as _hashlib
        key_id = _hashlib.md5(masked_question.encode("utf-8")).hexdigest()[:8]
    else:
        key_id = str(msg_idx)
    _items = [c for c in (choices or []) if (c.get("label") or c.get("query"))][:4]
    if not _items:
        return
    cols = st.columns(len(_items))
    for i, ch in enumerate(_items):
        label = (ch.get("label") or ch.get("query") or "").strip()
        query = (ch.get("query") or ch.get("label") or "").strip()
        if cols[i].button(
            label, key=f"clarify_{key_id}_{msg_idx}_{i}", use_container_width=True,
        ):
            st.session_state["clicked_q"] = query
            # PR-Hard-Scope: 명시 선택을 hard 제약으로 — 별도 키(clicked_hard_cat)로
            # 전달해 retriever 가 force-include·incident 위에서 {공통,cat} 강제.
            # clicked_cat(soft)과 분리 → suggestion 클릭 동작 무영향.
            st.session_state["clicked_hard_cat"] = ch.get("cat")
            st.rerun()


def _render_closing_remark(is_critical: bool, *, msg_idx: int | None = None) -> None:
    """PR-Fun1 작업 5: 답변 후 random 격려 멘트 1줄.

    msg_idx 가 있으면 session_state 에 pin 해서 같은 답변 replay 시 멘트
    유지 (rerun 마다 random pick 으로 chip 멘트가 바뀌면 산만). 신규 답변
    렌더 시 (msg_idx=None 또는 키 부재) 만 새로 뽑음.
    """
    from core.personality import closing_remark
    key = f"closing_{msg_idx}" if msg_idx is not None else None
    if key and key in st.session_state:
        text = st.session_state[key]
    else:
        text = closing_remark(is_critical=is_critical)
        if key:
            st.session_state[key] = text
    color = "#a93226" if is_critical else "#475569"
    st.markdown(
        f"<div style='font-size:12px;color:{color};padding:6px 0 8px;"
        f"font-style:italic;font-family:-apple-system,Pretendard,sans-serif;'>"
        f"{text}</div>",
        unsafe_allow_html=True,
    )


def _render_contexts(contexts: list[dict]) -> None:
    if not contexts:
        return
    import html as _html
    with st.expander("참고 사규", expanded=False):
        for c in contexts:
            # 모든 DB 출처 값은 escape — 악성 DOCX 본문(<script>) 가 admin
            # 업로드 경로로 들어와 사용자에게 stored XSS 로 실행되는 경로 차단.
            badge = _html.escape(_KIND_BADGE_TEXT.get(c.get("doc_kind", ""), "DOC"))
            title = _html.escape(c.get("doc_title") or "문서")
            cite_raw = ""
            if c.get("article_no"):
                cite_raw = c["article_no"]
            elif c.get("case_no"):
                cite_raw = f"#{c['case_no']}"
            cite = _html.escape(cite_raw)
            cite_html = f'<span class="nx-doc-cite">{cite}</span>' if cite else ""
            text = _html.escape((c.get("text") or "")[:480])
            st.html(
                f"""
                <div class="nx-doc-card">
                  <div class="nx-doc-header">
                    <span class="nx-doc-badge">{badge}</span>
                    <span class="nx-doc-title">{title}</span>
                    {cite_html}
                  </div>
                  <p class="nx-doc-text">{text}</p>
                </div>
                """
            )


def _show_example_questions() -> str | None:
    """SAMPLE_QUESTIONS 8개 chip — empty state 에 노출 (PR-Fun1.4 부활).

    PR-Fun1.4: click 패턴을 PR-Fun1 의 pending_q + rerun 으로 통일.
    return 값은 None 항상 — 호출 측은 무시. main() 의 clicked_q =
    pop("pending_q") 흐름이 처리.
    """
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
            # PR-Fun1.5: clicked_q 매개체로 분리. main() 입구 early exit
            # 가 처리 — query carry-over issue 회피.
            st.session_state["clicked_q"] = q
            st.rerun()
    return None


# ── PR-Fun1: empty-state 동적 인사 + Daily Tip + 빠른 액션 카드 ──
@st.cache_data(ttl=3600, show_spinner=False)
def _cached_dynamic_greeting(_hour_bucket: int, _weekday: int) -> str:
    """1시간 1회 LLM 호출로 인사 생성. 실패 시 fallback hardcoded pool.

    cache key 는 시간대(시) + 요일 — 같은 cache window 안에선 동일 인사
    유지. 호출 시 settings().gemini_api_key 검증 + 60초 timeout. LLM
    응답 80자 cap (UI 가독성).
    """
    from core.personality import (
        build_greeting_user_prompt,
        fallback_greeting,
        GREETING_SYSTEM_PROMPT,
    )
    from core.config import settings as _settings
    s = _settings()
    if not s.gemini_api_key:
        return fallback_greeting()
    try:
        from google import genai
        from google.genai import types
        cli = genai.Client(api_key=s.gemini_api_key)
        cfg = types.GenerateContentConfig(
            system_instruction=GREETING_SYSTEM_PROMPT,
            temperature=0.7,  # 변주 위해 약간 ↑
            top_p=0.95,
        )
        from concurrent.futures import ThreadPoolExecutor, TimeoutError as _Timeout
        ex = ThreadPoolExecutor(max_workers=1)
        try:
            fut = ex.submit(
                lambda: cli.models.generate_content(
                    model=s.chat_model,
                    contents=build_greeting_user_prompt(),
                    config=cfg,
                ),
            )
            res = fut.result(timeout=15)
        except _Timeout:
            return fallback_greeting()
        finally:
            ex.shutdown(wait=False, cancel_futures=True)
        text = (getattr(res, "text", "") or "").strip()
        # 따옴표·whitespace 정리
        text = text.strip("\"'“”‘’\n\r\t ")
        if not text or len(text) > 200:
            return fallback_greeting()
        return text
    except Exception:
        return fallback_greeting()


@st.cache_data(ttl=86400, show_spinner=False)
def _cached_daily_tip(_date_iso: str, doc_title: str) -> str:
    """1일 1회 LLM 호출로 사규 한 줄 fun fact 생성. 실패 시 빈 문자열.

    빈 문자열이면 호출자가 Tip 섹션 자체를 숨김. cache key 는 날짜 +
    doc_title — 같은 날 doc_title 이 같으면 동일 결과.
    """
    from core.personality import build_tip_user_prompt, TIP_SYSTEM_PROMPT
    from core.config import settings as _settings
    s = _settings()
    if not s.gemini_api_key:
        return ""
    try:
        from google import genai
        from google.genai import types
        cli = genai.Client(api_key=s.gemini_api_key)
        cfg = types.GenerateContentConfig(
            system_instruction=TIP_SYSTEM_PROMPT,
            temperature=0.6,
            top_p=0.95,
        )
        from concurrent.futures import ThreadPoolExecutor, TimeoutError as _Timeout
        ex = ThreadPoolExecutor(max_workers=1)
        try:
            fut = ex.submit(
                lambda: cli.models.generate_content(
                    model=s.chat_model,
                    contents=build_tip_user_prompt(doc_title),
                    config=cfg,
                ),
            )
            res = fut.result(timeout=15)
        except _Timeout:
            return ""
        finally:
            ex.shutdown(wait=False, cancel_futures=True)
        text = (getattr(res, "text", "") or "").strip()
        text = text.strip("\"'“”‘’\n\r\t ")
        if not text or len(text) > 200:
            return ""
        return text
    except Exception:
        return ""


def _slim_structured(sa) -> dict | None:
    """StructuredAnswer → 카드 렌더용 슬림 dict (raw_json 제외 → session_state 경량). 없으면 None."""
    if sa is None:
        return None
    try:
        d = sa.to_dict() if hasattr(sa, "to_dict") else dict(sa)
    except Exception:
        return None
    secs = []
    for s in (d.get("sections") or []):
        claims = []
        for c in (s.get("claims") or []):
            claims.append({
                "text": c.get("text", ""),
                "verbatim_quote": c.get("verbatim_quote", ""),
                "doc_title": c.get("doc_title", ""),
                "clause": c.get("clause", ""),
            })
        secs.append({"title": s.get("title", ""), "claims": claims})
    if not secs:
        return None
    return {
        "sections": secs,
        "unsupported_topics": d.get("unsupported_topics") or [],
        "data_gaps": d.get("data_gaps") or [],
    }


def _build_structured_card_html(d) -> str:
    """슬림 structured dict → 목업형 답변 카드 HTML. 없으면 빈 문자열(→ 호출측 markdown fallback).

    데이터에 verdict(금지/허용) 필드가 없으므로 거짓 pill 미생성 — 중립 헤더.
    CSS 는 자체 <style> 동봉(정적 _CSS 무수정).
    """
    if not d or not isinstance(d, dict):
        return ""
    import html as _h
    secs = d.get("sections") or []
    if not secs:
        return ""
    css = (
        "<style>"
        ".nx-vc{font-family:var(--font);}"
        ".nx-vc-head{display:flex;align-items:center;gap:9px;padding-bottom:12px;margin-bottom:4px;border-bottom:1px solid var(--c-border);}"
        ".nx-vc-head .nx-compass{width:22px;height:22px;flex:0 0 22px;}"
        ".nx-vc-head b{font-size:14px;font-weight:700;color:var(--c-primary);}"
        ".nx-vc-sec{margin-top:16px;}"
        ".nx-vc-sectitle{font-size:10.5px;font-weight:700;letter-spacing:.12em;text-transform:uppercase;color:#A8654E;margin-bottom:8px;}"
        ".nx-vc-claim{font-size:14px;line-height:1.7;color:var(--c-text);margin:0 0 8px;}"
        ".nx-vc-quote{border-left:3px solid var(--c-accent);padding:2px 0 2px 13px;margin:4px 0 10px;}"
        ".nx-vc-quote p{font-family:'Nanum Myeongjo',serif;font-size:13.5px;line-height:1.7;color:#2C2B28;margin:0;}"
        ".nx-vc-cite{display:inline-block;font-size:11px;color:#5F5E5A;background:var(--c-surface);border-radius:6px;padding:3px 9px;margin-top:6px;}"
        ".nx-vc-note{font-size:12.5px;color:var(--c-caption);border-top:1px solid var(--c-border);margin-top:14px;padding-top:10px;}"
        "</style>"
    )
    parts = [css, '<div class="nx-vc">',
             '<div class="nx-vc-head"><span class="nx-compass"></span><b>DF COMPASS 답변</b></div>']
    for s in secs:
        claims = s.get("claims") or []
        if not claims:
            continue
        title = _h.escape(str(s.get("title") or ""))
        parts.append('<div class="nx-vc-sec">')
        if title:
            parts.append('<p class="nx-vc-sectitle">' + title + '</p>')
        for c in claims:
            txt = _h.escape(str(c.get("text") or ""))
            if txt:
                parts.append('<p class="nx-vc-claim">' + txt + '</p>')
            q = _h.escape(str(c.get("verbatim_quote") or ""))
            if q:
                parts.append('<div class="nx-vc-quote"><p>' + q + '</p></div>')
                cite_raw = " ".join(p for p in (str(c.get("doc_title") or ""), str(c.get("clause") or "")) if p)
                if cite_raw:
                    parts.append('<span class="nx-vc-cite">📎 ' + _h.escape(cite_raw) + '</span>')
        parts.append('</div>')
    for t in (d.get("unsupported_topics") or []):
        parts.append('<p class="nx-vc-note">ℹ️ 사규에서 직접 확인 안 됨 — ' + _h.escape(str(t)) + '</p>')
    for g in (d.get("data_gaps") or []):
        parts.append('<p class="nx-vc-note">⚠️ 필수 문서 누락 — ' + _h.escape(str(g)) + '</p>')
    parts.append('</div>')
    return "".join(parts)


_ENABLE_VERDICT_SHADOW = get_secret("ENABLE_VERDICT_SHADOW", "false").lower() == "true"
_ENABLE_VERDICT_CARD = get_secret("ENABLE_VERDICT_CARD", "false").lower() == "true"


def _build_verdict_card_html(d) -> str:
    """Verdict dict → 목업형 판정 카드(stance pill·grounded 세리프 인용·출처·신뢰도).
    데이터/stance 없으면 기존 브랜드 헤더로 fallback. 색상은 안전쪽(금지·신고대상=레드).
    """
    if not d or not isinstance(d, dict):
        return _answer_card_header_html()
    import html as _h
    stance = str(d.get("stance") or "").strip()
    if not stance:
        return _answer_card_header_html()
    tone = {
        "금지": ("#C8102E", "#FCEEF0"),
        "신고대상": ("#C8102E", "#FCEEF0"),
        "조건부": ("#B7791F", "#FBF3E2"),
        "허용": ("#2F7A4D", "#EAF5EE"),
        "확인필요": ("#6B6A66", "#F0EFEC"),
    }.get(stance, ("#6B6A66", "#F0EFEC"))
    color, bg = tone
    label = _h.escape(str(d.get("label") or stance)[:40])
    badge = _h.escape(str(d.get("badge") or "")[:24])
    quote = _h.escape(str(d.get("quote") or ""))
    cite = _h.escape(" ".join(p for p in (str(d.get("doc_title") or ""), str(d.get("clause") or "")) if p))
    conf = str(d.get("confidence") or "")
    conf_label = {"high": "높은 신뢰도", "medium": "보통 신뢰도", "low": "낮은 신뢰도"}.get(conf, "")
    css = (
        "<style>"
        ".nx-vd{margin:2px 0 14px;}"
        ".nx-vd-pill{display:inline-flex;align-items:center;gap:8px;padding:7px 13px;border-radius:11px;border:1px solid " + color + ";background:" + bg + ";}"
        ".nx-vd-pill .ico{width:8px;height:8px;border-radius:50%;background:" + color + ";flex:0 0 8px;}"
        ".nx-vd-pill b{font-size:13.5px;font-weight:700;color:" + color + ";}"
        ".nx-vd-badge{font-size:11px;font-weight:700;color:" + color + ";background:rgba(255,255,255,0.62);border-radius:6px;padding:2px 8px;}"
        ".nx-vd-quote{border-left:3px solid " + color + ";padding:3px 0 3px 14px;margin:13px 0 9px;}"
        ".nx-vd-quote p{font-family:'Nanum Myeongjo',serif;font-size:14px;line-height:1.7;color:#2C2B28;margin:0;}"
        ".nx-vd-cite{display:inline-block;font-size:11px;color:#5F5E5A;background:var(--c-surface,#F4F1EB);border-radius:6px;padding:3px 9px;margin-top:7px;}"
        ".nx-vd-foot{display:flex;align-items:center;gap:7px;margin-top:11px;font-size:11.5px;color:var(--c-caption,#7A766E);}"
        ".nx-vd-foot .dot{width:7px;height:7px;border-radius:50%;background:" + color + ";flex:0 0 7px;}"
        '[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarAssistant"]){border-left:3px solid var(--c-accent,#C8102E) !important;}'
        "</style>"
    )
    parts = [css, '<div class="nx-vd">',
             '<span class="nx-vd-pill"><span class="ico"></span><b>' + label + '</b>'
             + ('<span class="nx-vd-badge">' + badge + '</span>' if badge else '') + '</span>']
    if quote:
        parts.append('<div class="nx-vd-quote"><p>' + quote + '</p></div>')
        if cite:
            parts.append('<span class="nx-vd-cite">📕 ' + cite + '</span>')
    if conf_label:
        parts.append('<div class="nx-vd-foot"><span class="dot"></span>' + conf_label + '</div>')
    parts.append('</div>')
    return "".join(parts)


def _answer_card_header_html() -> str:
    """답변 카드 상단 브랜드 헤더(레드 점 + 라벨 + 헤어라인) + 답변 카드 좌측 레드 액센트.
    답변 본문과 독립적으로 prepend 되는 HTML — 내용/색상/리스트 구조에 영향 없음.
    """
    return (
        "<style>"
        ".nx-ach{display:flex;align-items:center;gap:8px;margin:2px 0 14px;}"
        ".nx-ach .dot{width:7px;height:7px;border-radius:50%;background:var(--c-accent,#C8102E);flex:0 0 7px;}"
        ".nx-ach b{font-size:11.5px;font-weight:700;letter-spacing:.07em;color:var(--c-primary,#1F1E1D);white-space:nowrap;}"
        ".nx-ach .rule{flex:1;height:1px;background:var(--c-border,#E7E3DC);}"
        '[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarAssistant"]){border-left:3px solid var(--c-accent,#C8102E) !important;}'
        "</style>"
        '<div class="nx-ach"><span class="dot"></span><b>DF COMPASS 답변</b><span class="rule"></span></div>'
    )


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
        '.st-key-hero_send_btn button{height:58px !important;min-height:58px !important;border-radius:14px !important;font-size:21px !important;font-weight:700 !important;}'
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
    _hero_pills = [
        ("선물 받았어요", "거래처에서 선물을 받아도 되나요?"),
        ("동료 부상", "동료가 다쳤어요. 긴급 보고는 어떻게 하나요?"),
        ("법인카드", "법인카드를 개인 용도로 사용해도 되나요?"),
    ]
    _pcols = st.columns(len(_hero_pills))
    for _pi, (_plabel, _pq) in enumerate(_hero_pills):
        if _pcols[_pi].button(_plabel, key="hpill_" + str(_pi), use_container_width=True):
            st.session_state["clicked_q"] = _pq
            st.rerun()


_PROD_ENV_VALUES = {"prod", "production"}

_HISTORY_CAP = 100  # session_state["history"] 최대 entry 수 (FIFO 자르기)

# 🔄 다시 답변 — core/chatbot.ask 시그니처에 temperature/system_prompt
# override 인자가 없어 호출 측에서 model 파라미터 조정이 불가. 차선책으로
# 사용자 question 앞에 다음 prefix 를 prepend + prev_turn 으로 이전 답변
# 컨텍스트를 ask_stream 에 전달 → LLM 이 이전 답변과 다른 관점으로 작성.
# core/ 시그니처는 무수정.
_REROLL_PREFIX = (
    "[다시 답변 요청] 이전 답변과 다른 관점·다른 근거 사규·다른 측면을 "
    "강조하여 답변해주세요. 단, 사실관계는 정확해야 합니다.\n\n원 질문: "
)

# 피드백 사유 chip 옵션 — _render_feedback 가 부정/긍정 분기로 사용.
# DB 의 feedback_reasons (jsonb) 에 선택값 그대로 저장되어 admin 측 집계
# 시 한국어 라벨이 그대로 드러남 — 진단 가독성을 위해 의도된 설계.
_FB_REASONS_NEG = [
    "사실과 달라요",
    "출처가 부족해요",
    "질문 의도 못 파악",
    "답변이 모호함",
    "신고·문의 안내 누락",
    "기타",
]
_FB_REASONS_POS = [
    "정확해요",
    "출처가 명확",
    "실무에 바로 적용 가능",
    "기타",
]


def _push_history(item) -> None:
    """history 에 push 후 cap 초과 시 앞쪽부터 자른다 (FIFO).
    session_state 메모리 누적 방어 — 100건 = user/assistant 50쌍."""
    h = st.session_state.setdefault("history", [])
    h.append(item)
    if len(h) > _HISTORY_CAP:
        del h[: len(h) - _HISTORY_CAP]


def _chunks_to_str_stream(stream_iter, out_holder: dict):
    """ask_stream 의 ("chunk", str) | ("done", Answer) 튜플을 st.write_stream
    호환 str-only generator 로 변환 (PR-Fun3a 페이즈 2).

    ("done", Answer) 시점의 Answer 를 out_holder["ans"] 로 closure 보존 —
    st.write_stream 호출자가 streaming 종료 후 ans 를 회수하도록 한다.
    chunk 추출 외 가공 없음 (커서·prefix 없음 — write_stream 의 native
    append 가 매끄러움 담당).

    예외는 그대로 raise — 호출 측 retry/에러 분기 로직이 받음.
    """
    out_holder.setdefault("ans", None)
    for kind, val in stream_iter:
        if kind == "chunk":
            yield val
        elif kind == "done":
            out_holder["ans"] = val


def _inject_streaming_scroll_js_once() -> None:
    """답변 streaming 시 자동 scroll 추적 JS 를 session 당 1회 주입
    (PR-Fun3a 페이즈 2).

    - MutationObserver 가 body subtree 의 child 추가를 감지 → near-bottom
      이면 smooth scroll 로 끝까지 추적. 사용자가 위로 scroll 했으면 추적 X
      (max - scrollY > 200px threshold).
    - components.html iframe 안의 JS 가 parent window 에 접근 — Streamlit
      same-origin iframe 이라 가능 (이미 timer iframe 에서 동일 패턴 검증).
    - session_state guard 로 중복 주입 차단 — rerun 마다 observer 가 새로
      생기지 않도록.
    - height=0 으로 보이지 않게 — 단지 JS bootstrap 용 슬롯.
    """
    if st.session_state.get("_nx_scroll_js_injected"):
        return
    st.session_state["_nx_scroll_js_injected"] = True
    components.html(
        """
<script>
  (function() {
    try {
      var top = window.parent || window;
      if (top._nx_scroll_observer) return;
      var doc = top.document;
      var THRESHOLD = 200;
      var nearBottom = function() {
        var max = doc.documentElement.scrollHeight - top.innerHeight;
        return (max - top.scrollY) < THRESHOLD;
      };
      var sticky = true;
      top.addEventListener('scroll', function() {
        sticky = nearBottom();
      }, { passive: true });
      var observer = new MutationObserver(function() {
        if (!sticky) return;
        var max = doc.documentElement.scrollHeight - top.innerHeight;
        top.scrollTo({ top: max, behavior: 'smooth' });
      });
      observer.observe(doc.body, { childList: true, subtree: true, characterData: true });
      top._nx_scroll_observer = observer;
    } catch (e) {
      console.warn('[nx-scroll]', e);
    }
  })();
</script>
""",
        height=0,
    )


def _inject_streaming_visual_polish_once() -> None:
    """답변 streaming 영역 visual polish CSS 주입 (PR-Fun3b 페이즈 3).

    `st.write_stream` (PR-Fun3a) 의 native append streaming 위에서 가독성·
    한국어 line-break·font smoothing 만 보강. 진정한 token-append 렌더는
    phase 4 (custom React component) 영역 — 본 함수는 architectural
    refactor 없이 가능한 범위 limit.

    적용 대상: chat_message 안의 Markdown 컨테이너 (사용자/어시스턴트 모두).
    선택자 `[data-testid="stChatMessage"] [data-testid="stMarkdown"]` 은
    Streamlit 1.36+ 의 안정 testid. 미래 버전에서 깨지면 fallback 으로
    `.stMarkdown` class 도 함께 명시.

    fade-in 애니메이션 적용 X — write_stream 의 chunk-마다 markdown 전체
    re-render 와 결합 시 opacity 가 매 chunk 마다 0.5→1 pulsing 으로
    시각적 거슬림. 향후 token-level append 로 전환 시 재고려.

    session 당 1회 — _nx_visual_polish_injected guard.
    """
    if st.session_state.get("_nx_visual_polish_injected"):
        return
    st.session_state["_nx_visual_polish_injected"] = True
    components.html(
        """
<style id="nx-visual-polish-injected">
  /* Korean text rendering polish — line-height·letter-spacing·word-break */
  [data-testid="stChatMessage"] [data-testid="stMarkdown"],
  [data-testid="stChatMessage"] .stMarkdown {
    -webkit-font-smoothing: antialiased;
    -moz-osx-font-smoothing: grayscale;
    text-rendering: optimizeLegibility;
  }
  [data-testid="stChatMessage"] [data-testid="stMarkdown"] p,
  [data-testid="stChatMessage"] [data-testid="stMarkdown"] li,
  [data-testid="stChatMessage"] .stMarkdown p,
  [data-testid="stChatMessage"] .stMarkdown li {
    line-height: 1.75;
    letter-spacing: -0.005em;
    /* keep-all 은 한글 어절 단위 줄바꿈 — 영문/숫자 단어는 그대로 break */
    word-break: keep-all;
    overflow-wrap: anywhere;
  }
  /* 인라인 코드·인용 padding 미세 조정 */
  [data-testid="stChatMessage"] [data-testid="stMarkdown"] code {
    padding: 1px 4px;
    border-radius: 4px;
  }
  /* root scroll behavior 보강 — PR-Fun3a scroll JS 와 함께 동작 */
  html { scroll-behavior: smooth; scroll-padding-bottom: 32px; }
</style>
<script>
  // visual polish 는 CSS-only — JS bootstrap 불필요. 단지 inline 으로
  // CSS 를 parent document 에 주입하기 위해 components.html 사용 (st.markdown
  // 의 unsafe_allow_html 로는 같은 효과지만 components.html 패턴 통일).
  (function() {
    try {
      var top = window.parent || window;
      var doc = top.document;
      // 이미 주입된 경우 skip (rerun 시 다중 주입 방어)
      if (doc.getElementById('nx-visual-polish-mirror')) return;
      // CSS 가 iframe 내부에만 있으면 parent 에 적용 안 됨 → mirror 로 parent 에도.
      var src = document.getElementById('nx-visual-polish-injected');
      if (!src) return;
      var mirror = doc.createElement('style');
      mirror.id = 'nx-visual-polish-mirror';
      mirror.textContent = src.textContent;
      doc.head.appendChild(mirror);
    } catch (e) {
      console.warn('[nx-visual-polish]', e);
    }
  })();
</script>
""",
        height=0,
    )


def _render_beta_banner() -> None:
    s = settings()
    # 정확한 prod 화이트리스트 — 'prod-test' 같은 모호 값에 banner 가 숨지 않음.
    if (s.env_tag or "").lower() in _PROD_ENV_VALUES:
        return
    st.markdown(
        '<div style="background:#f4f4f4; color:#666; padding:8px 14px; '
        'border-radius:6px; font-size:12px; margin-bottom:16px;">'
        '🛡️ 베타 환경입니다. 입력하신 내용은 모델 학습에 사용되지 않습니다. '
        '<span style="color:#888;">자세한 안내는 좌측 사이드바 참조.</span>'
        '</div>',
        unsafe_allow_html=True,
    )


def _check_rate_limit() -> bool:
    """세션 단위 일일 한도. 초과 시 False 반환 (호출자가 안내 문구 출력).
    한국 시간(KST) 자정 기준으로 카운터 리셋. UTC 기준이면 한국 23시에 한도
    초과 후 0시 1분에 다시 시도해도 카운터가 안 풀려 임직원이 혼란.
    회사 이관 + SSO 도입 후에는 user_id_hash 기반 서버 카운터로 교체."""
    s = settings()
    # KST = UTC+9 (DST 없음). pytz 미사용 — 표준 라이브러리만으로.
    kst = _dt.timezone(_dt.timedelta(hours=9))
    today = _dt.datetime.now(kst).date().isoformat()
    rec = st.session_state.get("_rate_rec") or {"date": today, "count": 0}
    if rec["date"] != today:
        rec = {"date": today, "count": 0}
    if rec["count"] >= s.daily_query_limit:
        st.session_state["_rate_rec"] = rec
        return False
    rec["count"] += 1
    st.session_state["_rate_rec"] = rec
    return True


def _render_report_channels_panel(hotlines: dict[str, str]) -> None:
    """신고 방법 안내 박스 — Critical mode (괴롭힘/중대재해/비리/횡령 등) 시 표시.

    PR-Refactor-ActionButton-Per-Category-V2: 앱 footer (line 952-954) 의
    routing rule '신고·조사는 CSR팀 또는 신세계면세점 핫라인' 과 일관성.
    사용자가 사규 절차에 따라 직접 신고 — 'CSR팀 문의' label 사용 안 함.
    """
    ethics_hotline = (hotlines.get("ethics_hotline_url") or "").strip()
    anon_url = (hotlines.get("internal_report_url") or "").strip()
    ext_hotline = (hotlines.get("external_hotline") or "").strip()
    with st.container(border=True):
        st.markdown("**📞 신고 방법 안내**")
        st.markdown(
            "신고·조사 사항은 **CSR팀** 또는 **신세계면세점 핫라인**으로 "
            "접수해 주시기 바랍니다."
        )
        st.markdown(
            "**📋 1차 보고**: SRMS 시스템 즉시 등록 (인지 시점 24시간 內)"
        )
        # PR-Phase-15.2: SRMS 접속 link_button (시급성 순서 — 최상단).
        st.link_button(
            "🔗 SRMS 바로가기",
            "https://rms.shinsegae.com/",
            use_container_width=True,
        )
        if ethics_hotline:
            st.link_button(
                "🏢 신세계면세점 핫라인",
                ethics_hotline,
                use_container_width=True,
            )
        if anon_url:
            st.link_button(
                "🔒 사내 익명 제보 채널",
                anon_url,
                use_container_width=True,
            )
        if ext_hotline:
            st.markdown(f"📞 외부 상담채널: {ext_hotline}")
        st.caption(
            "⚠️ 본 답변은 사규 해석 보조이며, 실제 신고는 사규 절차에 따라 "
            "직접 진행하시기 바랍니다."
        )


def _render_clean_report_panel(hotlines: dict[str, str]) -> None:
    """클린신고 (자진신고) 안내 박스 — 금품·향응 수수 등 본인의 비위 자진 신고.

    PR-Hotline-Branch (사용자 피드백 memory #11 issue 1):
    '신고 방법 안내' 가 사건사고용 (SRMS) 만 안내 → 클린신고 별도 panel 추가.
    """
    anon_url = (hotlines.get("internal_report_url") or "").strip()
    ext_hotline = (hotlines.get("external_hotline") or "").strip()
    with st.container(border=True):
        st.markdown("**💼 클린신고 (자진 신고) 안내**")
        st.markdown(
            "금품·향응 수수 등 이해관계자와의 비위 행위는 "
            "**SHRS**의 **클린신고신청서**를 통해 자진 신고하시기 바랍니다."
        )
        st.markdown(
            "**📋 등록방법**:  \n"
            "SHRS → **윤리경영** → **윤리실천등록** → **클린신고신청서**"
        )
        st.markdown(
            "**📋 신고 기한**: 수수 확인일로부터 **3일 이내** "
            "(7일 이내 자진 신고 시 징계 감경 가능)"
        )
        st.link_button(
            "🔗 SHRS 바로가기",
            "https://hr.shinsegae.com/index.jsp",
            use_container_width=True,
        )
        if anon_url:
            st.link_button(
                "🔒 사내 익명 제보 채널",
                anon_url,
                use_container_width=True,
            )
        if ext_hotline:
            st.markdown(f"📞 외부 상담채널: {ext_hotline}")
        st.caption(
            "⚠️ 본 답변은 사규 해석 보조이며, 실제 신고는 사규 절차에 따라 "
            "직접 진행하시기 바랍니다."
        )


def _render_hr_inquiry_panel(hotlines: dict[str, str]) -> None:
    """인사교육팀 문의 안내 박스 — hotline_config 4개 키 매핑, 빈 값은 렌더 생략.
    DB 스키마 변경 없이 기존 키만 사용 (`hr_contact_text`, `hr_chatbot_url`,
    `internal_report_url`, `external_hotline`)."""
    hr_text = (hotlines.get("hr_contact_text") or "").strip()
    hr_chatbot = (hotlines.get("hr_chatbot_url") or "").strip()
    anon_url = (hotlines.get("internal_report_url") or "").strip()
    ext_hotline = (hotlines.get("external_hotline") or "").strip()
    with st.container(border=True):
        st.markdown("**📞 인사교육팀 문의 채널**")
        st.markdown(hr_text or "인사교육팀에 직접 문의하세요.")
        # URL 항목은 placeholder(example.invalid) 일 수 있으므로 그대로 link_button —
        # admin 이 hotline_config 갱신하면 즉시 반영.
        if hr_chatbot:
            st.link_button("💬 사내 인사 챗봇", hr_chatbot, use_container_width=True)
        if anon_url:
            st.link_button("🔒 익명 신고 채널", anon_url, use_container_width=True)
        if ext_hotline:
            # 외부 상담채널은 URL 이 아닌 전화번호("고용노동부 1350") 가 들어
            # 있어 link_button 부적합 → 텍스트 라인으로.
            st.markdown(f"📞 외부 상담채널: {ext_hotline}")
        st.caption(
            "⚠️ 본 답변은 사규 해석 보조이며, 인사 행정 결정은 인사교육팀 문의가 우선합니다."
        )


def _render_action_buttons(
    msg_idx: int,
    *,
    original_q: str | None,
    prev_answer: str | None,
    hotlines: dict[str, str],
    contexts: list[dict] | None = None,
    answer_text: str | None = None,
    is_critical: bool = False,
    confidence: str | None = None,
) -> None:
    """답변 본문 직후 두 액션: [📞 인사교육팀 문의] [🔄 다시 답변].

    인사교육팀 문의 — toggle. session_state["hr_open"] set 으로 msg_idx 별 독립.
    다시 답변 — 1회 한정. session_state["rerolled_msgs"] set 으로 msg_idx 별
    중복 차단. 클릭 시 session_state["_pending_reroll"] 에 reroll request 적재
    후 rerun → main() 다음 사이클에서 _run_ask(reroll_of=...) 로 처리.

    can_reroll=False (이미 받음 / original_q·prev_answer 누락) 일 때 reroll
    자리는 button 대신 회색 markdown placeholder 로 대체. Streamlit 1.57
    widget rerun diffing 에서 disabled+help 인자가 reroll 측에만 붙으면 col_b
    button 의 ID 안정성이 깨져 rerun 마다 button 이 누적되는 회귀가 관측되어,
    inquiry 버튼과 인자 시그니처를 동일하게 정렬 (disabled/help 모두 제거).
    """
    hr_open: set = st.session_state.setdefault("hr_open", set())
    rerolled: set = st.session_state.setdefault("rerolled_msgs", set())
    already_rerolled = msg_idx in rerolled
    can_reroll = (original_q is not None and prev_answer is not None
                  and not already_rerolled)

    # PR-Multi-Signal-Button-Branch-Refactor:
    # 분기 logic 을 core/nexus_button_branch.classify_button 으로 추출
    # — UI ↔ Validation 통일 + Multi-signal (query intent + contexts + answer).
    from core.nexus_button_branch import classify_button

    _decision = classify_button(
        query=(original_q or ""),
        answer_text=(answer_text or ""),
        contexts=contexts,
        is_critical=is_critical,
        confidence=(confidence or ""),
    )
    is_hr_graceful = (_decision == "hr_inquiry")
    is_report_related = (_decision == "report")
    is_clean_report = (_decision == "clean_report")
    show_inquiry_button = (_decision != "hidden")

    # 일반 query — button 없이 reroll 만 표시 (full-width).
    if not show_inquiry_button:
        if can_reroll:
            reroll_clicked = st.button(
                "🔄 다시 답변",
                key=f"reroll_btn_{msg_idx}",
                use_container_width=True,
            )
            if reroll_clicked:
                rerolled.add(msg_idx)
                st.session_state["_pending_reroll"] = {
                    "original_q":  original_q,
                    "prev_answer": prev_answer,
                }
                st.rerun()
        return

    # Button label 결정 (분기 조건에 따라 — 3-way).
    if is_hr_graceful:
        # 인사 graceful — 휴가/평가/근태 등 인사 routing
        hr_label = (
            "📞 인사교육팀 문의 닫기" if msg_idx in hr_open
            else "📞 인사교육팀 문의"
        )
    elif is_clean_report:
        # PR-Hotline-Branch: 클린신고 (자진신고) — SHRS CSR경영란
        hr_label = (
            "💼 클린신고 안내 닫기" if msg_idx in hr_open
            else "💼 클린신고 안내"
        )
    else:
        # is_report_related — 신고 방법 안내 (사건사고 / SRMS)
        hr_label = (
            "📞 신고 방법 안내 닫기" if msg_idx in hr_open
            else "📞 신고 방법 안내"
        )

    # 목업 PROACTIVE DOCK: "다음 단계" 라벨 + 굵은 빨간 주 액션(full-width) +
    # 보조 다시답변. 컬럼 2분할 → 세로 스택으로 주 액션 강조. 분기 logic 동일.
    st.markdown(
        '<div style="font-size:11.5px;font-weight:700;letter-spacing:0.06em;'
        'color:#9A968D;margin:8px 0 6px 2px;">다음 단계</div>',
        unsafe_allow_html=True,
    )
    hr_clicked = st.button(
        hr_label, key=f"hr_btn_{msg_idx}", type="primary",
        use_container_width=True,
    )
    if can_reroll:
        reroll_clicked = st.button(
            "🔄 다시 답변",
            key=f"reroll_btn_{msg_idx}",
            use_container_width=True,
        )
    else:
        # disabled 인자를 쓰지 않고 markdown placeholder 로 회색 표기.
        # 이미 다시 답변 받았거나 history meta 가 누락된 fallback 메시지.
        st.markdown(
            "<div style='text-align:center; padding:8px 0; "
            "color:#aaa; font-size:14px; border:1px solid #eee; "
            "border-radius:8px; background:#fafafa;'>"
            "🔄 다시 답변 받음"
            "</div>",
            unsafe_allow_html=True,
        )
        reroll_clicked = False
    if hr_clicked:
        if msg_idx in hr_open:
            hr_open.remove(msg_idx)
        else:
            hr_open.add(msg_idx)
        st.rerun()
    if reroll_clicked:
        rerolled.add(msg_idx)
        st.session_state["_pending_reroll"] = {
            "original_q":  original_q,
            "prev_answer": prev_answer,
        }
        st.rerun()
    if msg_idx in hr_open:
        # PR-Hotline-Branch: 3-way 분기 (clean_report / report / hr_inquiry)
        if is_clean_report:
            _render_clean_report_panel(hotlines)
        elif is_report_related:
            _render_report_channels_panel(hotlines)
        else:
            _render_hr_inquiry_panel(hotlines)


def _feedback_update(sb, payload: dict, *,
                     query_log_id: int | None,
                     masked_question: str | None) -> bool:
    """PR-Fun1.5: query_log_id 우선 매칭, 없으면 masked_question + 최근 5분
    ts 윈도우 fallback. PR-S1 의 RLS 가 anon SELECT 차단 → INSERT RETURNING
    이 빈 list → ans.query_log_id None 인 경우 대비. UPDATE 자체는 anon
    INSERT/UPDATE 정책 통과로 실제 row 수정 가능 (RETURNING 만 차단).

    매칭이 다중 row 잡을 위험: query_masked 가 동일한 질문의 짧은 시간 내
    중복 INSERT 거의 X (사용자 1명 기준). 5분 윈도우로 충분 — race 위험은
    베타 단계 acceptable.

    PR-Beta-Hotfix-Feedback: stderr 진단 로깅 강화. prefix
    `[QUERY_LOGS FB OK]` / `[QUERY_LOGS FB FAIL]` 로 Streamlit Cloud Logs
    에서 grep 추출. 실 update row 가 0 일 가능성도 노출 (RLS RETURNING
    blocked 상태에서는 data 가 빈 list 라 0 vs 1 구분 불가하지만 path
    선택 (id|masked) 와 payload key list 만이라도 가시화).
    """
    import sys
    path = "id" if query_log_id else ("masked" if masked_question else "none")
    payload_keys = list(payload.keys())
    try:
        if query_log_id:
            res = sb.table("query_logs").update(payload).eq("id", query_log_id).execute()
        elif masked_question:
            from datetime import datetime as _dt, timedelta as _td, timezone as _tz
            recent = (_dt.now(_tz.utc) - _td(minutes=5)).isoformat()
            res = (
                sb.table("query_logs")
                .update(payload)
                .eq("query_masked", masked_question)
                .gte("ts", recent)
                .execute()
            )
        else:
            print(
                f"[QUERY_LOGS FB FAIL]  reason=no_identifier  payload_keys={payload_keys}",
                file=sys.stderr, flush=True,
            )
            return False
        # data 길이는 RLS RETURNING 차단 환경에서 0 으로 나올 수 있음 — 진단용 참고만.
        rows = len(getattr(res, "data", None) or [])
        print(
            f"[QUERY_LOGS FB OK]  path={path}  query_log_id={query_log_id}  "
            f"masked_head={(masked_question or '')[:30]!r}  "
            f"payload_keys={payload_keys}  returned_rows={rows}",
            file=sys.stderr, flush=True,
        )
        return True
    except Exception as e:
        msg_parts = [
            f"[QUERY_LOGS FB FAIL]",
            f"path={path}",
            f"type={type(e).__name__}",
            f"msg={e}",
        ]
        for attr in ("message", "code", "details", "hint", "status_code"):
            val = getattr(e, attr, None)
            if val is not None and val != "":
                msg_parts.append(f"{attr}={val}")
        msg_parts.append(f"query_log_id={query_log_id}")
        msg_parts.append(f"masked_head={(masked_question or '')[:30]!r}")
        msg_parts.append(f"payload_keys={payload_keys}")
        print("  ".join(msg_parts), file=sys.stderr, flush=True)
        return False


def _record_feedback_click(
    sb, query_log_id: int | None, *,
    positive: bool, masked_question: str | None = None,
) -> bool:
    """클릭 시점 즉시 기록 — feedback (기존 ±1, admin/radar 호환) +
    feedback_type (신규, 'positive'/'negative') + feedback_at 동시 갱신.

    db/04 의 feedback (smallint) 컨벤션은 -1/+1 (db/04_beta_hooks.sql:25).
    """
    from datetime import datetime, timezone
    payload = {
        "feedback":      1 if positive else -1,
        "feedback_type": "positive" if positive else "negative",
        "feedback_at":   datetime.now(timezone.utc).isoformat(),
    }
    return _feedback_update(
        sb, payload,
        query_log_id=query_log_id, masked_question=masked_question,
    )


def _record_feedback_submit(
    sb, query_log_id: int | None, *,
    reasons: list[str], comment: str | None,
    masked_question: str | None = None,
) -> bool:
    """제출 시 reasons (jsonb 배열) + comment (기존 text) 추가 갱신.
    feedback_at 은 클릭 시점 그대로 둔다."""
    payload: dict = {"feedback_reasons": reasons}
    if comment:
        payload["feedback_comment"] = comment[:500]
    return _feedback_update(
        sb, payload,
        query_log_id=query_log_id, masked_question=masked_question,
    )


def _render_feedback(
    sb, msg_idx: int, query_log_id: int | None,
    *, masked_question: str | None = None,
) -> None:
    """답변 1건당 피드백 — CTA + 사유 chip + 자유 의견.

    상태 (session_state):
      feedback_clicked: dict[msg_idx → 'positive' | 'negative']
      feedback_submitted: set[msg_idx]

    상태별 렌더:
      (A) 미클릭 → CTA 라벨 + caption + 두 버튼
      (B) 클릭 후, 미제출 → 두 버튼 영역은 markdown placeholder
                            (선택된 쪽만 강조). 그 아래 사유 chip + textarea +
                            [제출] [건너뛰기] 폼 펼침.
      (C) 제출 또는 건너뛰기 → "✅ 피드백 감사합니다" caption 만.

    Streamlit 1.57 widget rerun diffing 회피 (PR-1B 후속에서 학습):
      - disabled / help 인자 사용 금지 → 분기로 button vs markdown 토글
      - 모든 위젯 key 에 msg_idx 포함

    history replay 동작: session_state 의 feedback_submitted 가 같은 세션 내
    유지되므로 새로고침 없이는 (C) 상태 자연스럽게 재현. 페이지 새로고침으로
    session_state 초기화 시 history 자체도 비어 replay 자체가 안 일어남
    (베타 단계 비용 가드).

    PR-Fun1.5: PR-S1 의 RLS SELECT 차단으로 INSERT RETURNING 빈 list →
    ans.query_log_id None 가 흔함. masked_question 이 fallback 매칭자로
    record_feedback 의 update 경로가 query_masked + 최근 5분 ts 윈도우로
    row 매칭. 둘 다 None 이면 추적 불가 → 가드.
    """
    if not query_log_id and not masked_question:
        return
    clicked: dict = st.session_state.setdefault("feedback_clicked", {})
    submitted: set = st.session_state.setdefault("feedback_submitted", set())

    # (C) 제출 또는 건너뛰기 완료
    if msg_idx in submitted:
        st.caption("✅ 피드백 감사합니다.")
        return

    state = clicked.get(msg_idx)  # None | 'positive' | 'negative'

    # (A) 미클릭
    if state is None:
        st.markdown("**이 답변이 정확하고 도움이 되셨나요?**")
        st.caption("베타 단계입니다. 여러분의 피드백이 답변 품질 개선에 직결됩니다.")
        col_pos, col_neg = st.columns(2)
        pos_clicked = col_pos.button(
            "👍 도움됐어요", key=f"fb_pos_{msg_idx}", use_container_width=True,
        )
        neg_clicked = col_neg.button(
            "👎 아쉬워요", key=f"fb_neg_{msg_idx}", use_container_width=True,
        )
        # PR-Beta-Hotfix-Feedback: UI 상태는 DB update 결과와 무관하게 항상
        # 진행. 이전 패턴 (DB 성공 시에만 clicked 설정) 은 update 가 silent
        # 실패할 때 click 이 작동 X 처럼 보이는 사고. update 실패 시 toast
        # 로 사용자에게 노출 + stderr 로 운영자 진단.
        if pos_clicked:
            ok = _record_feedback_click(
                sb, query_log_id, positive=True,
                masked_question=masked_question,
            )
            clicked[msg_idx] = "positive"
            if not ok:
                st.toast(
                    "피드백 저장 실패 — 다시 시도해주세요",
                    icon="⚠️",
                )
            st.rerun()
        if neg_clicked:
            ok = _record_feedback_click(
                sb, query_log_id, positive=False,
                masked_question=masked_question,
            )
            clicked[msg_idx] = "negative"
            if not ok:
                st.toast(
                    "피드백 저장 실패 — 다시 시도해주세요",
                    icon="⚠️",
                )
            st.rerun()
        return

    # (B) 클릭 후 — 두 버튼 자리는 markdown placeholder (선택된 쪽만 강조)
    is_positive = (state == "positive")
    pos_selected_html = (
        "<div style='text-align:center; padding:8px 0; color:#1A1A1A; "
        "font-size:14px; border:2px solid #1A1A1A; border-radius:4px; "
        "background:#fff; font-weight:600;'>✓ 👍 도움됐어요</div>"
    )
    pos_inactive_html = (
        "<div style='text-align:center; padding:8px 0; color:#aaa; "
        "font-size:14px; border:1px solid #eee; border-radius:4px; "
        "background:#fafafa;'>👍 도움됐어요</div>"
    )
    neg_selected_html = (
        "<div style='text-align:center; padding:8px 0; color:#1A1A1A; "
        "font-size:14px; border:2px solid #1A1A1A; border-radius:4px; "
        "background:#fff; font-weight:600;'>✓ 👎 아쉬워요</div>"
    )
    neg_inactive_html = (
        "<div style='text-align:center; padding:8px 0; color:#aaa; "
        "font-size:14px; border:1px solid #eee; border-radius:4px; "
        "background:#fafafa;'>👎 아쉬워요</div>"
    )
    col_a, col_b = st.columns(2)
    col_a.markdown(pos_selected_html if is_positive else pos_inactive_html,
                   unsafe_allow_html=True)
    col_b.markdown(neg_selected_html if not is_positive else neg_inactive_html,
                   unsafe_allow_html=True)

    # 사유 chip + 자유 의견
    options = _FB_REASONS_POS if is_positive else _FB_REASONS_NEG
    chip_label = ("어떤 점이 좋았나요? (복수 선택 가능)" if is_positive
                  else "어떤 점이 아쉬웠나요? (복수 선택 가능)")
    reasons = st.pills(
        chip_label,
        options=options,
        selection_mode="multi",
        key=f"fb_reasons_{msg_idx}",
    )
    comment = st.text_area(
        "자유 의견 (선택)",
        height=80,
        placeholder="구체적인 의견을 자유롭게 적어주세요 (선택)",
        key=f"fb_comment_{msg_idx}",
    )
    col_submit, col_skip = st.columns(2)
    submit_clicked = col_submit.button(
        "제출", key=f"fb_submit_{msg_idx}", use_container_width=True,
    )
    skip_clicked = col_skip.button(
        "건너뛰기", key=f"fb_skip_{msg_idx}", use_container_width=True,
    )
    if submit_clicked:
        # PR-Beta-Hotfix-Feedback: click 헬퍼와 동일하게 UI 진행 우선.
        # update 실패해도 submitted 처리 — 사용자에게 (C) caption 표시.
        ok = _record_feedback_submit(
            sb, query_log_id,
            reasons=reasons or [], comment=comment,
            masked_question=masked_question,
        )
        submitted.add(msg_idx)
        if not ok:
            st.toast(
                "피드백 저장 실패 — 운영자에게 보고해주세요",
                icon="⚠️",
            )
        st.rerun()
    if skip_clicked:
        # 건너뛰기 — DB 추가 쓰기 없음 (이미 클릭 시 type/at 기록됨)
        submitted.add(msg_idx)
        st.rerun()


def _render_mode_buttons(msg_idx: int) -> None:
    """답변 마지막에 멀티 턴 모드 버튼 표시 (정상 답변 한정).

    "🔗 관련 질문" → next_turn_mode="followup" → 다음 _run_ask 가 직전 1턴
    (질문/답변)을 prev_turn 으로 ask() 에 전달.
    "✨ 새 주제" → next_turn_mode="new" → prev_turn=None.

    msg_idx: history 인덱스. 위젯 키 충돌 방지 + 다중 클릭 차단용.
    """
    clicked_key = f"_mode_clicked_{msg_idx}"
    already_clicked = st.session_state.get(clicked_key, False)
    col1, col2, _ = st.columns([1, 1, 4])
    with col1:
        if st.button("🔗 관련 질문", key=f"mode_fu_{msg_idx}", disabled=already_clicked):
            st.session_state["next_turn_mode"] = "followup"
            st.session_state[clicked_key] = True
            st.toast("🔗 관련 질문 모드 — 다음 입력은 이전 답변과 연결됩니다")
            st.rerun()
    with col2:
        if st.button("✨ 새 주제", key=f"mode_new_{msg_idx}", disabled=already_clicked):
            st.session_state["next_turn_mode"] = "new"
            st.session_state[clicked_key] = True
            st.toast("✨ 새 주제로 시작합니다")
            st.rerun()


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


def _run_ask(
    sb, q: str, cat: str, hotlines: dict,
    *,
    reroll_of: dict | None = None,
    hard_category: str | None = None,
) -> None:
    """답변 생성. reroll_of={"original_q","prev_answer"} 면 다시 답변 모드.

    reroll 모드에서는:
      - user 메시지 chat_message + history push 를 skip (사용자가 새로 입력
        한 게 아니므로). 답변 카드만 새로 추가 → 두 답변을 비교 가능.
      - prev_turn 자동 설정 (이전 답변을 LLM 컨텍스트에).
      - question 앞에 _REROLL_PREFIX prepend → 다른 관점 강조.
    core/chatbot.ask 시그니처는 무수정 (temperature/system_prompt override
    인자가 없어 호출 측 차선책).
    """
    # 채팅 활성 sticky 플래그 — 질문 처리가 시작되면(스트리밍 중단·재진입
    # 무관) 빈 홈을 다시 그리지 않도록. user 메시지 history push 보다 _먼저_
    # 세팅 → interrupt 로 history 가 빈 채로 재렌더돼도 빈 홈 재등장·칩
    # 재클릭 루프 차단. 새 세션(history init)에서만 False 로 리셋.
    st.session_state["_chat_active"] = True
    import sys
    import traceback
    # ── 진단 로그 (PR fix/run-ask-answer-display) ──
    # STRUCTURED_SYNTHESIS_ENABLED='true' 가 Secrets 에 설정됐는데도 logs 에
    # structured_ask 호출 흔적 zero → flag 가 settings() 에 제대로 매핑됐는지
    # + 어느 branch 가 실제 실행되는지 stderr 로 가시화.
    try:
        _diag_s = settings()
        print(
            f"[_run_ask] structured_enabled="
            f"{getattr(_diag_s, 'structured_synthesis_enabled', 'ATTR_MISSING')!r} "
            f"verified_enabled="
            f"{getattr(_diag_s, 'chatbot_use_verified_ask', 'ATTR_MISSING')!r} "
            f"q_head={q[:60]!r}",
            file=sys.stderr, flush=True,
        )
    except Exception as _diag_err:
        print(
            f"[_run_ask] diag settings() failed: "
            f"{type(_diag_err).__name__}: {_diag_err}",
            file=sys.stderr, flush=True,
        )
    if not _check_rate_limit():
        s = settings()
        with st.chat_message("assistant", avatar="🧭"):
            st.warning(
                f"⚠️ 오늘 질의 한도({s.daily_query_limit}회)를 초과했습니다. "
                "베타 비용 가드 정책입니다. 내일 다시 이용해 주세요."
            )
        return

    # 멀티 턴 모드 체크 (한 턴 한정, pop 으로 즉시 삭제). 사용자가 직전 답변
    # 마지막에 "🔗 관련 질문" 클릭 → next_turn_mode="followup". 그 외는 "new".
    # reroll 모드에서는 followup 결정 무시 (reroll 이 prev_turn 을 강제).
    mode = st.session_state.pop("next_turn_mode", "new")
    prev_turn: dict | None = None
    effective_q = q
    if reroll_of is not None:
        prev_turn = {
            "question": reroll_of["original_q"],
            "answer":   reroll_of["prev_answer"],
        }
        effective_q = _REROLL_PREFIX + reroll_of["original_q"]
        # 호출 인자 가시성 — reroll prefix·prev_turn 가 실제 ask_stream 으로
        # 들어가는지 확인 (검증 체크리스트 항목 6 대체 — temperature override
        # 가 core 시그니처상 불가하므로 question/prev_turn 만 확인).
        import sys as _sys
        print(
            f"[reroll] prefix_applied=True prev_q_len={len(prev_turn['question'])} "
            f"prev_a_len={len(prev_turn['answer'])} effective_q_head="
            f"{effective_q[:80]!r}",
            file=_sys.stderr, flush=True,
        )
    elif mode == "followup":
        history = st.session_state.get("history", [])
        # 마지막 assistant entry + 그 직전 user entry 추출
        last_assistant_idx = None
        for i in range(len(history) - 1, -1, -1):
            if history[i][0] == "assistant":
                last_assistant_idx = i
                break
        if last_assistant_idx is not None and last_assistant_idx > 0:
            if history[last_assistant_idx - 1][0] == "user":
                prev_turn = {
                    "question": history[last_assistant_idx - 1][1],
                    "answer": history[last_assistant_idx][1],
                }

    if reroll_of is not None:
        st.caption("🔄 같은 질문에 다른 관점에서 답변 (1회 한정) — 이전 답변은 위에 그대로 유지")
    elif prev_turn is not None:
        st.caption("🔗 관련 추가 질문 모드 — 이전 답변과 연결됩니다")

    if reroll_of is None:
        _push_history(("user", q, {}))
        with st.chat_message("user", avatar="👤"):
            st.markdown(q)

    ans = None
    _verdict_dict = None
    last_err: Exception | None = None
    tb_str = ""
    friendly_msg = ""
    # PR-Fun3a 페이즈 2: streaming 시 자동 scroll 추적 JS 주입 (session 1회).
    # MutationObserver 가 body subtree 변경 감지 → near-bottom 이면 끝까지
    # smooth scroll. 사용자가 위로 scroll 한 상태면 추적 정지.
    _inject_streaming_scroll_js_once()
    # PR-Fun3b 페이즈 3: typography·smoothing visual polish CSS 주입 (1회).
    # write_stream 위에서 한국어 가독성·font-smoothing·smooth scroll 보강.
    # 진정한 token-append render 는 phase 4 (custom React component) 영역.
    _inject_streaming_visual_polish_once()

    with st.chat_message("assistant", avatar="🧭"):
        # 답변 본문 placeholder — streaming 점진 표시 + 후처리 단일 update.
        # status 컨테이너보다 위쪽 영역에 자리 잡아 사용자는 처리 단계 메시지
        # 위에서 답변이 점진적으로 그려지는 걸 본다. status 종료(collapsed)
        # 후에도 placeholder 는 그대로 답변 본문을 유지.
        _hdr_ph = st.empty()
        _hdr_ph.markdown(_answer_card_header_html(), unsafe_allow_html=True)
        answer_placeholder = st.empty()
        # Timer placeholder — status 밖에 자리 잡아 status collapsed 후에도
        # 그대로 보이도록. 답변 진행 중에는 components.html 의 JS 카운터,
        # 답변 완료 시 markdown 으로 "X초 만에 답변 완료" 정적 메시지로 교체.
        timer_placeholder = st.empty()

        # avg_latency 캐시 (status 진입 전 계산 — timer_placeholder 가 status
        # 밖에서 components.html 을 그리려면 _avg_s 가 미리 결정돼야 함).
        _now = _time.time()
        if (
            "avg_latency_s" not in st.session_state
            or _now - st.session_state.get("avg_latency_at", 0) > 300
        ):
            st.session_state["avg_latency_s"] = get_avg_latency_seconds(sb)
            st.session_state["avg_latency_at"] = _now
        _avg_s = st.session_state["avg_latency_s"]

        # JS setInterval 실시간 카운터. components.html 의 iframe 안에서
        # self-contained 동작 — st.markdown(unsafe_allow_html) sandbox 우회.
        # 답변 완료 시 timer_placeholder.markdown(...) 으로 정적 메시지 교체
        # → iframe 자체가 사라지면서 setInterval 도 자동 cleanup.
        with timer_placeholder.container():
            components.html(
                f"""
<div id="dfc-elapsed-wrap" style="background:#FAF6F1;padding:10px 14px;
     border-radius:10px;font-family:-apple-system,'Segoe UI',sans-serif;
     font-size:13px;color:#666;display:flex;justify-content:space-between;
     align-items:center;border:1px solid #EDE6DC;box-sizing:border-box;">
  <span>⏱️ <span id="dfc-elapsed" style="font-weight:600;color:#C8102E;">0</span>초 경과</span>
</div>
<script>
  (function() {{
    var start = Date.now();
    var elem = document.getElementById('dfc-elapsed');
    if (!elem) return;
    setInterval(function() {{
      elem.innerText = Math.round((Date.now() - start) / 1000);
    }}, 250);
  }})();
</script>
""",
                height=60,
            )

        # PR-Fun1.6: st.empty placeholder + emoji progress 한 줄 패턴.
        # PR-Fun1.8: CSS keyframes (nx-spin / nx-pulse) class + st.progress
        # bar 단계별 갱신. emoji 자체 애니메이션 + 시각적 진행률.
        # 목업 THINKING: 나침반 스피너 + 상태 한 줄. 진행 바는 CSS 로 숨기되
        # progress_bar 변수는 후속 .progress()/.empty() 호환 위해 유지.
        st.markdown(
            "<style>"
            '[data-testid="stProgress"]{display:none !important;}'
            ".nx-think{display:flex;align-items:center;gap:14px;padding:16px 4px;}"
            ".nx-think-spin{display:inline-flex;align-items:center;justify-content:center;"
            "width:44px;height:44px;border-radius:50%;background:rgba(200,16,46,0.08);"
            "font-size:22px;animation:nx-spin 2s linear infinite;}"
            ".nx-think-txt{display:flex;flex-direction:column;gap:3px;}"
            ".nx-think-line{font-size:15px;font-weight:600;color:var(--c-primary);}"
            ".nx-think-sub{font-size:12.5px;color:#9A968D;}"
            "</style>",
            unsafe_allow_html=True,
        )
        progress_placeholder = st.empty()
        progress_bar = st.progress(0, text="진행 중...")

        def _spinner_html(line: str, sub: str = "") -> str:
            _sub = f'<div class="nx-think-sub">{sub}</div>' if sub else ""
            return (
                '<div class="nx-think"><span class="nx-think-spin">🧭</span>'
                '<div class="nx-think-txt">'
                f'<div class="nx-think-line">{line}</div>{_sub}'
                "</div></div>"
            )

        progress_placeholder.markdown(
            _spinner_html("관련 사규 탐색 중…", "근거 조항 분석 · 판정 생성"),
            unsafe_allow_html=True,
        )

        def _on_progress(stage: str, payload: dict) -> None:
            if stage == "analyze":
                progress_placeholder.markdown(
                    _spinner_html("질문 분석 중…", "핵심 쟁점·도메인 파악"),
                    unsafe_allow_html=True,
                )
            elif stage == "search_start":
                progress_placeholder.markdown(
                    _spinner_html("관련 사규 탐색 중…", "근거 조항 검색"),
                    unsafe_allow_html=True,
                )
            elif stage == "synonym_substitution":
                _subs = payload.get("substitutions") or []
                if _subs:
                    _subs_text = ", ".join(
                        f"`{s}` → `{p}`" for s, p in _subs if s and p
                    )
                    if _subs_text:
                        st.info(f"💡 다음 사규 용어로 검색했습니다: {_subs_text}")
            elif stage == "search_rpc_done":
                _matched = payload.get("matched", 0)
                progress_placeholder.markdown(
                    _spinner_html("관련 사규 탐색 중…", f"{_matched}개 사규 매칭 · 의미 재정렬"),
                    unsafe_allow_html=True,
                )
            elif stage == "search_done":
                total = payload.get("total", 0)
                if total == 0:
                    progress_placeholder.markdown(
                        _spinner_html("답변 작성 중…", "검색 결과 없음 — 답변에 한계가 있을 수 있어요"),
                        unsafe_allow_html=True,
                    )
                    return
                seen: set[str] = set()
                unique_titles: list[str] = []
                for t in payload.get("doc_titles", []):
                    if t and t not in seen:
                        unique_titles.append(t)
                        seen.add(t)
                shown = unique_titles[:2]
                more = len(unique_titles) - len(shown)
                title_str = ", ".join(shown)
                if more > 0:
                    title_str += f" 외 {more}건"
                progress_placeholder.markdown(
                    _spinner_html("답변 작성 중…", f"근거 사규: {title_str}"),
                    unsafe_allow_html=True,
                )
            elif stage == "complete":
                pass

        # ─────────────────────────────────────────────────
        # Phase 7.5 (PR #108): X+ structured_ask 분기 (최우선).
        # STRUCTURED_SYNTHESIS_ENABLED=True 시 auto_classify → retrieve →
        # auto_golden → structured synthesis (헌법적 제약) → deterministic verify.
        # 기본 False — 라이브 chat 영향 zero.
        # ─────────────────────────────────────────────────
        _s_phase75 = settings()
        if getattr(_s_phase75, "structured_synthesis_enabled", False):
            print("[_run_ask] X+ structured_ask branch entered", file=sys.stderr, flush=True)
            try:
                from core.orchestration.structured_ask import structured_ask
                with st.spinner("🏛️ 답변 생성 + 검증 중... (약 30~60초 소요)"):
                    progress_bar.progress(0.3, text="auto_classify → retrieve → 검증 중...")
                    xres = structured_ask(sb, effective_q, audit_source="live_chat")
                    progress_bar.progress(1.0, text="✅ 검증 완료")
                    # === [PR-Fix-Render-1] X+ 답변 렌더 안전망 시작 ===
                    import sys as _rf_sys, traceback as _rf_tb
                    import streamlit as _rf_st

                    _rf_md = None
                    _rf_xres_type = type(xres).__name__ if xres is not None else "None"
                    try:
                        _rf_md = xres.rendered_markdown if xres is not None else None
                    except Exception as _rf_e_attr:
                        print(f"[_run_ask:X+:RENDER] attr_error {type(_rf_e_attr).__name__}: {_rf_e_attr}", file=_rf_sys.stderr, flush=True)

                    _rf_md_len = len(_rf_md) if isinstance(_rf_md, str) else -1
                    print(f"[_run_ask:X+:RENDER] xres={_rf_xres_type} md_len={_rf_md_len}", file=_rf_sys.stderr, flush=True)

                    if isinstance(_rf_md, str) and _rf_md.strip():
                        # 1순위: 기존 placeholder 가 있으면 사용 (스트리밍 UI 와 일관성)
                        _rf_used_placeholder = False
                        try:
                            _rf_ph = locals().get("answer_placeholder", None)
                            if _rf_ph is not None and hasattr(_rf_ph, "markdown"):
                                _rf_ph.markdown(_rf_md)
                                _rf_used_placeholder = True
                                print(f"[_run_ask:X+:RENDER] placeholder.markdown OK", file=_rf_sys.stderr, flush=True)
                        except Exception as _rf_e_ph:
                            print(f"[_run_ask:X+:RENDER] placeholder fail {type(_rf_e_ph).__name__}: {_rf_e_ph}", file=_rf_sys.stderr, flush=True)
                            print(_rf_tb.format_exc(), file=_rf_sys.stderr, flush=True)
                        # 2순위: placeholder 가 없거나 실패했으면 st.markdown 직접 (반드시 화면에 박힘)
                        if not _rf_used_placeholder:
                            try:
                                _rf_st.markdown(_rf_md)
                                print(f"[_run_ask:X+:RENDER] st.markdown direct OK", file=_rf_sys.stderr, flush=True)
                            except Exception as _rf_e_st:
                                print(f"[_run_ask:X+:RENDER] st.markdown fail {type(_rf_e_st).__name__}: {_rf_e_st}", file=_rf_sys.stderr, flush=True)
                                print(_rf_tb.format_exc(), file=_rf_sys.stderr, flush=True)
                    else:
                        print(f"[_run_ask:X+:RENDER] empty/None md — showing error", file=_rf_sys.stderr, flush=True)
                        try:
                            _rf_st.error(f"⚠ 답변 생성은 완료되었으나 출력이 비어있습니다 (md_len={_rf_md_len}). 다시 시도하거나 관리자에게 문의하세요.")
                        except Exception:
                            pass
                    # === [PR-Fix-Render-1] X+ 답변 렌더 안전망 끝 ===
                _v = xres.verification.verdict
                _s = xres.verification.overall_score
                if _v == "pass":
                    st.success(f"✅ 검증 완료 (score {_s:.0f}/100)")
                elif _v == "warn":
                    st.warning(f"⚠️ 검증 결과 주의 (score {_s:.0f}/100)")
                elif _v == "fail":
                    st.error(f"❌ 답변 신뢰도 부족 (score {_s:.0f}/100)")
                else:
                    st.error("🔥 검증 시스템 오류")
                # [PR-Fix-Render-Final] re-enabled — safety net 은 spinner 안이라 collapsed. spinner-외부 호출 필요.
                _vc_html = ""
                try:
                    _vc_html = _build_structured_card_html(_slim_structured(getattr(xres, "structured_answer", None)))
                except Exception:
                    _vc_html = ""
                if _vc_html:
                    answer_placeholder.markdown(_vc_html, unsafe_allow_html=True)
                else:
                    answer_placeholder.markdown(xres.rendered_markdown)
                with st.expander(
                    f"🔬 상세 검증 정보 "
                    f"(⏱️ 전체 {xres.elapsed_total_ms}ms / Gemini {xres.elapsed_gemini_ms}ms / "
                    f"classifier `{xres.classifier_source}` / golden `{xres.golden_source}`)"
                ):
                    if xres.verification.coverage_gaps:
                        st.markdown("**Coverage gaps:**")
                        for gap in xres.verification.coverage_gaps:
                            emoji = (
                                "🔴" if gap.severity == "HIGH"
                                else "🟡" if gap.severity == "MEDIUM"
                                else "🟢"
                            )
                            st.markdown(f"{emoji} [{gap.severity}] {gap.topic}")
                    if xres.verification.hallucinated_details:
                        st.markdown("**Hallucinated:**")
                        for h in xres.verification.hallucinated_details:
                            st.markdown(f"- {h.reason}: {h.claim.text[:80]}")
                    st.markdown(f"**Incident nodes:** `{xres.incident_nodes}`")
                progress_placeholder.markdown(
                    "<div style='height:0;overflow:hidden'></div>",
                    unsafe_allow_html=True,
                )
                progress_bar.empty()
                # === [PR-Fix-History-Push] X+ 답변을 session_state["history"] 에 push ===
                # X+ 분기는 ans 객체를 만들지 않아 함수 끝의 _push_history (line 2560)
                # 도달 불가. push 누락 시 rerun 후 history iterate (main() line 2864)
                # 가 user 메시지만 그려 assistant chat_message 가 사라짐 → UI 빈 영역.
                # ask_stream·verified_ask 패턴 정렬. xres 필드를 ans 구조로 매핑.
                _push_history((
                    "assistant", xres.rendered_markdown,
                    {
                        "contexts": xres.chunks,
                        "critical": False,
                        "kind": None,
                        "thinking": "",
                        "elapsed": xres.elapsed_total_ms / 1000.0,
                        "query_log_id": None,
                        "original_q": q,
                        "confidence": "high",
                        "structured": _slim_structured(getattr(xres, "structured_answer", None)),
                    },
                ))
                # === [PR-Fix-History-Push] 끝 ===
                return
            except Exception as _xerr:
                import sys as _xsys
                import traceback as _xtb
                print(
                    f"[_run_ask:X+:EXCEPT] {type(_xerr).__name__}: {_xerr}",
                    file=_xsys.stderr, flush=True,
                )
                print(_xtb.format_exc(), file=_xsys.stderr, flush=True)
                # 마지막 안전망 — except 안에서도 답변 박기 시도 (xres 가 except 진입 전에 만들어졌다면)
                try:
                    if 'xres' in dir() and xres is not None:
                        _emd = getattr(xres, 'rendered_markdown', None)
                        if isinstance(_emd, str) and _emd.strip():
                            import streamlit as _est
                            _est.markdown(_emd)
                            print(f"[_run_ask:X+:EXCEPT] recovered render via st.markdown", file=_xsys.stderr, flush=True)
                except Exception:
                    pass

        # ─────────────────────────────────────────────────
        # Phase 4 (PR #98): verified_ask 분기 (feature flag).
        # CHATBOT_USE_VERIFIED_ASK=True 시 Gemini 답변 + Claude judge 검증
        # 통합 흐름. block-until-verified — 컴플라이언스 신뢰성 우선.
        # 기본 False — 기존 streaming UX 보존, regression 위험 zero.
        # ─────────────────────────────────────────────────
        _s_phase4 = settings()
        if getattr(_s_phase4, "chatbot_use_verified_ask", False):
            print("[_run_ask] verified_ask branch entered", file=sys.stderr, flush=True)
            try:
                from core.orchestration.verified_ask import verified_ask
                with st.spinner("🔄 답변 생성 + 검증 중... (약 30~60초 소요)"):
                    progress_bar.progress(0.3, text="Gemini 답변 생성 중...")
                    verified = verified_ask(
                        sb, effective_q,
                        category=(cat if cat and cat != "전체" else None),
                        audit_source="live_chat",
                    )
                    progress_bar.progress(1.0, text="✅ 검증 완료")
                if verified.verdict == "pass":
                    st.success(
                        f"✅ 검증 완료 (score {verified.score:.0f}/100)"
                    )
                elif verified.verdict == "warn":
                    st.warning(
                        f"⚠️ 검증 결과 주의 (score {verified.score:.0f}/100)"
                    )
                elif verified.verdict == "fail":
                    st.error("❌ 검증 실패 — 관할 부서 확인 권장")
                else:
                    st.error("🔥 검증 시스템 오류 — 답변 사용 시 주의")
                answer_placeholder.markdown(verified.text)
                with st.expander(
                    f"🔬 상세 검증 결과 "
                    f"(⏱️ Gemini {verified.elapsed_gemini_ms}ms / "
                    f"Claude {verified.elapsed_claude_ms}ms / "
                    f"전체 {verified.elapsed_total_ms}ms)"
                ):
                    from core.verification.reports import render_report_markdown
                    st.markdown(render_report_markdown(verified.report))
                # progress placeholder 정리.
                progress_placeholder.markdown(
                    "<div style='height:0;overflow:hidden'></div>",
                    unsafe_allow_html=True,
                )
                progress_bar.empty()
                return
            except Exception as _verr:
                # verified_ask 실패 시 — 기존 streaming 으로 fallback.
                import sys as _vsys
                print(
                    f"[app:_run_ask] verified_ask failed, fallback to ask_stream: "
                    f"{type(_verr).__name__}: {_verr}",
                    file=_vsys.stderr, flush=True,
                )

        print(
            "[_run_ask] fallback ask_stream branch entered",
            file=sys.stderr, flush=True,
        )
        stream_buffer = ""
        for attempt in range(3):
            try:
                if attempt > 0:
                    sb = _supabase()
                    # retry 시 부분 stream 표시 폐기 — 새 시도가 처음부터 점진 표시
                    stream_buffer = ""
                    answer_placeholder.empty()
                # 첫 시도만 callback 활성화 — retry 는 silent 로 단계 메시지
                # 중복 표시 방지. retry 경로는 그대로 두되 사용자에게는
                # 자연스럽게 한 번의 흐름으로 보이게 한다.
                cb = _on_progress if attempt == 0 else None
                # streaming 답변 — ask_stream 가 ("chunk", str) / ("done",
                # Answer) yield. critical / injection / stream 예외 시
                # 내부에서 ask() 동기 위임 → ("done", Answer) 단일 yield.
                # PR-Fun3a: write_stream 으로 갈아탐 — placeholder.markdown
                # per chunk (DOM 전체 교체) → write_stream 의 native append
                # streaming. claude.ai 스타일 token 매끄러움 확보. 튜플 yield
                # 형태는 _chunks_to_str_stream wrapper 가 str 만 추출하면서
                # ("done", Answer) 의 ans 를 closure dict 로 보존.
                _stream_holder: dict = {"ans": None}
                _stream_iter = ask_stream(
                    sb,
                    question=effective_q,
                    category=cat,
                    progress_callback=cb,
                    prev_turn=prev_turn,
                    hard_category=hard_category,
                )
                stream_buffer = answer_placeholder.write_stream(
                    _chunks_to_str_stream(_stream_iter, _stream_holder)
                ) or ""
                ans = _stream_holder["ans"]
                break
            except Exception as e:
                last_err = e
                tb_str = traceback.format_exc()
                print(f"\n=== ASK ERROR (attempt {attempt}) ===\n{tb_str}", file=sys.stderr, flush=True)
                if "client has been closed" in str(e).lower() and attempt < 2:
                    continue
                break

        # progress placeholder + bar 정리 — 답변 본문 final 표시 _전_에 비움.
        # 에러 분기는 아래 if ans is None 에서도 한 번 더 안전망.
        # PR-Fun3a 페이즈 2: empty() 직접 호출 시 container 가 즉시 사라져
        # scroll jump 가 일어남 → 0-height div 로 교체해 layout 보존 (시각적
        # 으로는 동일하게 사라짐). 에러 분기는 그대로 empty() 유지 (에러
        # 메시지가 자리 차지).
        progress_placeholder.markdown(
            "<div style='height:0;overflow:hidden'></div>",
            unsafe_allow_html=True,
        )
        progress_bar.empty()

        print(
            f"[_run_ask] post-stream ans_present={ans is not None} "
            f"buffer_len={len(stream_buffer or '')} "
            f"ans_text_len={len(getattr(ans, 'text', '') or '') if ans else 0}",
            file=sys.stderr, flush=True,
        )

        if ans is None:
            # 부분 stream 잔재 정리 — 에러 메시지로 깔끔히 대체
            answer_placeholder.empty()
            # Timer 도 정리 — 카운터가 에러 후에도 계속 증가하면 부적절
            timer_placeholder.empty()
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
            elif (
                "503" in err_text or "UNAVAILABLE" in err_text
                or "429" in err_text or "RESOURCE_EXHAUSTED" in err_text
                or "high demand" in err_text.lower()
            ):
                friendly_msg = (
                    "⏳ Gemini 모델이 일시적으로 트래픽 폭주 상태입니다 (HTTP 503 / 429).\n\n"
                    "**잠시 후 같은 질문을 다시 시도해 주세요.** "
                    "수 분 내 자동 회복되는 일시 장애로, 코드/설정 문제가 아닙니다."
                )
            else:
                friendly_msg = "⚠️ 일시적인 오류가 발생했습니다. 잠시 후 다시 시도해 주세요."
            st.markdown(friendly_msg)
            with st.expander("🔧 기술 세부정보 (관리자용)", expanded=False):
                st.code(tb_str or str(last_err) or "(no traceback)", language="python")
        else:
            s = settings()
            # PR-Ambiguity-Askback: 모호성 역질문 — 본문 + 선택지 버튼만 렌더,
            # 일반 chrome(카테고리/신뢰도 chip·contexts·suggestions·액션·피드백)
            # 생략. 선택지 클릭 → clicked_q 재질의 → 정상 RAG (loop 없음).
            if getattr(ans, "clarify_choices", None):
                answer_placeholder.markdown(ans.text)
                timer_placeholder.empty()  # PR-Ambiguity-Askback-Fix: 라이브 카운터 정지(역질문은 즉시 반환)
                _ab_idx = len(st.session_state["history"])
                _render_clarify_choices(
                    ans.clarify_choices,
                    msg_idx=_ab_idx,
                    masked_question=getattr(ans, "masked_question", None),
                )
                _push_history((
                    "assistant", ans.text,
                    {"contexts": [], "critical": False, "kind": None,
                     "thinking": "", "elapsed": getattr(ans, "elapsed", 0.0),
                     "query_log_id": None, "original_q": q,
                     "confidence": "high", "suggestions": [],
                     "masked_question": getattr(ans, "masked_question", None),
                     "clarify_choices": list(ans.clarify_choices)},
                ))
                return
            if ans.thinking:
                with st.expander("🧠 AI 검토 과정", expanded=False):
                    st.caption("AI가 답변을 생성한 검토 단계입니다. 답변 신뢰도 판단에 참고하세요.")
                    st.markdown(ans.thinking)
            if ans.is_critical:
                _render_critical_banner()
            # 후처리(_ensure_citation/_normalize_citation_block) 적용된 final
            # 로 placeholder 단일 update — 커서 ▎ 제거 + [참조:] 정규화 반영.
            # critical / fallback 케이스는 placeholder 가 비어있어 한 번에 표시.
            answer_placeholder.markdown(ans.text)
            # ── [Verdict Stage 1] Shadow: 로그만, UI 무영향 ──
            if _ENABLE_VERDICT_SHADOW:
                try:
                    from core.synthesis.verdict_extractor import extract_verdict
                    _v = extract_verdict(effective_q, ans.text, list(getattr(ans, "contexts", []) or []))
                    if _v is not None and getattr(_v, "stance", ""):
                        _verdict_dict = _v.to_dict()
                        _hdr_ph.markdown(_build_verdict_card_html(_verdict_dict), unsafe_allow_html=True)
                except Exception:
                    _verdict_dict = None
            # PR-Coding-Policy-Defense: retrieval/LLM critical path 에서 silent
            # 처리된 내부 오류를 운영자에게 가시화 (접힌 expander). chunk_incident_nodes
            # 같은 스키마 오류가 force-include 를 무력화한 사고 재발 조기 감지.
            _critical_errs = st.session_state.pop("_critical_errors", None)
            if _critical_errs:
                with st.expander(
                    f"⚠️ Internal warnings ({len(_critical_errs)})", expanded=False
                ):
                    for _err in _critical_errs:
                        st.code(_err, language="text")
            # PR-Fun1 작업 4: 카테고리 chip — 답변 본문 직후, confidence chip 위.
            # critical 답변에도 표시 (사용자 정보 제공).
            # PR-Fix-Category-Citation-Based: ans.text 전달 → 인용 prefix 기반 결정.
            _render_category_chip(ans.contexts, answer_text=ans.text)
            # PR-C1: 신뢰도 chip — 답변 본문 직후, contexts 펼침 직전.
            _render_confidence_chip(ans.confidence, ans.contexts, answer_text=ans.text)
            # PR-Phase-18.7 H2: timer_placeholder 에 직접 meta 를 덮어써
            # 라이브 카운터 → 정적 meta 가 "같은 자리"에서 단일 갱신.
            # 별도 .empty() 호출 불필요 (markdown 이 placeholder 내용을 교체).
            _render_answer_meta(
                elapsed=ans.elapsed,
                model=s.chat_model,
                container=timer_placeholder,
            )
            _render_contexts(ans.contexts)
            # PR-Fun1 작업 3: 후속 질문 카드 (critical 시 비활성).
            # PR-Fun1.4 작업 7 + PR-Fun1.6: ans_id 우선, masked_question
            # hash fallback 으로 button key 안정화 (RLS RETURNING None 대비).
            _render_suggestion_cards(
                getattr(ans, "suggestions", []) or [],
                is_critical=ans.is_critical,
                msg_idx=len(st.session_state["history"]),
                ans_id=getattr(ans, "query_log_id", None),
                masked_question=getattr(ans, "masked_question", None),
                source_category=_domain_from_contexts(ans.contexts),
            )
            # PR-Fun1 작업 5: 랜덤 격려 멘트 (critical 시 critical_pool).
            _render_closing_remark(
                ans.is_critical,
                msg_idx=len(st.session_state["history"]),
            )
            # 액션 버튼 (📞 인사교육팀 문의 / 🔄 다시 답변) — 답변 본문 직후, 피드백 위.
            # msg_idx 는 곧 push 될 assistant 엔트리의 인덱스 (= 현재 history 길이).
            # original_q: reroll 모드면 reroll_of 의 원 질문, 정상이면 직전 user 메시지(q).
            _action_msg_idx = len(st.session_state["history"])
            _action_orig_q = (reroll_of["original_q"]
                              if reroll_of is not None else q)
            _render_action_buttons(
                _action_msg_idx,
                original_q=_action_orig_q,
                prev_answer=ans.text,
                hotlines=hotlines,
                contexts=ans.contexts,
                answer_text=ans.text,
                is_critical=ans.is_critical,
                confidence=ans.confidence,
            )
            # 피드백 UI — 답변마다 고유 인덱스로 위젯 키 분리.
            # PR-Fun1.5: query_log_id None 일 때 masked_question 으로
            # fallback 매칭 (RLS RETURNING 차단 우회).
            _render_feedback(
                sb, msg_idx=_action_msg_idx,
                query_log_id=ans.query_log_id,
                masked_question=getattr(ans, "masked_question", None),
            )

    # original_q: history replay 시 액션 버튼(다시 답변)이 원 질문을 복원하는
    # 데 필요. reroll 모드면 최초 질문, 정상 모드면 사용자 입력 q.
    _saved_orig_q = (reroll_of["original_q"] if reroll_of is not None else q)
    if ans is None:
        _push_history((
            "assistant", friendly_msg,
            {"contexts": [], "critical": False, "kind": None, "thinking": "",
             "elapsed": 0.0, "original_q": _saved_orig_q},
        ))
        return

    # PR-2.5: reroll 시 query_logs.query_masked 에 _REROLL_PREFIX 가 mask_pii
    # 거쳐 그대로 박힘 (core/chatbot.ask_stream 가 effective_q 를 직접 저장).
    # core/ 시그니처 무수정 제약상 호출 측에서 사후 UPDATE 로 보정. select 후
    # marker("원 질문: ") 기준으로 split → mask_pii 가 prefix 본문 일부를
    # 마스킹해도 marker 자체는 보존되므로 안전. 실패해도 답변 흐름 무방해.
    if reroll_of is not None and ans.query_log_id is not None:
        try:
            cur = sb.table("query_logs").select("query_masked")\
                .eq("id", ans.query_log_id).execute()
            masked_raw = (cur.data[0].get("query_masked") if cur.data else "") or ""
            marker = "원 질문: "
            mark_idx = masked_raw.find(marker)
            cleaned = (masked_raw[mark_idx + len(marker):].strip()
                       if mark_idx >= 0 else masked_raw)
            sb.table("query_logs").update({
                "query_masked": cleaned,
                "is_reroll":    True,
            }).eq("id", ans.query_log_id).execute()
        except Exception as e:
            import sys
            print(f"[PR-2.5 reroll fixup failed] id={ans.query_log_id} err={e}",
                  file=sys.stderr, flush=True)

    _push_history((
        "assistant", ans.text,
        {
            "contexts": ans.contexts,
            "critical": ans.is_critical,
            "kind": ans.critical_kind,
            "thinking": ans.thinking,
            "elapsed": ans.elapsed,
            "query_log_id": ans.query_log_id,
            "original_q": _saved_orig_q,
            "confidence": getattr(ans, "confidence", "high"),
            "verdict": _verdict_dict,
            "suggestions": list(getattr(ans, "suggestions", []) or []),
            # PR-Fun1.5: query_log_id None (RLS RETURNING 차단) 시 피드백
            # update fallback 매칭 식별자.
            "masked_question": getattr(ans, "masked_question", None),
        },
    ))

    # 멀티 턴 모드 버튼 — 정상 답변 한정. 에러 흐름(line 1164-1169)에서는
    # 호출하지 않음(이전 답변이 에러인 메시지에 "관련 질문" 노출은 무의미).
    msg_idx = len(st.session_state["history"]) - 1
    _render_mode_buttons(msg_idx)


_CONSENT_BODY_MD = """
**본 챗봇은 베타 테스트 중이며, 정보처리자가 회사가 아닌 개별 운영자입니다.**
정식 OPEN 시 회사 GCP(Vertex AI) + 회사 Supabase 로 이관 예정이며,
그 시점부터 회사가 정보처리자가 됩니다.

참가자께서는 아래 내용을 확인·동의하신 뒤 베타 테스트에 참여해 주시기 바랍니다.

1. **데이터 흐름**
   - 입력하신 질의는 `[익명]` 마스킹 후 외부 LLM API로 전송되어 답변이 생성됩니다.
   - 사용 LLM (베타 단계):
     - 주(主) 모델: Google Gemini API (유료 티어)
     - 보조 모델: Anthropic Claude API (Gemini API 일시 장애 시 자동 우회)
   - **두 API 모두 약관상 입력·출력이 모델 학습에 사용되지 않습니다.**
     - Gemini 유료 티어: Google API 약관에 따라 학습 제외
     - Claude API: Anthropic Commercial Terms 에 따라 학습 제외
   - 다만 양사는 **이용약관 위반 모니터링(Trust & Safety) 목적**으로 입력·
     출력을 단기간 보관할 수 있습니다 (Anthropic 기본 최대 30일, Google
     정책 동일 수준). **이 보관은 모델 학습과 무관**하며 보관 기간 종료
     시 자동 폐기됩니다. 정식 운영 이관 시점에는 회사 명의로 **Zero Data
     Retention(보관 0일) 계약** 적용을 검토합니다.
   - 마스킹 후 본문·검색 hit 만 Supabase 에 저장되며, 원본 질의는 즉시 폐기됩니다.

2. **인프라 주체 (베타 한정)**
   - Supabase 프로젝트 / Gemini · Claude API 키 모두 **개별 운영자(개인)** 명의입니다.
   - 회사-Google 간 DPA(데이터 처리 계약) 및 회사 차원의 처리방침 고지는
     **정식 OPEN 후** 적용됩니다.
   - 베타 단계의 로그(`query_logs`)는 회사 계정 이관 시 **이관하지 않고 폐기**됩니다.

3. **답변 한계**
   - 본 챗봇은 사규 해석 보조 도구이며 **법적 효력이 없습니다.**
   - 신고·조사 사항은 CSR팀 또는 신세계면세점 핫라인으로 접수해 주시기 바랍니다.
   - 인사 규정·복리후생 등 인사 행정 사항은 인사교육팀에 문의해 주시기 바랍니다.
   - 핫라인 URL 일부는 placeholder 상태일 수 있습니다.

4. **수집 정보**
   - 본 동의 화면에서 입력하신 **성명·사번**은 동의 기록 목적으로만 보관됩니다.
   - 베타 종료 시 동의 기록도 함께 폐기됩니다.

5. **철회**
   - 동의 후에도 운영자(`ADMIN`)에게 요청하시면 본인 동의 기록 및 질의 로그를 삭제할 수 있습니다.
"""


def _record_consent(sb, *, name: str, emp_no: str, version: str, env: str,
                    ) -> tuple[bool, str | None]:
    """Returns (success, error_message). 사번은 별도 컬럼(participant_emp_no)
    에 저장 — 기존 'name / emp_no' 단일 문자열 파싱 깨짐 위험 제거.
    db/07 미적용 환경 호환을 위해 participant_emp_no 컬럼 미존재 시 details
    에만 저장하는 fallback 포함."""
    name = (name or "").strip()
    emp_no = (emp_no or "").strip()
    payload: dict = {
        "participant":     name,
        "consent_version": version,
        "env":             env,
        "details":         {"emp_no": emp_no or None},
    }
    if emp_no:
        payload["participant_emp_no"] = emp_no
    try:
        sb.table("beta_consents").insert(payload).execute()
        return True, None
    except Exception as e:
        msg = str(e)
        # participant_emp_no 컬럼 부재 (db/07 미적용) — 컬럼 빼고 재시도
        if "participant_emp_no" in msg:
            payload.pop("participant_emp_no", None)
            try:
                sb.table("beta_consents").insert(payload).execute()
                return True, None
            except Exception as e2:
                return False, str(e2)
        return False, msg


def _consent_cookie_manager():
    """PR-Fun1.1 작업 1-B: extra-streamlit-components 의 CookieManager.

    PR-Fun1.1 hotfix2: @st.cache_resource 제거. CookieManager 는 streamlit
    component (widget) 을 등록하므로 cached function 안에서 호출 시
    CachedWidgetWarning 발생. 동일 key 로 매 rerun 마다 호출해도
    component 가 reuse 되므로 캐시 불필요.

    cookie 동기화는 첫 cycle 에 None 일 수 있으므로 호출 측이 None 대비.
    다음 cycle 에 정상 dict.
    """
    import extra_streamlit_components as stx
    return stx.CookieManager(key="df_compass_consent_cookie_mgr")


_CONSENT_COOKIE_NAME = "df_compass_consent_v"


def _consent_gate(sb) -> bool:
    """베타 환경에서 동의 미완료 시 동의 화면을 렌더하고 False 반환.
    호출자는 False 면 st.stop() 으로 본 화면 렌더를 차단해야 한다.
    운영(`NEXUS_ENV=prod*`)에서는 항상 True (게이트 비활성).

    PR-Fun1.1 hotfix3: form_placeholder.empty() 패턴 폐기.
      - 동의 통과 검증을 form 렌더링 _위_ 에서 분기 — 동의 후엔 form 코드
        자체가 실행되지 않음.
      - cookie set 은 submit cycle 에서 직접 호출하지 않고 session_state 의
        pending flag 로 다음 cycle 에 미룸. cm.set() 의 component frame 이
        메인 UI 와 함께 그려져 cookie 실제 set + form 잔재 0.
    """
    s = settings()
    if not (s.env_tag or "").startswith("beta"):
        return True

    cur_ver = s.consent_version
    cm = _consent_cookie_manager()

    # PR-Fun1.1 hotfix3: pending cookie set 처리 — 직전 submit 의 deferred
    # cookie set 을 본 cycle 에서 실행. cm.set() 의 streamlit component 가
    # 본 cycle 의 frame 에 그려져 JS 가 실제 cookie 를 저장한다.
    _pending = st.session_state.pop("_pending_consent_cookie", None)
    if _pending:
        try:
            from datetime import datetime as _dt, timedelta as _td
            cm.set(
                _CONSENT_COOKIE_NAME, _pending,
                expires_at=_dt.now() + _td(days=30),
                key="set_consent_cookie",
            )
        except Exception:
            pass

    # 분기 1: 같은 session 통과
    if st.session_state.get("beta_consent_v") == cur_ver:
        return True

    # 분기 2: cookie 30일 영속 통과
    try:
        cookies = cm.get_all() or {}
    except Exception:
        cookies = {}
    if cookies.get(_CONSENT_COOKIE_NAME) == cur_ver:
        st.session_state["beta_consent_v"] = cur_ver
        return True

    # 여기 도달 = 동의 미완. form 직접 그리기 (placeholder 패턴 폐기).
    st.markdown('<div class="nx-topbar"></div>', unsafe_allow_html=True)
    st.markdown(
        """
        <div class="nx-hero" style="margin-bottom:24px">
          <p class="nx-hero-eyebrow">BETA · 사전 동의</p>
          <h1 class="nx-hero-title">베타 참가 동의서</h1>
          <p class="nx-hero-sub">
            본 환경은 정식 OPEN 전 베타 테스트입니다.
            아래 내용을 확인하시고 동의해 주신 분께만 베타 챗봇이 활성화됩니다.
          </p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown(_CONSENT_BODY_MD)
    st.markdown("---")

    # PR-Fun1.4 작업 1: st.form / st.form_submit_button 폐기. form widget
    # 의 streamlit quirk (rerun 사이 잔재) 가 동의 sub-section 잔재 issue
    # 의 root cause. 단순 input + checkbox + button 패턴으로 전환.
    c1, c2 = st.columns(2)
    with c1:
        name = st.text_input("성명 *", value="", key="consent_name_input")
    with c2:
        emp_no = st.text_input("사번 (선택)", value="", key="consent_emp_no_input")
    agree = st.checkbox(
        "위 내용을 모두 읽고 베타 참가에 동의합니다.",
        key="consent_agree_input",
    )
    submitted = st.button("동의하고 시작", type="primary", key="consent_submit_btn")

    if submitted:
        # 입력 검증 — stored XSS / SQL 페이로드 차단 + 형식 강제.
        # name: 한글/영문/공백 1~50자, emp_no: 숫자/하이픈 4~12자(선택)
        import re as _re
        _RE_NAME = _re.compile(r"^[가-힣A-Za-z\s]{1,50}$")
        _RE_EMPNO = _re.compile(r"^[0-9-]{4,12}$")
        if not name.strip():
            st.error("성명을 입력해 주세요.")
        elif not _RE_NAME.match(name.strip()):
            st.error("성명은 한글·영문·공백만 사용해 주세요 (1~50자).")
        elif emp_no.strip() and not _RE_EMPNO.match(emp_no.strip()):
            st.error("사번은 숫자 4~12자 (하이픈 허용) 형식이어야 합니다.")
        elif not agree:
            st.error("동의 체크박스를 선택해 주세요.")
        else:
            ok, err = _record_consent(
                sb,
                name=name,
                emp_no=emp_no,
                version=cur_ver,
                env=s.env_tag,
            )
            participant = name.strip() + (f" / {emp_no.strip()}" if emp_no.strip() else "")
            if not ok:
                # INSERT 실패는 RLS/grants/스키마 캐시 문제. 사용자에게 즉시
                # 노출하고 게이트 통과 시키지 않음 — 동의 미기록 상태로
                # 챗봇이 열리는 거버넌스 사고 방지.
                st.error(
                    "⚠️ 동의 기록 저장에 실패했습니다. 운영자에게 다음 메시지를 전달해 주세요.\n\n"
                    "Supabase 콘솔에서 다음을 실행:\n"
                    "`alter table beta_consents disable row level security;`\n"
                    "`grant insert, select on beta_consents to anon, authenticated;`\n"
                    "`grant usage, select on sequence beta_consents_id_seq to anon, authenticated;`\n"
                    "`notify pgrst, 'reload schema';`"
                )
                with st.expander("기술 세부정보", expanded=False):
                    st.code(err or "(no detail)")
            else:
                # PR-Fun1.1 hotfix3: cookie set 은 다음 cycle 로 deferred —
                # cm.set() 의 component frame 이 form 과 같은 cycle 에 그려져
                # disabled-looking 잔재를 만들던 issue 해결.
                st.session_state["beta_consent_v"] = cur_ver
                st.session_state["beta_consent_participant"] = participant
                st.session_state["_pending_consent_cookie"] = cur_ver
                st.rerun()

    return False


def main():
    st.markdown(_CSS, unsafe_allow_html=True)
    # 4px top frame line
    st.markdown('<div class="nx-topbar"></div>', unsafe_allow_html=True)

    # Boot-time secrets validation — 누락·이상값을 부팅 직후 가시화.
    # INFO: 로 시작하는 항목은 차단하지 않고 caption 으로만 노출 (예: Claude 키 미설정).
    issues = validate_settings()
    blockers = [i for i in issues if not i.startswith("INFO:")]
    infos    = [i for i in issues if i.startswith("INFO:")]
    if blockers:
        st.error(
            "⚠️ 환경 설정 문제로 앱을 시작할 수 없습니다:\n\n"
            + "\n".join(f"- {b}" for b in blockers)
        )
        st.stop()
    if infos:
        with st.expander("⚙ 환경 설정 정보 (참조)", expanded=False):
            for i in infos:
                st.caption(i)

    sb = _supabase()
    if sb is None:
        st.error("Supabase 설정이 없습니다. SUPABASE_URL / SUPABASE_KEY 를 secrets에 추가하세요.")
        st.stop()

    # PR-Coding-Policy-Defense: DB schema self-check (session 당 1회).
    if not st.session_state.get("_schema_checked"):
        _validate_db_schema(sb)
        st.session_state["_schema_checked"] = True

    if not _consent_gate(sb):
        st.stop()

    if "history" not in st.session_state:
        st.session_state["history"] = []
        st.session_state["_chat_active"] = False

    hotlines = load_hotlines(sb)
    cat = _sidebar(sb, hotlines)

    _render_beta_banner()

    # PR-Fun1.2 hotfix: PR-Fun1.1 의 pending_q early exit 폐기. early exit
    # 의 return 이 main() 의 chat_input 영역까지 도달 못 하게 해서 답변 후
    # chat_input 자체가 안 그려졌다 (사용자 다음 질문 불가). 원래 흐름
    # (chat_input 또는 pending_q 둘 중 하나 채워지면 _run_ask) 복구.

    # chat_input 을 먼저 호출(하단 sticky) → 첫 질문이 하단 입력으로 와도
    # 빈 홈이 답변과 동시에 렌더되지 않도록 게이트에 q_input 반영.
    q_input = st.chat_input("질문을 입력하세요…", max_chars=2000)
    # PR-Fun1.4: hero 는 history 비어있고 진행 중 질문(clicked_q·q_input) 없을 때만.
    # 빈 홈을 placeholder 에 렌더 → 같은 run 에서 질문이 처리되면 _home_ph.empty()
    # 로 즉시 제거. chip 의 st.rerun() 이 run 을 못 끊는 경우에도 답변과 동시
    # 노출되지 않게 하는 구조 가드 (게이트로 못 막던 single-run co-render 해결).
    _home_ph = st.empty()
    if (not st.session_state.get("history")
            and not st.session_state.get("clicked_q")
            and not q_input
            and not st.session_state.get("_chat_active")):
        with _home_ph.container():
            _render_empty_state(sb)

    # Chat history replay — 최근 30 messages 만 렌더 (rerun 비용 제어).
    # 50건 넘어가면 매 입력 후 응답 표시까지 lag 발생 → 윈도우 30 권장.
    s = settings()
    _history = st.session_state["history"]
    _RENDER_WINDOW = 30
    if len(_history) > _RENDER_WINDOW:
        st.caption(f"⋯ 이전 {len(_history) - _RENDER_WINDOW}건은 표시 생략 (최근 {_RENDER_WINDOW}건만 표시)")
        _start = len(_history) - _RENDER_WINDOW
    else:
        _start = 0
    for idx, (role, content, meta) in enumerate(_history[_start:], start=_start):
        with st.chat_message(role, avatar=("🧭" if role == "assistant" else "👤")):
            if role == "assistant" and meta.get("thinking"):
                with st.expander("🧠 AI 검토 과정", expanded=False):
                    st.caption("AI가 답변을 생성한 검토 단계입니다. 답변 신뢰도 판단에 참고하세요.")
                    st.markdown(meta["thinking"])
            if role == "assistant" and meta.get("critical"):
                _render_critical_banner()
            _vc_html = ""
            if role == "assistant":
                try:
                    _vc_html = _build_structured_card_html(meta.get("structured"))
                except Exception:
                    _vc_html = ""
            if role == "assistant":
                _vd = meta.get("verdict")
                if _vd:
                    st.markdown(_build_verdict_card_html(_vd), unsafe_allow_html=True)
                else:
                    st.markdown(_answer_card_header_html(), unsafe_allow_html=True)
            if _vc_html:
                st.markdown(_vc_html, unsafe_allow_html=True)
            else:
                st.markdown(content)
            # PR-Ambiguity-Askback: 모호성 역질문 turn replay — 선택지 버튼만,
            # 일반 chrome 생략 (continue 로 이하 chip/contexts/suggestions/피드백 skip).
            if role == "assistant" and meta.get("clarify_choices"):
                _render_clarify_choices(
                    list(meta.get("clarify_choices") or []),
                    msg_idx=idx,
                    masked_question=meta.get("masked_question"),
                )
                continue
            # PR-Fun1 작업 4: 카테고리 chip — replay 시 contexts 있으면 표시.
            # PR-Fix-Category-Citation-Based: content (답변 본문) 전달 → 인용 prefix 기반 결정.
            if role == "assistant" and meta.get("contexts"):
                _render_category_chip(meta["contexts"], answer_text=content)
            # PR-C1: history replay 에도 chip 노출. 기존 entry (confidence 키 없음)
            # 는 'high' default 로 회귀 안전.
            # PR-Phase-18.7: query_log_id != None 가드 제거 — confidence 는
            # query_log_id 와 독립 정보. RLS RETURNING 차단으로 query_log_id 가
            # None 인 응답에도 chip 표시해 사용자 정보 일관성 ↑.
            if role == "assistant":
                _render_confidence_chip(
                    meta.get("confidence", "high"),
                    meta.get("contexts"),
                    answer_text=content,
                )
            # PR-Answer-Meta-Visibility: history replay 에도 응답 시간 + 모델명 표시.
            # 기존 entry (elapsed=0 또는 미저장) 는 함수 내부 가드로 표시 안 함.
            if role == "assistant":
                _render_answer_meta(
                    elapsed=meta.get("elapsed", 0.0),
                    model=s.chat_model,
                )
            if role == "assistant" and meta.get("contexts"):
                _render_contexts(meta["contexts"])
            # PR-Fun1 작업 3·5: suggestions 카드 + 격려 멘트 (replay).
            # PR-Fun1.6: query_log_id 가드 제거 — RLS RETURNING 차단으로
            # query_log_id 가 None 이어도 suggestions/closing 은 그려야 함.
            # 함수 내부 자체 가드 (suggestions 비어있으면 return).
            if role == "assistant":
                _render_suggestion_cards(
                    list(meta.get("suggestions") or []),
                    is_critical=bool(meta.get("critical")),
                    msg_idx=idx,
                    ans_id=meta.get("query_log_id"),
                    masked_question=meta.get("masked_question"),
                )
                _render_closing_remark(
                    bool(meta.get("critical")), msg_idx=idx,
                )
            # 액션 버튼 — 정상 답변(query_log_id 있음) 한정. 에러 답변은 다시
            # 답변 시 동일 에러 반복 가능성 + 인사교육팀 문의는 의미 없으므로 미노출.
            if (role == "assistant" and meta.get("query_log_id") is not None):
                _render_action_buttons(
                    idx,
                    original_q=meta.get("original_q"),
                    prev_answer=content,
                    hotlines=hotlines,
                    contexts=meta.get("contexts"),
                    answer_text=content,
                    is_critical=bool(meta.get("critical", False)),
                    confidence=meta.get("confidence"),
                )
            # PR-Fun1.5: history replay 도 query_log_id None 케이스 처리.
            # query_log_id 또는 masked_question 둘 중 하나라도 있으면 표시.
            if role == "assistant" and (
                meta.get("query_log_id") or meta.get("masked_question")
            ):
                _render_feedback(
                    sb, msg_idx=idx,
                    query_log_id=meta.get("query_log_id"),
                    masked_question=meta.get("masked_question"),
                )
            # 멀티 턴 모드 버튼 — 마지막 assistant 메시지 + 정상 답변 한정.
            # 중간 메시지나 에러 답변에 버튼 노출 시 disabled 노이즈 발생 → 차단.
            if (role == "assistant"
                    and idx == len(_history) - 1
                    and meta.get("query_log_id") is not None):
                _render_mode_buttons(idx)

    # PR-Fun1.5: pending_q 매개체 폐기. clicked_q 매개체는 main() 입구의
    # early exit 가 별도 처리. 여기엔 chat_input 만 처리.
    st.markdown(
        '<div style="text-align:center; color:#888; font-size:11px; '
        'padding:24px 0 8px 0; border-top:1px solid #eee; margin-top:32px;">'
        '© 2026 신세계디에프 (Shinsegae Duty Free) · 인사담당 CSR팀<br>'
        '본 답변은 사규 해석 보조 도구이며 법적 효력은 없습니다. '
        '인사·신고 행정 사항은 인사교육팀에 직접 문의하세요.'
        '</div>',
        unsafe_allow_html=True,
    )

    # PR-Fun1.3: chat_input widget 을 다른 분기 처리 _전_에 호출 —
    # _run_ask 호출 후 main() 가 일찍 종료되더라도 chat_input widget 이
    # 매 rerun 에 등록되도록 보장. streamlit chat_input 은 화면 하단
    # sticky 라 호출 위치와 무관하게 항상 동일 위치에 렌더된다.
    # max_chars=2000 — 사규 질문에 충분한 길이이며 메가바이트 페이로드 차단.
    # (q_input 은 빈 홈 게이트용으로 main 상단에서 미리 호출 — 여기서 재호출 금지)

    # PR-Fun1.5: SAMPLE_QUESTIONS chip / [SUGGESTIONS] 카드 click 의 매개체
    # session_state['clicked_q'] 처리. main 흐름 다른 분기보다 _먼저_ 처리
    # → carry-over issue 회피. _run_ask 후 st.rerun() 으로 다음 cycle 에
    # main() 정상 흐름 복귀 (chat_input widget early 호출로 등록 보장).
    _clicked = st.session_state.pop("clicked_q", None)
    _clicked_cat = st.session_state.pop("clicked_cat", None)
    _clicked_hard = st.session_state.pop("clicked_hard_cat", None)
    if _clicked:
        _home_ph.empty()  # 같은 run co-render 방지 — 답변 전 빈 홈 강제 제거
        _run_ask(sb, _clicked, _clicked_cat or cat, hotlines,
                 hard_category=_clicked_hard)
        st.rerun()

    # 🔄 다시 답변 — 액션 버튼 클릭 시 session_state 에 적재된 reroll request.
    # rerun 다음 사이클에 history replay 후 본 분기에서 ask_stream 재호출.
    # pop 으로 즉시 제거 — 동일 reroll 이 두 번 실행되는 일을 차단.
    pending = st.session_state.pop("_pending_reroll", None)
    if pending is not None:
        _run_ask(sb, q="", cat=cat, hotlines=hotlines, reroll_of=pending)
        return

    # chat_input 직접 입력만 처리 (clicked_q 는 위에서 처리).
    if not q_input:
        return

    _home_ph.empty()  # 같은 run co-render 방지 — 답변 전 빈 홈 강제 제거
    _run_ask(sb, q_input, cat, hotlines)


if __name__ == "__main__":
    main()
