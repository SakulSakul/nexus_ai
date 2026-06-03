"""DF COMPASS 스타일 — app.py 에서 분리(동작 무변경, CSS 문자열 그대로).

st.markdown(CSS, unsafe_allow_html=True) 로 주입한다.
"""

CSS = """
<style>
@import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.min.css');
@import url('https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:opsz,wght,FILL,GRAD@20..48,100..700,0..1,-50..200');
@import url('https://fonts.googleapis.com/css2?family=Material+Symbols+Rounded:opsz,wght,FILL,GRAD@20..48,100..700,0..1,-50..200');
@import url('https://fonts.googleapis.com/css2?family=Nanum+Myeongjo:wght@400;700;800&display=swap');
@font-face {
  font-family: 'SDDOES Myeongjo';
  src: url('https://www.shinsegae.com/resources/site/fonts/SDDOESMyeongjoNeoaTTF-dMd.woff') format('woff');
  font-weight: 400 700;
  font-style: normal;
  font-display: swap;
}

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
/* user 질문 — 목업: 오른쪽 진한 말풍선 + 아바타 숨김 (PR-UI8b: testid 양규약 커버) */
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]),
[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]) {
  background: #2C2B28 !important;
  border-color: #2C2B28 !important;
  width: fit-content !important;
  max-width: 78% !important;
  margin-left: auto !important;
  margin-right: 0 !important;
  padding: 0.7rem 1.1rem !important;
  border-radius: 16px !important;
  box-shadow: 0 1px 3px rgba(31,30,29,0.12) !important;
}
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) [data-testid="stChatMessageAvatarUser"],
[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]) [data-testid="chatAvatarIcon-user"] { display: none !important; }
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) .stMarkdown,
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) .stMarkdown p,
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) .stMarkdown li,
[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]) .stMarkdown,
[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]) .stMarkdown p,
[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]) .stMarkdown li {
  color: #FFFFFF !important;
  max-width: none !important;
}

/* ── Chat input (홈 입력창과 동일하게 흰색 · 빨간 포커스 테두리 제거) ── */
[data-testid="stChatInput"] textarea {
  font-family: var(--font) !important;
  border: 0 !important;
  border-top: 1px solid var(--c-border) !important;
  border-radius: 0 !important;
  background: #fff !important;
  font-size: 14.5px !important;
  line-height: 1.6 !important;
  min-height: 54px !important;
  padding: 14px 16px !important;
  color: var(--c-text) !important;
  box-shadow: none !important;
  outline: none !important;
  resize: none !important;
}
[data-testid="stChatInput"] textarea:focus {
  border-top: 1px solid var(--c-border) !important;
  box-shadow: none !important;
}
[data-testid="stChatInput"] {
  border: 0 !important;
  border-top: 1px solid var(--c-border) !important;
  border-radius: 0 !important;
  box-shadow: none !important;
  background: #fff !important;
}
[data-testid="stChatInput"] > div,
[data-testid="stChatInput"] [data-testid="stChatInputTextArea"] {
  background: #fff !important;
}
[data-testid="stChatInput"] > div:focus-within,
[data-testid="stChatInput"]:focus-within {
  border-color: var(--c-border) !important;
  box-shadow: none !important;
}

/* ── Bottom 영역 여백 축소 (입력창 아래 흰 여백 과다) ── */
[data-testid="stBottomBlockContainer"] {
  padding-top: 0.5rem !important;
  padding-bottom: 0.6rem !important;
}

/* ── 역질문 칩: 글 길이와 무관하게 카드 높이 통일 ── */
[class*="st-key-sugg_"] button {
  min-height: 60px !important;
  white-space: normal !important;
  line-height: 1.4 !important;
  padding: 10px 14px !important;
  text-align: center !important;
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
