"""NEXUS AI · 임직원용 Streamlit 프론트엔드 (PoC)."""

from __future__ import annotations

import streamlit as st

import datetime as _dt

from core.chatbot import ask, record_feedback
from core.config import CATEGORIES, get_secret, load_hotlines, settings


st.set_page_config(
    page_title="NEXUS AI",
    page_icon="🛡️",
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
[data-testid="stHeader"] { background: transparent !important; }
[data-testid="stToolbar"] { display: none !important; }
[data-testid="stDecoration"] { display: none !important; }
* { box-sizing: border-box; }

/* ── 4px top frame ── */
.nx-topbar {
  position: fixed;
  top: 0; left: 0; right: 0;
  height: 4px;
  background: var(--c-primary);
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
  background: var(--c-primary) !important;
  border-color: var(--c-primary) !important;
  color: #FFFFFF !important;
  font-weight: 700 !important;
}
[data-testid="stSidebar"] .stFormSubmitButton > button[kind="primary"]:hover,
[data-testid="stSidebar"] .stButton > button[kind="primary"]:hover {
  background: #333333 !important;
  border-color: #333333 !important;
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

/* 베타 배너 — 환경 식별 명시. 운영 이관 시 NEXUS_ENV=prod 로 자동 숨김. */
.nx-beta-banner {
  background: #1A1A1A;
  color: #FFFFFF;
  padding: 10px 18px;
  margin: 0 0 16px;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.08em;
  display: flex;
  align-items: center;
  gap: 12px;
}
.nx-beta-tag {
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.2em;
  background: #FFFFFF;
  color: #1A1A1A;
  padding: 2px 7px;
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


def _render_beta_banner() -> None:
    s = settings()
    if (s.env_tag or "").startswith("prod"):
        return
    st.markdown(
        f"""
        <div class="nx-beta-banner">
          <span class="nx-beta-tag">BETA</span>
          본 환경은 베타 테스트({s.env_tag})이며 개인 인프라에서 운영됩니다 ·
          Gemini 유료 티어(학습 비활성) · 답변 품질 검증 단계입니다.
        </div>
        """,
        unsafe_allow_html=True,
    )


def _check_rate_limit() -> bool:
    """세션 단위 일일 한도. 초과 시 False 반환 (호출자가 안내 문구 출력).
    회사 이관 + SSO 도입 후에는 user_id_hash 기반 서버 카운터로 교체."""
    s = settings()
    today = _dt.date.today().isoformat()
    rec = st.session_state.get("_rate_rec") or {"date": today, "count": 0}
    if rec["date"] != today:
        rec = {"date": today, "count": 0}
    if rec["count"] >= s.daily_query_limit:
        st.session_state["_rate_rec"] = rec
        return False
    rec["count"] += 1
    st.session_state["_rate_rec"] = rec
    return True


def _render_feedback(sb, msg_idx: int, query_log_id: int | None) -> None:
    """답변 1건당 👍/👎 한 번. session_state 로 중복 클릭 차단."""
    if not query_log_id:
        return
    key_state = f"_fb_state_{msg_idx}"
    state = st.session_state.get(key_state)
    if state in ("up", "down"):
        st.caption("👍 의견 감사합니다." if state == "up" else "👎 의견 감사합니다. 사유는 운영자가 검토합니다.")
        return
    c1, c2, _ = st.columns([1, 1, 8])
    if c1.button("👍", key=f"fb_up_{msg_idx}"):
        if record_feedback(sb, query_log_id=query_log_id, feedback=1):
            st.session_state[key_state] = "up"
            st.rerun()
    if c2.button("👎", key=f"fb_down_{msg_idx}"):
        if record_feedback(sb, query_log_id=query_log_id, feedback=-1):
            st.session_state[key_state] = "down"
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


def _run_ask(sb, q: str, cat: str, hotlines: dict) -> None:
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
            s = settings()
            if ans.thinking and s.show_thinking:
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
            # 피드백 UI — 답변마다 고유 인덱스로 위젯 키 분리.
            _render_feedback(sb, msg_idx=len(st.session_state["history"]),
                             query_log_id=ans.query_log_id)

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
            "query_log_id": ans.query_log_id,
        },
    ))


_CONSENT_BODY_MD = """
**본 챗봇은 베타 테스트 중이며, 정보처리자가 회사가 아닌 개별 운영자입니다.**
정식 OPEN 시 회사 GCP(Vertex AI) + 회사 Supabase 로 이관 예정이며,
그 시점부터 회사가 정보처리자가 됩니다.

참가자께서는 아래 내용을 확인·동의하신 뒤 베타 테스트에 참여해 주시기 바랍니다.

1. **데이터 흐름**
   - 입력하신 질의는 `[익명]` 마스킹 후 Google Gemini API(유료 티어)로 전송됩니다.
   - 유료 티어이므로 **모델 학습에는 사용되지 않습니다.**
   - 마스킹 후 본문·검색 hit 만 Supabase 에 저장되며, 원본 질의는 즉시 폐기됩니다.

2. **인프라 주체 (베타 한정)**
   - Supabase 프로젝트 / Gemini API 키 모두 **개별 운영자(개인)** 명의입니다.
   - 회사-Google 간 DPA(데이터 처리 계약) 및 회사 차원의 처리방침 고지는
     **정식 OPEN 후** 적용됩니다.
   - 베타 단계의 로그(`query_logs`)는 회사 계정 이관 시 **이관하지 않고 폐기**됩니다.

3. **답변 한계**
   - 본 챗봇은 사규 해석 보조 도구이며 **법적 효력이 없습니다.**
   - 신고·조사 절차 등 인사 행정 사항은 인사팀에 직접 문의하셔야 합니다.
   - 핫라인 URL 일부는 placeholder 상태일 수 있습니다.

4. **수집 정보**
   - 본 동의 화면에서 입력하신 **성명·사번**은 동의 기록 목적으로만 보관됩니다.
   - 베타 종료 시 동의 기록도 함께 폐기됩니다.

5. **철회**
   - 동의 후에도 운영자(`ADMIN`)에게 요청하시면 본인 동의 기록 및 질의 로그를 삭제할 수 있습니다.
"""


def _record_consent(sb, *, participant: str, version: str, env: str, details: dict) -> None:
    try:
        sb.table("beta_consents").insert({
            "participant":     participant,
            "consent_version": version,
            "env":             env,
            "details":         details,
        }).execute()
    except Exception:
        pass


def _consent_gate(sb) -> bool:
    """베타 환경에서 동의 미완료 시 동의 화면을 렌더하고 False 반환.
    호출자는 False 면 st.stop() 으로 본 화면 렌더를 차단해야 한다.
    운영(`NEXUS_ENV=prod*`)에서는 항상 True (게이트 비활성)."""
    s = settings()
    if not (s.env_tag or "").startswith("beta"):
        return True

    cur_ver = s.consent_version
    if st.session_state.get("beta_consent_v") == cur_ver:
        return True

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
        if not name.strip():
            st.error("성명을 입력해 주세요.")
        elif not agree:
            st.error("동의 체크박스를 선택해 주세요.")
        else:
            participant = name.strip()
            if emp_no.strip():
                participant = f"{participant} / {emp_no.strip()}"
            _record_consent(
                sb,
                participant=participant,
                version=cur_ver,
                env=s.env_tag,
                details={"emp_no": emp_no.strip() or None},
            )
            st.session_state["beta_consent_v"] = cur_ver
            st.session_state["beta_consent_participant"] = participant
            st.rerun()

    return False


def main():
    st.markdown(_CSS, unsafe_allow_html=True)
    # 4px top frame line
    st.markdown('<div class="nx-topbar"></div>', unsafe_allow_html=True)

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
    s = settings()
    for idx, (role, content, meta) in enumerate(st.session_state["history"]):
        with st.chat_message(role):
            if role == "assistant" and meta.get("thinking") and s.show_thinking:
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
            if role == "assistant" and meta.get("query_log_id"):
                _render_feedback(sb, msg_idx=idx, query_log_id=meta["query_log_id"])

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
