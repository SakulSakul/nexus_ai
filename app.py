"""DF COMPASS · 임직원용 Streamlit 프론트엔드 (PoC)."""

from __future__ import annotations

import streamlit as st
import streamlit.components.v1 as components


def _nx_iframe(html: str, *, height: int = 0) -> None:
    """st.components.v1.html (2026-06-01 이후 제거 예정) -> st.iframe 마이그레이션.

    버전 안전: st.iframe 가 있으면 사용, 없으면 구 components.html fallback.
    둘 다 HTML 문자열을 iframe 으로 렌더 -> 내부 JS sandbox 동작 보존.
    """
    _fn = getattr(st, "iframe", None)
    # st.iframe 는 height<=0 을 거부(StreamlitInvalidHeightError).
    # 보이지 않는 JS/CSS 주입 슬롯(height=0, parent window 접근)은 구
    # components.html 로 처리 — 해당 버전에 존재하며 0 허용. 동작 보존.
    # 가시 콘텐츠(height>0)만 st.iframe 로 마이그레이션.
    if _fn is not None and height > 0:
        _fn(html, height=height)
    else:
        components.html(html, height=height)

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
from ui.styles import CSS as _CSS  # PR-refactor(1): 스타일 분리(동작 무변경)

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


from ui.render import (  # PR-refactor(5): 답변 부가 렌더 헬퍼 분리(동작 무변경)
    _render_confidence_chip, _render_answer_meta, _render_category_chip,
    _domain_from_contexts, _render_suggestion_cards, _render_clarify_choices,
    _render_closing_remark, _render_contexts,
)


from ui.cards import (  # PR-refactor(2): 카드 빌더 분리(동작 무변경)
    _slim_structured, _build_structured_card_html, _build_verdict_card_html,
    _answer_card_header_html, _ENABLE_VERDICT_SHADOW, _ENABLE_VERDICT_CARD,
)

from ui.home import _render_empty_state  # PR-refactor(3): 빈 홈 분리(동작 무변경)

_PROD_ENV_VALUES = {"prod", "production"}

_HISTORY_CAP = 100  # session_state["history"] 최대 entry 수 (FIFO 자르기)

_REROLL_PREFIX = (
    "[다시 답변 요청] 이전 답변과 다른 관점·다른 근거 사규·다른 측면을 "
    "강조하여 답변해주세요. 단, 사실관계는 정확해야 합니다.\n\n원 질문: "
)


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
    _nx_iframe(
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
    _nx_iframe(
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


from ui.panels import (  # PR-refactor(4): 신고/문의 패널 분리(동작 무변경)
    _render_report_channels_panel, _render_clean_report_panel, _render_hr_inquiry_panel,
)


from ui.feedback import _render_action_buttons, _render_feedback, _render_mode_buttons  # PR-refactor(6)


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


def _request_stop():
    """⏹ 생성 중지 버튼 on_click — 진행 중 질문 취소 플래그. main() 상단이 처리."""
    st.session_state["_stop_requested"] = True


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
    # PR-diag/auto-resume: 실행 시작 — abort 마커 리셋 + inflight 등록.
    st.session_state["_last_abort"] = None
    st.session_state["_run_phase"] = "start"
    st.session_state["_inflight_q"] = q or None
    st.session_state["_inflight_n"] = st.session_state.get("_inflight_n", 0) + 1
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
        with st.chat_message("user"):
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
            _nx_iframe(
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
        # PR-stop: 생성 중지 — 잘못 입력 시 1분 안 기다리고 즉시 취소. 처리 중 유일하게
        # 허용되는 위젯. 클릭 → on_click 플래그 → rerun → main() 상단이 진행 질문 취소.
        _stop_ph = st.empty()
        with _stop_ph.container():
            st.button("⏹ 생성 중지", key="_stop_gen_btn",
                      on_click=_request_stop, use_container_width=True)

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
                st.session_state["_run_phase"] = "synthesis_stream"
                stream_buffer = answer_placeholder.write_stream(
                    _chunks_to_str_stream(_stream_iter, _stream_holder)
                ) or ""
                ans = _stream_holder["ans"]
                break
            except Exception as e:
                last_err = e
                tb_str = traceback.format_exc()
                st.session_state["_last_abort"] = {"type": "llm_error",
                    "phase": "synthesis_stream",
                    "detail": f"{type(e).__name__}: {e}"[:300], "attempt": attempt}
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
        try:
            _stop_ph.empty()
        except Exception:
            pass

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
            st.session_state["_run_phase"] = "post_stream_render"
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
                st.session_state["_inflight_q"] = None
                st.session_state["_inflight_n"] = 0
                st.session_state["_run_phase"] = "done"
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
        st.session_state["_inflight_q"] = None
        st.session_state["_inflight_n"] = 0
        st.session_state["_run_phase"] = "done"
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

    st.session_state["_run_phase"] = "committing"
    st.session_state["_inflight_q"] = None
    st.session_state["_inflight_n"] = 0
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
    st.session_state["_run_phase"] = "done"


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
    # PR-rootfix: CookieManager 양방향 컴포넌트는 매 run 비동기 post-back → rerun.
    # _run_ask 중 그 rerun 이 터지면 답변 커밋 전 인터럽트(dangling). 동의 완료 세션 +
    # 쿠키 set 대기 없음이면 컴포넌트를 안 그려 채팅 중 rerun 소스 제거.
    _session_ok = st.session_state.get("beta_consent_v") == cur_ver
    if _session_ok and not st.session_state.get("_pending_consent_cookie"):
        return True
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

    # 분기 1: 같은 session 통과 (pending cookie set 처리 후 재확인)
    if _session_ok:
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


def _run_ask_guarded(*args, **kwargs):
    """_run_ask 의 모든-단계 예외/인터럽트 포착·가시화 (조용한 dangling 박멸).
    - RerunException/StopException = Streamlit 흐름제어 → 마커+rerun_data 기록 후 재-raise.
    - 그 외 예외(retrieval·합성·렌더·커밋 어느 단계든) → 마커+화면+에러턴 노출."""
    import sys as _sysg, traceback as _tbg
    try:
        _run_ask(*args, **kwargs)
    except BaseException as _e:
        _cls = type(_e).__name__
        _ph = st.session_state.get("_run_phase", "?")
        if _cls in ("RerunException", "StopException"):
            _rd = getattr(_e, "rerun_data", None); _rdi = ""
            try:
                if _rd is not None:
                    _rdi = (f"qs={getattr(_rd,'query_string',None)!r} "
                            f"page={getattr(_rd,'page_script_hash',None)!r} "
                            f"widgets={'Y' if getattr(_rd,'widget_states',None) else 'N'} "
                            f"frag={getattr(_rd,'fragment_id_queue',None)!r}")
            except Exception:
                _rdi = "(rerun_data introspect fail)"
            st.session_state["_last_abort"] = {"type": "streamlit_interrupt",
                "phase": _ph, "cls": _cls, "rerun_data": _rdi}
            print(f"[RUN_ABORT] Streamlit interrupt ({_cls}) phase={_ph} {_rdi} "
                  f"— 답변 커밋 전 중단(=dangling 원인)", file=_sysg.stderr, flush=True)
            raise
        _det = f"{_cls}: {_e}"
        st.session_state["_last_abort"] = {"type": "runtime_error", "phase": _ph,
            "detail": _det[:300]}
        print(f"[RUN_ERROR] phase={_ph} {_det}\n{_tbg.format_exc()}",
              file=_sysg.stderr, flush=True)
        try:
            st.error(f"\u274c 답변 처리 중 오류 (단계 {_ph}): {_det}")
        except Exception:
            pass
        try:
            _h = st.session_state.get("history", [])
            if _h and _h[-1][0] == "user":
                _h.append(("assistant",
                    f"\u26a0\ufe0f 답변 처리 중 오류가 발생했습니다 (단계 {_ph}): {_det}",
                    {"contexts": [], "critical": False, "elapsed": 0.0,
                     "original_q": _h[-1][1]}))
        except Exception:
            pass
        st.session_state["_inflight_q"] = None
        st.session_state["_inflight_n"] = 0


def main():
    st.markdown(_CSS, unsafe_allow_html=True)
    # 4px top frame line
    st.markdown('<div class="nx-topbar"></div>', unsafe_allow_html=True)
    # PR-stop: 생성 중지 처리 — 진행 질문 취소(턴 제거+상태 리셋)+입력 재활성.
    # 외부종료 오탐 방지를 위해 breadcrumb 보다 _먼저_ 실행.
    if st.session_state.pop("_stop_requested", False):
        import sys as _syss
        st.session_state["clicked_q"] = None
        st.session_state.pop("_pending_reroll", None)
        st.session_state["_inflight_q"] = None
        st.session_state["_inflight_n"] = 0
        st.session_state["_last_abort"] = None
        st.session_state["_run_phase"] = "done"
        _h = st.session_state.get("history", [])
        if _h and _h[-1][0] == "user":
            st.session_state["history"] = _h[:-1]
        print("[STOP] 사용자 생성 중지 — 진행 질문 취소", file=_syss.stderr, flush=True)
    # PR-diag: run breadcrumb + 외부종료 감지. sid 변화=재연결. 직전 run 이 mid-phase
    # 인데 예외 마커 없음 = Python 예외 없이 프로세스 사망(인프라/리소스/웹소켓).
    import sys as _sysd
    try:
        from streamlit.runtime.scriptrunner import get_script_run_ctx as _gctx
        _ctxd = _gctx()
        _sidd = (_ctxd.session_id[:8] if _ctxd and getattr(_ctxd, "session_id", None) else "?")
    except Exception:
        _sidd = "?"
    _pp = st.session_state.get("_run_phase")
    if (_pp in ("start", "synthesis_stream", "post_stream_render", "committing")
            and not st.session_state.get("_last_abort")):
        st.session_state["_last_abort"] = {"type": "external_kill", "phase": _pp}
        print(f"[RUN_KILLED] 직전 run phase={_pp} 예외없이 종료 → 외부종료 추정"
              f"(인프라/리소스/웹소켓/서버재시작)", file=_sysd.stderr, flush=True)
    st.session_state["_diag_run_n"] = st.session_state.get("_diag_run_n", 0) + 1
    print(f"[RUN_DIAG] run#{st.session_state['_diag_run_n']} sid={_sidd} "
          f"clicked_q={bool(st.session_state.get('clicked_q'))} "
          f"inflight={st.session_state.get('_inflight_q') is not None}:{st.session_state.get('_inflight_n',0)} "
          f"last_phase={_pp} last_abort={st.session_state.get('_last_abort')}",
          file=_sysd.stderr, flush=True)

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
    # PR-concurrent-guard: 처리 중(clicked_q/reroll)인 run 에서는 모든 제출 위젯을
    # 비활성/미렌더 → 답 생성(합성) 도중 새 제출이 run 을 폐기(external_kill)하는 것을
    # 원천 차단. (로그 확정: 동시 제출 시 진행 run 이 synthesis_stream 에서 외부종료됨.)
    _q_processing = bool(st.session_state.get("clicked_q")) or (
        st.session_state.get("_pending_reroll") is not None
    )
    q_input = st.chat_input(
        "질문을 입력하세요…", max_chars=2000, disabled=_q_processing
    )
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
        with st.chat_message(role, avatar=("🧭" if role == "assistant" else None)):
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
                if not _q_processing:
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
            if role == "assistant" and not _q_processing:
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
            if (role == "assistant" and meta.get("query_log_id") is not None
                    and not _q_processing):
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
            if role == "assistant" and not _q_processing and (
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
                    and meta.get("query_log_id") is not None
                    and not _q_processing):
                _render_mode_buttons(idx)

    # PR-retry-dangling: 답변이 안 만들어진 채 끝난 턴 감지 → 재실행 버튼.
    # 긴 RAG 생성(30~60초)이 Streamlit rerun/취소로 인터럽트되면 user 턴만
    # history 에 남고 assistant 턴이 없어 화면이 백지가 된다(에러 메시지조차
    # 없음). 이 경우 마지막 history 가 "user" 로 끝나므로 감지 가능. 새 질문
    # 처리 중(clicked_q/reroll/q_input)이면 곧 정상 답변이 push 되므로 미표시.
    # 재실행은 댕글링 user 턴 제거 후 기존 clicked_q 재질의 경로 재사용.
    _hist_now = st.session_state.get("history", [])
    if (
        _hist_now
        and _hist_now[-1][0] == "user"
        and not st.session_state.get("clicked_q")
        and not st.session_state.get("_pending_reroll")
        and not q_input
    ):
        _inflight = st.session_state.get("_inflight_q")
        _n = st.session_state.get("_inflight_n", 0)
        _CAP = 6
        if _inflight and _n < _CAP:
            import sys as _sysar
            print(f"[AUTO_RESUME] n={_n}/{_CAP} q={str(_inflight)[:40]!r} — 커밋전 중단 자동복구",
                  file=_sysar.stderr, flush=True)
            st.session_state["history"] = _hist_now[:-1]
            st.session_state["clicked_q"] = _inflight
            st.rerun()
        st.session_state["_inflight_q"] = None
        st.session_state["_inflight_n"] = 0
        _ab = st.session_state.get("_last_abort") or {}
        _ph = st.session_state.get("_run_phase", "?")
        _t = _ab.get("type")
        if _t == "streamlit_interrupt":
            st.warning(
                f"\u26a0\ufe0f 직전 답변이 **Streamlit rerun 으로 중단** "
                f"({_ab.get('cls')} · 단계 {_ab.get('phase')} · {_n}회 자동재시도 후).\n\n"
                f"rerun 트리거: `{_ab.get('rerun_data','?')}`\n\n다시 시도해 주세요."
            )
        elif _t == "llm_error":
            st.warning(
                f"\u26a0\ufe0f 직전 답변이 **LLM 오류로 중단** (단계 {_ab.get('phase')}):\n\n"
                f"`{_ab.get('detail')}`\n\n다시 시도해 주세요."
            )
        elif _t == "runtime_error":
            st.warning(
                f"\u26a0\ufe0f 직전 답변이 **처리 중 오류로 중단** (단계 {_ab.get('phase')}):\n\n"
                f"`{_ab.get('detail')}`\n\n다시 시도해 주세요."
            )
        elif _t == "external_kill":
            st.warning(
                f"\u26a0\ufe0f 직전 답변이 단계 **{_ab.get('phase')}** 에서 "
                f"**예외 없이 종료** = Streamlit/인프라가 프로세스를 종료(리소스·웹소켓·서버재시작). "
                f"앱/LLM 코드 오류가 아닙니다.\n\n다시 시도해 주세요."
            )
        else:
            st.warning(
                f"\u26a0\ufe0f 직전 답변이 커밋 전 종료 (마지막 단계: {_ph}, 원인 미기록). 다시 시도해 주세요."
            )
        if st.button(
            "\U0001f504 이 질문 다시 실행",
            use_container_width=True,
            key=f"_retry_dangling_{len(_hist_now)}",
        ):
            _dangling_q = _hist_now[-1][1]
            st.session_state["history"] = _hist_now[:-1]
            st.session_state["clicked_q"] = _dangling_q
            st.rerun()

    # PR-Fun1.5: pending_q 매개체 폐기. clicked_q 매개체는 main() 입구의
    # early exit 가 별도 처리. 여기엔 chat_input 만 처리.
    st.markdown(
        '<div style="text-align:center; color:#888; font-size:11px; '
        'padding:24px 0 8px 0; border-top:1px solid var(--c-border); margin-top:32px;">'
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
        _run_ask_guarded(sb, _clicked, _clicked_cat or cat, hotlines,
                 hard_category=_clicked_hard)
        st.rerun()

    # 🔄 다시 답변 — 액션 버튼 클릭 시 session_state 에 적재된 reroll request.
    # rerun 다음 사이클에 history replay 후 본 분기에서 ask_stream 재호출.
    # pop 으로 즉시 제거 — 동일 reroll 이 두 번 실행되는 일을 차단.
    pending = st.session_state.pop("_pending_reroll", None)
    if pending is not None:
        _run_ask_guarded(sb, q="", cat=cat, hotlines=hotlines, reroll_of=pending)
        return

    # chat_input 직접 입력 → clicked_q 경로로 통일 후 rerun.
    # 처리 run 은 _q_processing=True 라 chat_input·칩 전부 비활성 → 합성 도중
    # 동시 제출(폐기) 불가. (인라인 처리 제거 — co-render 는 다음 run 게이트가 처리.)
    if not q_input:
        return
    st.session_state["clicked_q"] = q_input
    st.rerun()


if __name__ == "__main__":
    main()
