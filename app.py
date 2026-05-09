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
  --c-primary:    #1A1A1A;   /* 본문/구조용 무채색 — 변경 없음 */
  --c-accent:     #C8102E;   /* 신세계 시그니처 레드 (액센트 전용) */
  --c-accent-dark:#9A0C24;   /* 호버 상태용 짙은 레드 */
  --c-accent-bg:  #FCEBEE;   /* 매우 옅은 핑크 — 배너/하이라이트 배경용 */
  --c-text:     #333333;
  --c-caption:  #767676;
  --c-muted:    #AEAEAE;
  --c-border:   #E0E0E0;
  --c-surface:  #F7F7F7;
  --c-bg:       #FFFFFF;
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


def _supabase():
    """매 스크립트 실행마다 새 클라이언트 생성. 캐시·session_state 어디에도 보관하지 않음.
    httpx 연결이 다른 사용자 세션에서 닫혀 공유 객체가 망가지는 문제를 원천 차단."""
    from supabase import create_client
    s = settings()
    if not s.supabase_url or not s.supabase_key:
        return None
    return create_client(s.supabase_url, s.supabase_key)


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

본 답변은 사규 해석 보조 도구이며 법적 효력은 없습니다. 인사 행정 사항은 인사팀에 직접 문의하세요.
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
            '인사 규정·복리후생 등 인사 행정 사항은 인사팀으로 문의해 주시기 바랍니다.'
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


def _render_confidence_chip(confidence: str) -> None:
    """PR-C1: 답변 본문 직후에 검색 신뢰도 chip 을 caption 톤으로 노출.

    confidence: 'high' | 'medium' | 'low'. 그 외 값은 표시 생략.
    본문(ans.text) 의 [참조: ...] / 종결 멘트(💬...) 과 시각적으로 분리되되
    눈에 띄는 회색 caption + 색상 점.
    """
    chip_map = {
        "high":   ("🟢", "높은 신뢰도", "#1f7a3a"),
        "medium": ("🟡", "보조 참고 — 정확한 사항은 인사팀 확인", "#a07020"),
        "low":    ("🔴", "검색 hit 부족 — 인사팀·CSR팀 확인 권장", "#a93226"),
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


def _render_category_chip(contexts: list[dict]) -> None:
    """PR-Fun1 작업 4: 답변 본문 직전에 카테고리 chip 한 줄 노출.

    contexts 가 비어있거나 카테고리 식별 불가면 표시 생략. 본문 헤더
    (📋 사규 기준 / ⚖️ 징계 기준 / 📂 사건사례) 는 LLM 출력 그대로 두고
    본 chip 만 카테고리별 색·아이콘으로 동적 변경 (가독성 유지).
    """
    if not contexts:
        return
    from core.personality import category_visual
    icon, color, label = category_visual(contexts)
    if not label:
        return
    st.markdown(
        f"<div style='font-size:12px;color:{color};padding:2px 0 4px;"
        f"font-family:-apple-system,Pretendard,sans-serif;'>"
        f"{icon} <strong style='color:{color};'>{label}</strong> 카테고리"
        f"</div>",
        unsafe_allow_html=True,
    )


def _render_suggestion_cards(
    suggestions: list[str], *, is_critical: bool, msg_idx: int,
) -> None:
    """PR-Fun1 작업 3: 답변 끝의 후속 질문 카드 3개.

    critical 답변에서는 카드 자체를 비활성 (핵심 회귀 방어). LLM prompt
    에서도 [Critical Mode 답변 가이드] 7번에 의해 [SUGGESTIONS] 블록이
    생성되지 않으나, 이중 방어로 UI 단도 차단.

    클릭 시 session_state['pending_q'] 로 query 적재 + rerun → main 의
    chat_input 처리부가 pop 해서 _run_ask 호출.
    """
    if is_critical or not suggestions:
        return
    st.markdown(
        "<div style='font-size:12px;color:#475569;padding:8px 0 4px;"
        "font-family:-apple-system,Pretendard,sans-serif;'>"
        "💡 <strong>이런 질문도 해볼 수 있어요</strong></div>",
        unsafe_allow_html=True,
    )
    cols = st.columns(min(3, len(suggestions)))
    for i, q in enumerate(suggestions[:3]):
        if cols[i].button(
            q, key=f"sugg_{msg_idx}_{i}", use_container_width=True,
        ):
            st.session_state["pending_q"] = q
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


def _render_empty_state(sb) -> None:
    """첫 진입 화면 — 동적 인사 + Daily Tip + 빠른 액션 카드.

    카드 클릭 시 session_state['pending_q'] 적재 + rerun. main 의
    chat_input 처리부가 pop 해서 _run_ask 호출.
    """
    from datetime import datetime as _dt
    now = _dt.now()
    greeting = _cached_dynamic_greeting(now.hour, now.weekday())

    with st.chat_message("assistant", avatar="🧭"):
        st.markdown(
            f"**DF COMPASS** · 신세계디에프 윤리·컴플라이언스 가이드\n\n"
            f"{greeting}\n\n"
            "💡 답변에는 항상 **출처 사규** 가 함께 표시됩니다."
        )

        # Daily Tip — 사규 random pick → LLM fun fact
        from core.personality import pick_random_doc_title
        doc_title = pick_random_doc_title(sb)
        tip_text = ""
        if doc_title:
            tip_text = _cached_daily_tip(now.date().isoformat(), doc_title)
        if doc_title and tip_text:
            # PR-Fun1.1 작업 2: column 분리 제거. col2 가 너무 좁아 button
            # 클릭 영역이 부족했던 issue 수정. 박스 + button 단일 row 로.
            st.markdown(
                f"<div style='background:#f8fafc;border-left:3px solid #94a3b8;"
                f"padding:8px 12px;margin:8px 0;border-radius:4px;"
                f"font-size:13px;'>"
                f"💡 <strong>오늘의 사규 한 입</strong> — {tip_text}<br>"
                f"<span style='color:#64748b;font-size:11px;'>"
                f"출처 후보: {doc_title}</span></div>",
                unsafe_allow_html=True,
            )
            if st.button(
                "👉 이 사규 알아보기",
                key="tip_explore",
                use_container_width=False,
            ):
                st.session_state["pending_q"] = f"{doc_title} 에 대해 알려주세요"
                st.rerun()

        st.markdown(
            "<div style='font-size:12px;color:#64748b;margin:12px 0 6px 0;'>"
            "빠른 시작 — 자주 묻는 카테고리</div>",
            unsafe_allow_html=True,
        )
        from core.personality import QUICK_ACTIONS
        cols = st.columns(len(QUICK_ACTIONS))
        for i, (icon, label, query) in enumerate(QUICK_ACTIONS):
            if cols[i].button(
                f"{icon} {label}", key=f"qa_{i}", use_container_width=True,
            ):
                st.session_state["pending_q"] = query
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


def _render_hr_inquiry_panel(hotlines: dict[str, str]) -> None:
    """인사팀 문의 안내 박스 — hotline_config 4개 키 매핑, 빈 값은 렌더 생략.
    DB 스키마 변경 없이 기존 키만 사용 (`hr_contact_text`, `hr_chatbot_url`,
    `internal_report_url`, `external_hotline`)."""
    hr_text = (hotlines.get("hr_contact_text") or "").strip()
    hr_chatbot = (hotlines.get("hr_chatbot_url") or "").strip()
    anon_url = (hotlines.get("internal_report_url") or "").strip()
    ext_hotline = (hotlines.get("external_hotline") or "").strip()
    with st.container(border=True):
        st.markdown("**📞 인사팀 문의 채널**")
        st.markdown(hr_text or "인사팀에 직접 문의하세요.")
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
            "⚠️ 본 답변은 사규 해석 보조이며, 인사 행정 결정은 인사팀 문의가 우선합니다."
        )


def _render_action_buttons(
    msg_idx: int,
    *,
    original_q: str | None,
    prev_answer: str | None,
    hotlines: dict[str, str],
) -> None:
    """답변 본문 직후 두 액션: [📞 인사팀 문의] [🔄 다시 답변].

    인사팀 문의 — toggle. session_state["hr_open"] set 으로 msg_idx 별 독립.
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
    hr_label = "📞 인사팀 문의 닫기" if msg_idx in hr_open else "📞 인사팀 문의"
    col_a, col_b = st.columns(2)
    hr_clicked = col_a.button(
        hr_label, key=f"hr_btn_{msg_idx}", use_container_width=True,
    )
    if can_reroll:
        reroll_clicked = col_b.button(
            "🔄 다시 답변",
            key=f"reroll_btn_{msg_idx}",
            use_container_width=True,
        )
    else:
        # disabled 인자를 쓰지 않고 markdown placeholder 로 회색 표기.
        # 이미 다시 답변 받았거나 history meta 가 누락된 fallback 메시지.
        col_b.markdown(
            "<div style='text-align:center; padding:8px 0; "
            "color:#aaa; font-size:14px; border:1px solid #eee; "
            "border-radius:4px; background:#fafafa;'>"
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
        _render_hr_inquiry_panel(hotlines)


def _record_feedback_click(sb, query_log_id: int, *, positive: bool) -> bool:
    """클릭 시점 즉시 기록 — feedback (기존 ±1, admin/radar 호환) +
    feedback_type (신규, 'positive'/'negative') + feedback_at 동시 갱신.

    db/04 의 feedback (smallint) 컨벤션은 -1/+1 (db/04_beta_hooks.sql:25).
    """
    import sys
    from datetime import datetime, timezone
    try:
        sb.table("query_logs").update({
            "feedback":      1 if positive else -1,
            "feedback_type": "positive" if positive else "negative",
            "feedback_at":   datetime.now(timezone.utc).isoformat(),
        }).eq("id", query_log_id).execute()
        return True
    except Exception as e:
        print(f"[fb click update failed] query_log_id={query_log_id} err={e}",
              file=sys.stderr, flush=True)
        return False


def _record_feedback_submit(sb, query_log_id: int, *,
                            reasons: list[str], comment: str | None) -> bool:
    """제출 시 reasons (jsonb 배열) + comment (기존 text) 추가 갱신.
    feedback_at 은 클릭 시점 그대로 둔다."""
    import sys
    try:
        payload: dict = {"feedback_reasons": reasons}
        if comment:
            payload["feedback_comment"] = comment[:500]
        sb.table("query_logs").update(payload).eq("id", query_log_id).execute()
        return True
    except Exception as e:
        print(f"[fb submit update failed] query_log_id={query_log_id} err={e}",
              file=sys.stderr, flush=True)
        return False


def _render_feedback(sb, msg_idx: int, query_log_id: int | None) -> None:
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
    """
    if not query_log_id:
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
        if pos_clicked:
            if _record_feedback_click(sb, query_log_id, positive=True):
                clicked[msg_idx] = "positive"
                st.rerun()
        if neg_clicked:
            if _record_feedback_click(sb, query_log_id, positive=False):
                clicked[msg_idx] = "negative"
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
        if _record_feedback_submit(sb, query_log_id,
                                   reasons=reasons or [], comment=comment):
            submitted.add(msg_idx)
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
    import sys
    import traceback
    if not _check_rate_limit():
        s = settings()
        with st.chat_message("assistant"):
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
        with st.chat_message("user"):
            st.markdown(q)

    ans = None
    last_err: Exception | None = None
    tb_str = ""
    friendly_msg = ""
    with st.chat_message("assistant"):
        # 답변 본문 placeholder — streaming 점진 표시 + 후처리 단일 update.
        # status 컨테이너보다 위쪽 영역에 자리 잡아 사용자는 처리 단계 메시지
        # 위에서 답변이 점진적으로 그려지는 걸 본다. status 종료(collapsed)
        # 후에도 placeholder 는 그대로 답변 본문을 유지.
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
  <span style="color:#999;">평균 약 {_avg_s}초</span>
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

        with st.status("문서 검색 및 답변 생성 중...", expanded=True) as status:
            # 진행 단계 표시 callback. ask() 가 emit("analyze") → ("search_start") →
            # ("search_done") → ("generate") → ("complete") 순으로 호출.
            # injection early-exit 분기에서는 callback 미호출(정상).
            def _on_progress(stage: str, payload: dict) -> None:
                if stage == "analyze":
                    st.write("🔍 질문을 분석하고 있어요...")
                elif stage == "search_start":
                    st.write("📚 관련 사규를 찾고 있어요...")
                elif stage == "search_done":
                    total = payload.get("total", 0)
                    if total == 0:
                        st.write("📋 검색 결과 없음 — 답변에 한계가 있을 수 있어요")
                        return
                    counts = payload.get("doc_kind_counts", {})
                    parts: list[str] = []
                    if counts.get("rule"):
                        parts.append(f"사규 {counts['rule']}건")
                    if counts.get("penalty"):
                        parts.append(f"징계기준 {counts['penalty']}건")
                    if counts.get("case"):
                        parts.append(f"사례 {counts['case']}건")
                    count_str = " · ".join(parts) if parts else f"{total}건"
                    # 중복 doc_title 제거 + 첫 3개 + 외 N건
                    seen: set[str] = set()
                    unique_titles: list[str] = []
                    for t in payload.get("doc_titles", []):
                        if t and t not in seen:
                            unique_titles.append(t)
                            seen.add(t)
                    shown = unique_titles[:3]
                    more = len(unique_titles) - len(shown)
                    title_str = ", ".join(shown)
                    if more > 0:
                        title_str += f" 외 {more}건"
                    st.write(f"📋 검색 완료 ({count_str}): {title_str}")
                elif stage == "generate":
                    st.write("🧠 답변을 작성하고 있어요...")
                # "complete" 는 status.update 가 처리하므로 별도 메시지 불필요

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
                    for kind, val in ask_stream(
                        sb,
                        question=effective_q,
                        category=cat,
                        progress_callback=cb,
                        prev_turn=prev_turn,
                    ):
                        if kind == "chunk":
                            stream_buffer += val
                            # 커서 ▎ 로 streaming 표시. answer_placeholder 가
                            # status 위쪽에 자리잡아 사용자가 답변 점진 그려짐을 본다.
                            answer_placeholder.markdown(stream_buffer + "▎")
                        elif kind == "done":
                            ans = val
                    break
                except Exception as e:
                    last_err = e
                    tb_str = traceback.format_exc()
                    print(f"\n=== ASK ERROR (attempt {attempt}) ===\n{tb_str}", file=sys.stderr, flush=True)
                    if "client has been closed" in str(e).lower() and attempt < 2:
                        continue
                    break

            # status 컨테이너 라벨 마무리 — 답변 본문은 status 밖에서 렌더링
            if ans is None:
                status.update(label="⚠️ 답변 생성 실패", state="error", expanded=True)
            else:
                status.update(label="🔍 처리 단계", state="complete", expanded=False)

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
            # PR-Fun1 작업 4: 카테고리 chip — 답변 본문 직후, confidence chip 위.
            # critical 답변에도 표시 (사용자 정보 제공).
            _render_category_chip(ans.contexts)
            # PR-C1: 신뢰도 chip — 답변 본문 직후, contexts 펼침 직전.
            _render_confidence_chip(ans.confidence)
            # Timer placeholder 를 정적 메시지로 교체 — JS 카운터 iframe 사라
            # 지면서 setInterval 도 자동 cleanup. ans.elapsed (서버 측 perf
            # counter) 가 사용자 wall-clock 보다 정확.
            timer_placeholder.markdown(
                "<div style='color:#888;font-size:12px;padding:6px 0;"
                "font-family:-apple-system,Pretendard,sans-serif;'>"
                f"⏱️ {ans.elapsed:.1f}초 만에 답변 완료</div>",
                unsafe_allow_html=True,
            )
            _render_contexts(ans.contexts)
            # PR-Fun1 작업 3: 후속 질문 카드 (critical 시 비활성).
            _render_suggestion_cards(
                getattr(ans, "suggestions", []) or [],
                is_critical=ans.is_critical,
                msg_idx=len(st.session_state["history"]),
            )
            # PR-Fun1 작업 5: 랜덤 격려 멘트 (critical 시 critical_pool).
            _render_closing_remark(
                ans.is_critical,
                msg_idx=len(st.session_state["history"]),
            )
            # 액션 버튼 (📞 인사팀 문의 / 🔄 다시 답변) — 답변 본문 직후, 피드백 위.
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
            )
            # 피드백 UI — 답변마다 고유 인덱스로 위젯 키 분리.
            _render_feedback(sb, msg_idx=_action_msg_idx,
                             query_log_id=ans.query_log_id)

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
            "suggestions": list(getattr(ans, "suggestions", []) or []),
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
   - 인사 규정·복리후생 등 인사 행정 사항은 인사팀에 문의해 주시기 바랍니다.
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

    with st.form("beta_consent_form"):
        c1, c2 = st.columns(2)
        with c1:
            name = st.text_input("성명 *", value="")
        with c2:
            emp_no = st.text_input("사번 (선택)", value="")
        agree = st.checkbox("위 내용을 모두 읽고 베타 참가에 동의합니다.")
        submitted = st.form_submit_button("동의하고 시작", type="primary")

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

    if not _consent_gate(sb):
        st.stop()

    if "history" not in st.session_state:
        st.session_state["history"] = []

    hotlines = load_hotlines(sb)
    cat = _sidebar(sb, hotlines)

    _render_beta_banner()

    # PR-Fun1.1 작업 3: pending_q early exit — 빠른 액션·Daily Tip·
    # suggestions 카드 클릭으로 적재된 query 가 있으면 empty state /
    # history replay / footer 등을 모두 건너뛰고 즉시 _run_ask 진입 →
    # st.status() spinner 가 사용자 화면 전환 직후 즉시 표시됨.
    _pending_q = st.session_state.pop("pending_q", None)
    if _pending_q:
        _run_ask(sb, _pending_q, cat, hotlines)
        return

    # Hero section
    st.markdown(
        """
        <div class="nx-hero">
          <p class="nx-hero-eyebrow">DF COMPASS · Compliance Intelligence</p>
          <h1 class="nx-hero-title">무엇을 도와드릴까요?</h1>
          <p class="nx-hero-sub">
            신세계디에프 임직원을 위한 윤리·컴플라이언스 가이드<br>
            사규/윤리강령/사례집/징계규정을 통합 검색합니다. (출처 자동 표기)
          </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # PR-Fun1: empty-state — 동적 인사 + Daily Tip + 빠른 액션 카드.
    # history 가 비어있을 때만 노출. 한 번이라도 질문하면 일반 채팅 흐름으로
    # 전환되어 자연스럽게 사라짐. 페이지 새로고침 시 session_state["history"]
    # 초기화되어 다시 노출 (의도된 동작 — 새 세션은 새 사용자 가능성).
    if not st.session_state.get("history"):
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
        with st.chat_message(role):
            if role == "assistant" and meta.get("thinking"):
                with st.expander("🧠 AI 검토 과정", expanded=False):
                    st.caption("AI가 답변을 생성한 검토 단계입니다. 답변 신뢰도 판단에 참고하세요.")
                    st.markdown(meta["thinking"])
            if role == "assistant" and meta.get("critical"):
                _render_critical_banner()
            st.markdown(content)
            # PR-Fun1 작업 4: 카테고리 chip — replay 시 contexts 있으면 표시.
            if role == "assistant" and meta.get("contexts"):
                _render_category_chip(meta["contexts"])
            # PR-C1: history replay 에도 chip 노출. 기존 entry (confidence 키 없음)
            # 는 'high' default 로 회귀 안전.
            if role == "assistant" and meta.get("query_log_id") is not None:
                _render_confidence_chip(meta.get("confidence", "high"))
            if role == "assistant" and meta.get("contexts"):
                _render_contexts(meta["contexts"])
            # PR-Fun1 작업 3·5: suggestions 카드 + 격려 멘트 (replay).
            if role == "assistant" and meta.get("query_log_id") is not None:
                _render_suggestion_cards(
                    list(meta.get("suggestions") or []),
                    is_critical=bool(meta.get("critical")),
                    msg_idx=idx,
                )
                _render_closing_remark(
                    bool(meta.get("critical")), msg_idx=idx,
                )
            # 액션 버튼 — 정상 답변(query_log_id 있음) 한정. 에러 답변은 다시
            # 답변 시 동일 에러 반복 가능성 + 인사팀 문의는 의미 없으므로 미노출.
            if (role == "assistant" and meta.get("query_log_id") is not None):
                _render_action_buttons(
                    idx,
                    original_q=meta.get("original_q"),
                    prev_answer=content,
                    hotlines=hotlines,
                )
            if role == "assistant" and meta.get("query_log_id"):
                _render_feedback(sb, msg_idx=idx, query_log_id=meta["query_log_id"])
            # 멀티 턴 모드 버튼 — 마지막 assistant 메시지 + 정상 답변 한정.
            # 중간 메시지나 에러 답변에 버튼 노출 시 disabled 노이즈 발생 → 차단.
            if (role == "assistant"
                    and idx == len(_history) - 1
                    and meta.get("query_log_id") is not None):
                _render_mode_buttons(idx)

    # PR-Fun1.1 작업 3: pending_q 는 main() 입구의 early exit 가 처리.
    # 여기까지 흘러왔다는 건 카드 클릭 query 가 없었다는 의미라 chat_input
    # 만 처리. clicked_q 변수는 호환성 위해 유지하되 None 으로 둠.
    clicked_q: str | None = None

    st.markdown(
        '<div style="text-align:center; color:#888; font-size:11px; '
        'padding:24px 0 8px 0; border-top:1px solid #eee; margin-top:32px;">'
        '© 2026 신세계디에프 (Shinsegae Duty Free) · 인사담당 CSR팀<br>'
        '본 답변은 사규 해석 보조 도구이며 법적 효력은 없습니다. '
        '인사·신고 행정 사항은 인사팀에 직접 문의하세요.'
        '</div>',
        unsafe_allow_html=True,
    )

    # 🔄 다시 답변 — 액션 버튼 클릭 시 session_state 에 적재된 reroll request.
    # rerun 다음 사이클에 history replay 후 본 분기에서 ask_stream 재호출.
    # pop 으로 즉시 제거 — 동일 reroll 이 두 번 실행되는 일을 차단.
    pending = st.session_state.pop("_pending_reroll", None)
    if pending is not None:
        _run_ask(sb, q="", cat=cat, hotlines=hotlines, reroll_of=pending)
        return

    # max_chars=2000 — 사규 질문에 충분한 길이이며 메가바이트 페이로드 차단
    q = st.chat_input("질문을 입력하세요…", max_chars=2000) or clicked_q
    if not q:
        return

    _run_ask(sb, q, cat, hotlines)


if __name__ == "__main__":
    main()
