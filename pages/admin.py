"""DF COMPASS · 관리자용 Streamlit 대시보드 (PoC).

기능:
- DOCX 업로드 → 청킹 → 카테고리 자동 추천 → 관리자 확인 → 적재
- 사규 버전 목록 (active / archived)
- 리스크 트렌드 레이더 (카테고리별 질의 빈도, k-anonymity 5 보장)
- Phase 3.5 도메인 검수 (샘플 등록 + CSV 일괄 + 회차 실행 + 4지표 채점)
- 핫라인/안내 문구 편집 (사내 익명제보, 외부 상담채널, 인사 라우팅)
- 심각 사안 키워드 사전 편집
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import json
import re
from collections import Counter, defaultdict

import streamlit as st

from core.config import CATEGORIES, settings
from core.review import run_review, threshold_breached
from parser.docx_parser import (
    looks_like_hr_procedure, match_hr_procedure_hints,
    parse_docx, suggest_categories,
)
from parser.ingest import ingest_docx


st.set_page_config(page_title="DF COMPASS · Admin", page_icon="🛠️", layout="wide")

# 헤더 anchor 아이콘 제거 + 사이드바 reopen 토글 prominent 스타일 (전역).
st.markdown(
    """
    <style>
    /* Streamlit 헤더 anchor 링크 아이콘 제거 */
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

    /* 사이드바 닫힘 상태 reopen 토글: 좌상단 고정·흑백 prominent */
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

    /* ──────────────────────────────────────────────────────────
       신세계 시그니처 레드 액센트 토큰 (admin 페이지 한정)
       app.py 와 동일한 토큰을 노출. 본문/구조는 흑백 유지하고
       상단 4px 프레임 · Primary 버튼 · 탭 활성 인디케이터에만 사용.
       ────────────────────────────────────────────────────────── */
    :root {
        --c-primary:    #1A1A1A;
        --c-accent:     #C8102E;
        --c-accent-dark:#9A0C24;
        --c-accent-bg:  #FCEBEE;
        --c-border:     #E0E0E0;
    }

    .nx-topbar {
        position: fixed;
        top: 0; left: 0; right: 0;
        height: 4px;
        background: var(--c-accent);
        z-index: 9999;
    }

    /* Primary 버튼 — 신세계 레드 */
    .stButton > button[kind="primary"],
    .stFormSubmitButton > button[kind="primary"] {
        background: var(--c-accent) !important;
        border: 1px solid var(--c-accent) !important;
        color: #FFFFFF !important;
        box-shadow: none !important;
    }
    .stButton > button[kind="primary"]:hover,
    .stFormSubmitButton > button[kind="primary"]:hover {
        background: var(--c-accent-dark) !important;
        border-color: var(--c-accent-dark) !important;
        box-shadow: none !important;
        transform: none !important;
    }

    /* 탭(Tabs) 활성 인디케이터 — 신세계 레드 */
    [data-baseweb="tab-highlight"] {
        background-color: var(--c-accent) !important;
    }
    [data-baseweb="tab-border"] {
        background-color: var(--c-border) !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


_LOGIN_LOCKOUT_LIMIT = 5    # 5회 실패 후 lockout
_LOGIN_LOCKOUT_SECS  = 60   # 60초 잠금


def _require_auth() -> None:
    """Admin 페이지 진입 전 비밀번호 인증. 미인증 시 st.stop()으로 렌더링 차단.
    무차별 대입 방어 — 5회 실패 시 60초 lockout (session_state 기반)."""
    from core.config import get_secret
    import time as _time

    if st.session_state.get("admin_authenticated"):
        return

    st.title("🔐 DF COMPASS · Admin 로그인")

    admin_pw = get_secret("ADMIN_PASSWORD")
    if not admin_pw:
        st.error("ADMIN_PASSWORD secret이 설정되지 않았습니다. 관리자에게 문의하세요.")
        st.stop()

    # Lockout 체크
    locked_until = st.session_state.get("_admin_locked_until", 0.0)
    now = _time.time()
    if locked_until > now:
        wait = int(locked_until - now)
        st.error(f"⚠️ 너무 많은 실패. **{wait}초 후** 다시 시도해 주세요.")
        st.stop()

    fails = int(st.session_state.get("_admin_fail_count", 0))
    if fails > 0:
        st.caption(f"비밀번호 시도 {fails}/{_LOGIN_LOCKOUT_LIMIT} — 5회 실패 시 60초 잠금")

    with st.form("admin_login"):
        pw = st.text_input("관리자 비밀번호", type="password")
        submitted = st.form_submit_button("로그인", type="primary")

    if submitted:
        if pw == admin_pw:
            st.session_state["admin_authenticated"] = True
            st.session_state["_admin_fail_count"] = 0
            st.session_state["_admin_locked_until"] = 0.0
            st.rerun()
        else:
            fails += 1
            st.session_state["_admin_fail_count"] = fails
            if fails >= _LOGIN_LOCKOUT_LIMIT:
                st.session_state["_admin_locked_until"] = _time.time() + _LOGIN_LOCKOUT_SECS
                st.session_state["_admin_fail_count"] = 0
                st.error(f"⚠️ {_LOGIN_LOCKOUT_LIMIT}회 실패 — {_LOGIN_LOCKOUT_SECS}초 동안 잠금됩니다.")
            else:
                st.error(f"비밀번호가 틀렸습니다. ({fails}/{_LOGIN_LOCKOUT_LIMIT})")

    st.stop()


def _supabase():
    """매 호출마다 새 클라이언트 생성. cache_resource 미사용 — multi-user
    Streamlit Cloud 에서 한 세션의 httpx close 가 다른 세션에 전파되는 문제
    회피. (app.py 도 동일 패턴.)"""
    from supabase import create_client
    s = settings()
    if not s.supabase_url or not s.supabase_key:
        return None
    return create_client(s.supabase_url, s.supabase_key)


def _supabase_admin():
    """service_role 클라이언트 — RLS 를 우회한다.

    ⚠️ 본 함수는 _require_auth() 로 비밀번호 게이트를 통과한 admin 페이지
    안에서만 호출할 것. 일반 사용자 코드 경로(app.py 응답)에서는 절대
    임포트/사용 금지. SUPABASE_SERVICE_ROLE_KEY 미설정 시 None.
    cache_resource 미사용 — 동일한 multi-user 격리 사유."""
    from supabase import create_client
    s = settings()
    if not s.supabase_url or not s.supabase_service_role_key:
        return None
    return create_client(s.supabase_url, s.supabase_service_role_key)


@st.cache_data(show_spinner=False)
def _cached_parse(file_bytes: bytes) -> list:
    return parse_docx(file_bytes)


def _rows_to_csv_bytes(rows: list[dict]) -> bytes:
    """list[dict] → CSV bytes (UTF-8 with BOM, Excel 호환). 빈 리스트면 b''."""
    if not rows:
        return b""
    keys: list[str] = []
    for r in rows:
        for k in r.keys():
            if k not in keys:
                keys.append(k)
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=keys, extrasaction="ignore")
    w.writeheader()
    for r in rows:
        w.writerow({k: ("" if r.get(k) is None else r.get(k)) for k in keys})
    return ("﻿" + buf.getvalue()).encode("utf-8")


def _audit(sb_admin, *, action: str, target: str | None = None,
           details: dict | None = None, actor: str | None = None) -> None:
    """관리자 행위 감사 로그. 실패해도 본 작업 흐름은 막지 않는다."""
    if sb_admin is None:
        return
    try:
        actor = actor or st.session_state.get("admin_actor") or "admin"
        sb_admin.table("admin_audit_logs").insert({
            "actor":   actor,
            "action":  action,
            "target":  target,
            "details": details or {},
        }).execute()
    except Exception:
        pass


@st.cache_data(ttl=60, show_spinner=False)
def _query_logs_health_check(_sb) -> dict:
    """최근 24시간 query_logs INSERT 건수 확인. silent fail 감시용.

    이전 사고: RLS INSERT 정책 누락으로 chatbot 응답 경로의 INSERT 가
    silent fail 했음. 본 헬스체크는 admin 진입 시 1회 호출되어 0 건이면
    배너로 운영자에게 즉시 알린다.

    파라미터 `_sb` 는 leading underscore 로 Streamlit cache 해싱 우회
    (supabase Client 는 unhashable). 60초 TTL — admin 페이지의 잦은
    rerun 부하 완화. 실패해도 페이지 진입은 막지 않는다.
    """
    from datetime import datetime, timedelta, timezone
    try:
        since = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
        res = (
            _sb.table("query_logs")
            .select("id", count="exact")
            .gte("ts", since)
            .limit(1)
            .execute()
        )
        return {"ok": True, "count": res.count or 0, "error": None}
    except Exception as e:
        return {"ok": False, "count": 0, "error": str(e)}


def _render_query_logs_health_banner(sb) -> None:
    """admin 진입부에서 호출. 이상 시 배너 표시 + dismiss 버튼.

    배너 자체가 페이지 진입을 막지는 않음(st.stop 없음). 운영자가
    "확인했음" 클릭 시 세션 동안 숨김.

    PR-S1: query_logs SELECT 는 RLS 로 anon 차단되어 service_role
    클라이언트로만 가능. _supabase_admin() 미설정 시 안내 배너로 폴백.
    """
    if st.session_state.get("health_warn_dismissed"):
        return
    admin_sb = _supabase_admin()
    if admin_sb is None:
        st.warning(
            "⚠️ `SUPABASE_SERVICE_ROLE_KEY` 미설정 — query_logs 헬스 체크"
            "와 레이더 통계가 동작하지 않습니다. (PR-S1 RLS 차단 후 admin "
            "경로는 service_role 키 필수)"
        )
        if st.button("확인했음 (이 세션 동안 숨김)", key="dismiss_health_warn"):
            st.session_state["health_warn_dismissed"] = True
            st.rerun()
        return
    health = _query_logs_health_check(admin_sb)
    if health["ok"] and health["count"] > 0:
        return  # 정상 트래픽 — 배너 없음

    if not health["ok"]:
        st.error(
            f"⚠️ query_logs SELECT 실패: {health['error']}\n\n"
            "RLS 정책 또는 테이블 존재 여부를 확인하세요. 통계 기능이 동작하지 않습니다."
        )
    else:
        st.warning(
            "⚠️ 최근 24시간 동안 query_logs 에 적재된 row 가 0 건입니다.\n\n"
            "원인 가능성:\n"
            "1. 사용자 질의가 없었음 (정상 — 베타 단계 트래픽 적음)\n"
            "2. RLS INSERT 정책 누락으로 silent fail (이전 사고와 동일 패턴)\n"
            "3. chatbot.py INSERT 코드 경로 이슈\n\n"
            "Supabase Dashboard 에서 직접 row 존재 여부 확인 권장."
        )
    if st.button("확인했음 (이 세션 동안 숨김)", key="dismiss_health_warn"):
        st.session_state["health_warn_dismissed"] = True
        st.rerun()


_KIND_LABEL = {"rule": "사규", "case": "사례", "penalty": "징계"}


def _tab_upload(sb):
    st.subheader("📥 DOCX 업로드 및 적재")

    files = st.file_uploader(
        "워드 파일 업로드 (여러 개 선택 가능)",
        type=["docx"],
        accept_multiple_files=True,
    )
    if not files:
        return

    uploader = st.text_input("등록자 (식별용, 전체 공통)", value="", key="ul_uploader")
    st.markdown(f"**총 {len(files)}개 파일** — 파일별로 카테고리를 확인·수정하세요.")
    st.markdown("---")

    valid_configs: list[dict] = []

    _MAX_DOCX_BYTES = 20 * 1024 * 1024   # 20MB — 사규 한 권 충분, OOM 방어
    for uf in files:
        fkey = uf.name
        # uf.size 로 read 전 사전 차단 (OOM 진짜 방어). UploadedFile 은 .size 속성 보장.
        pre_size = getattr(uf, "size", None)
        if isinstance(pre_size, int) and pre_size > _MAX_DOCX_BYTES:
            st.error(
                f"🚫 {uf.name}: {pre_size/1_048_576:.1f}MB — "
                f"한도 {_MAX_DOCX_BYTES/1_048_576:.0f}MB 초과로 건너뜀 (read 전 차단)."
            )
            continue
        file_bytes = uf.read()
        # double-check (uf.size 가 부정확한 경우 방어)
        if len(file_bytes) > _MAX_DOCX_BYTES:
            st.error(
                f"🚫 {uf.name}: {len(file_bytes)/1_048_576:.1f}MB — "
                f"한도 {_MAX_DOCX_BYTES/1_048_576:.0f}MB 초과로 건너뜀."
            )
            continue
        title_default = uf.name.rsplit(".", 1)[0]
        chunks = _cached_parse(file_bytes)
        sample = "\n".join(c.text for c in chunks[:6])
        matched_hints = match_hr_procedure_hints(title_default, sample)
        auto_cats = suggest_categories(sample)

        # 신고·조사 절차 hint 매칭 시 ⚠ 라벨로 expander 펼쳐 매칭 단어 노출.
        # admin 이 sensitive 마킹 강제 적재 체크박스를 체크해야만 일반 적재
        # 폼이 이어 노출된다. 미체크 시 기존 차단 동작 보존(continue).
        if matched_hints:
            label = f"⚠ {uf.name}  ·  신고·조사 절차 hint 매칭"
            expanded = True
        else:
            label = f"📄 {uf.name}  ·  청크 {len(chunks)}개"
            expanded = False

        with st.expander(label, expanded=expanded):
            sensitive_kind: str | None = None
            if matched_hints:
                # harassment 신호 단어가 하나라도 포함되면 harassment, 없으면 safety.
                # safety 폴백은 "신고처리"/"조사위원회"/"신고 절차" 같은 일반
                # 안전 사고 신고 절차 사규를 admin 이 직접 강제 적재할 때를 위함.
                harassment_hints = {"괴롭힘 신고", "성희롱 신고", "고충처리"}
                sensitive_kind = (
                    "harassment"
                    if any(h in harassment_hints for h in matched_hints)
                    else "safety"
                )
                st.warning(
                    f"신고·조사 절차 사규로 판단됨. "
                    f"매칭된 단어: **{', '.join(matched_hints)}**\n\n"
                    "이 사규는 적재 시 sensitive 마킹되며, RAG 답변에서 자동으로 핫라인 안내가 "
                    "추가됩니다 (현재 사용자 질의에 괴롭힘/성희롱/갑질 등 키워드 포함 시 동작; "
                    "키워드 회피 질의 대응은 PR 2)."
                )
                force = st.checkbox(
                    f"⚠ sensitive 마킹('{sensitive_kind}')으로 강제 적재",
                    key=f"ul_force_sensitive_{fkey}",
                )
                if not force:
                    continue

            st.caption(f"자동 추천 카테고리: **{', '.join(auto_cats)}** — 아래에서 수정")
            col1, col2 = st.columns(2)
            with col1:
                title = st.text_input(
                    "문서 제목", value=title_default, key=f"ul_title_{fkey}"
                )
                kind = st.selectbox(
                    "문서 종류",
                    options=["rule", "case", "penalty"],
                    format_func=lambda x: _KIND_LABEL[x],
                    key=f"ul_kind_{fkey}",
                )
                version = st.text_input(
                    "개정 차수 (예: v1)", value="v1", key=f"ul_ver_{fkey}"
                )
            with col2:
                eff = st.date_input(
                    "시행일", value=dt.date.today(), key=f"ul_eff_{fkey}"
                )
                # 1년 이상 미래 시행일 경고 — 오타 방어 (예: 2030 입력).
                # nexus_hybrid_search 가 effective_date 필터로 검색에서 제외하므로
                # 잘못된 미래 시행일이 들어가면 그 사규는 영원히 안 잡힘.
                if eff and (eff - dt.date.today()).days > 365:
                    st.warning(
                        f"⚠ 시행일이 1년 이상 미래({eff.isoformat()}) — "
                        "오타 여부 확인. 검색 결과에 노출되지 않습니다."
                    )
                cats = st.multiselect(
                    "카테고리 (다중 선택, 필수)",
                    options=list(CATEGORIES),
                    default=auto_cats,
                    key=f"ul_cats_{fkey}",
                )
            # 관리부서: 2열 바깥에 전폭으로 배치. 자유 텍스트, 선택 입력.
            # 빈 값은 ingest_docx 진입 시 NULL 로 정규화된다.
            dept = st.text_input(
                "관리부서",
                value="",
                placeholder="예: 인사팀, 윤리경영팀, 컴플라이언스팀",
                help="사규 본문에 명시된 관리부서명을 그대로 입력. "
                     "비워두면 챗봇이 일반 안내문구 사용.",
                key=f"ul_dept_{fkey}",
            )
            with st.expander("청크 미리보기 (5개)", expanded=False):
                for c in chunks[:5]:
                    head = c.article_no or (
                        f"#{c.case_no}" if c.case_no else f"chunk {c.chunk_idx}"
                    )
                    st.markdown(f"**{head}**")
                    st.caption(c.text[:400])

            valid_configs.append({
                "fname": uf.name,
                "file_bytes": file_bytes,
                "title": title,
                "kind": kind,
                "version": version,
                "eff": eff,
                "cats": cats,
                "department": dept,
                # matched_hints 가 비어있으면 None — meta.sensitive_kind 미저장.
                # 강제 적재 케이스만 "harassment"/"safety" 가 ingest_docx 에 전달돼
                # nexus_documents.meta.sensitive_kind 로 마킹된다.
                "force_sensitive_kind": sensitive_kind,
            })

    if not valid_configs:
        return

    st.markdown("---")
    st.markdown(f"적재 대상: **{len(valid_configs)}개 파일**")

    if st.button("✅ 전체 적재 실행", type="primary", key="ul_submit"):
        admin_sb = _supabase_admin()
        for cfg in valid_configs:
            if not cfg["cats"]:
                st.error(f"**{cfg['fname']}** — 카테고리를 1개 이상 선택하세요.")
                continue
            with st.spinner(f"{cfg['fname']} 임베딩 및 적재 중..."):
                try:
                    res = ingest_docx(
                        sb,
                        file_bytes=cfg["file_bytes"],
                        title=cfg["title"],
                        doc_kind=cfg["kind"],
                        version=cfg["version"],
                        effective_date=cfg["eff"],
                        uploaded_by=uploader or None,
                        confirmed_categories=cfg["cats"],
                        department=cfg["department"],
                        source_filename=cfg["fname"],
                        force_sensitive_kind=cfg.get("force_sensitive_kind"),
                    )
                    if res.skipped_hr_procedure:
                        st.error(f"**{cfg['fname']}** — 신고절차 문서로 차단됨")
                        _audit(admin_sb, action="document_upload_blocked",
                               target=cfg["fname"], details={"reason": "hr_procedure"},
                               actor=uploader or None)
                    else:
                        msg = f"**{cfg['fname']}** — 청크 {res.chunks_inserted}개 적재 완료"
                        if res.archived_previous:
                            msg += " · 이전 버전 자동 archived"
                        st.success(msg)
                        _audit(admin_sb, action="document_upload",
                               target=str(res.document_id) if res.document_id else None,
                               details={
                                   "title": cfg["title"], "kind": cfg["kind"],
                                   "version": cfg["version"],
                                   "filename": cfg["fname"],
                                   "chunks": res.chunks_inserted,
                                   "archived_previous": res.archived_previous,
                                   "sensitive_kind": cfg.get("force_sensitive_kind"),
                               },
                               actor=uploader or None)
                except Exception as e:
                    st.error(f"**{cfg['fname']}** — 오류: {e}")


def _tab_versions(sb):
    st.subheader("📚 문서/버전 관리")
    show_archived = st.toggle("archived 포함", value=False)
    q = sb.table("nexus_documents").select("*").order("uploaded_at", desc=True)
    if not show_archived:
        q = q.eq("status", "active")
    rows = q.execute().data or []
    if not rows:
        st.info("등록된 문서가 없습니다.")
        return
    # 다중 선택 가능한 dataframe — 일괄 삭제 영역에서 selection 사용.
    # selection_mode="multi-row" + on_select="rerun" 로 row 클릭·Shift/Ctrl 클릭 다중 선택.
    event = st.dataframe(
        rows,
        use_container_width=True,
        selection_mode="multi-row",
        on_select="rerun",
        key="docs_table_select",
    )
    selected_rows = event.selection.rows if event and event.selection else []

    # 관리부서 인라인 편집기. 적재 시 비워뒀거나 사규 본문 표기가
    # 바뀐 경우 admin 이 코드 수정 없이 즉시 갱신할 수 있도록 제공.
    # 빈 입력은 NULL 로 정규화. 업데이트는 service_role 키로만 가능.
    st.markdown("---")
    st.markdown("#### 🏢 관리부서 인라인 편집")
    admin_sb = _supabase_admin()
    if admin_sb is None:
        st.caption(
            "SUPABASE_SERVICE_ROLE_KEY secret 이 설정되지 않아 부서 편집을 사용할 수 없습니다."
        )
        return
    for r in rows:
        doc_id = r["id"]
        title = r.get("title") or "(제목 없음)"
        version = r.get("version") or ""
        status = r.get("status") or ""
        current = r.get("owning_department") or ""
        c1, c2, c3 = st.columns([5, 4, 1])
        with c1:
            st.markdown(f"**{title}** · {version} · `{status}`")
        with c2:
            new_dept = st.text_input(
                "관리부서",
                value=current,
                placeholder="예: 인사팀, 윤리경영팀",
                key=f"ver_dept_{doc_id}",
                label_visibility="collapsed",
            )
        with c3:
            if st.button("저장", key=f"ver_dept_save_{doc_id}"):
                norm = new_dept.strip() or None
                if norm == (current or None):
                    st.toast("변경 사항 없음")
                else:
                    admin_sb.table("nexus_documents").update(
                        {"owning_department": norm}
                    ).eq("id", doc_id).execute()
                    _audit(admin_sb, action="owning_department_update",
                           target=str(doc_id),
                           details={"title": title, "before": current, "after": norm})
                    st.success(f"저장됨: {title}")
                    st.rerun()

    # ── 문서 일괄 삭제 (다중 선택 + 체크박스 확인 + 명시 버튼) ────
    # archive 만으로는 vector 인덱스가 시간 지나며 비대해짐. 완전 삭제는
    # nexus_chunks 도 ON DELETE CASCADE 로 같이 사라져 검색 인덱스도 정리됨.
    # Storage 의 원본 docx (nexus-docs-original 버킷) 도 함께 정리.
    st.markdown("---")
    st.markdown("#### 🗑️ 문서 일괄 삭제 (되돌릴 수 없음)")
    st.caption(
        "위 표에서 행을 다중 선택한 뒤 삭제할 수 있습니다. "
        "nexus_chunks 와 Storage 의 원본 docx 도 함께 정리됩니다."
    )

    if not selected_rows:
        st.info("삭제할 행을 위 표에서 선택하세요.")
    else:
        selected_ids: list[str] = []
        selected_titles: list[str] = []
        selected_storage_paths: list[str] = []
        for idx in selected_rows:
            row = rows[idx]
            selected_ids.append(row["id"])
            selected_titles.append(
                f"{row.get('title', '?')} ({row.get('version', '?')})"
            )
            sp = row.get("source_storage_path")
            if sp:
                selected_storage_paths.append(sp)

        st.warning(f"**{len(selected_ids)}건 선택됨**")
        with st.expander("선택된 사규 목록", expanded=(len(selected_ids) <= 5)):
            for t in selected_titles:
                st.write(f"- {t}")

        # 5건 초과 시 추가 경고 — 일상적 정리(1~3건)는 한 번에, 대량 실수만 차단.
        if len(selected_ids) > 5:
            st.error(
                f"⚠️ {len(selected_ids)}건은 평소보다 많은 양입니다. "
                "의도한 작업인지 다시 확인하세요."
            )

        confirm = st.checkbox(
            f"위 {len(selected_ids)}건의 문서를 완전히 삭제하는 데 동의합니다 "
            "(chunks · Storage 원본 docx 포함, 되돌릴 수 없음)",
            key="bulk_delete_confirm",
        )

        if st.button(
            "⚠ 일괄 삭제 실행",
            type="primary",
            disabled=not confirm,
            key="bulk_delete_btn",
        ):
            # 1단계 — DB 일괄 삭제 (chunks CASCADE 자동)
            db_ok = False
            try:
                admin_sb.table("nexus_documents").delete().in_(
                    "id", selected_ids
                ).execute()
                db_ok = True
            except Exception as e:
                st.error(f"DB 삭제 실패: {e}")

            # 2단계 — Storage 원본 docx 일괄 정리 (best-effort)
            # ingest.py:93 와 동일한 버킷명 사용.
            storage_ok = True
            storage_err: str | None = None
            if db_ok and selected_storage_paths:
                try:
                    admin_sb.storage.from_("nexus-docs-original").remove(
                        selected_storage_paths
                    )
                except Exception as e:
                    storage_ok = False
                    storage_err = str(e)

            # 3단계 — 감사 로그 (다건이면 count + ids + titles 기록)
            if db_ok:
                _audit(
                    admin_sb,
                    action="document_bulk_delete",
                    target=f"{len(selected_ids)} docs",
                    details={
                        "count": len(selected_ids),
                        "ids": selected_ids,
                        "titles": selected_titles,
                        "storage_cleaned": storage_ok,
                    },
                )

            # 4단계 — 결과 표시 + rerun
            if db_ok and storage_ok:
                st.success(
                    f"✅ {len(selected_ids)}건 삭제 완료 (DB + Storage)"
                )
            elif db_ok and not storage_ok:
                st.warning(
                    f"⚠ DB 삭제 완료 ({len(selected_ids)}건), "
                    f"Storage 정리 부분 실패: {storage_err}"
                )
            if db_ok:
                st.rerun()


def _tab_radar(sb):
    st.subheader("📡 리스크 트렌드 레이더")
    days = st.slider("조회 기간(일)", 7, 90, 30)
    since = (dt.datetime.utcnow() - dt.timedelta(days=days)).isoformat()
    # PR-S1: query_logs SELECT 는 service_role 만 가능. anon sb 인자는
    # 다른 테이블(hotline_config_public 등) 호환 위해 시그니처 유지하되
    # query_logs 만 admin_sb 로 분리.
    admin_sb = _supabase_admin()
    if admin_sb is None:
        st.error(
            "⚠️ `SUPABASE_SERVICE_ROLE_KEY` 미설정 — 레이더 통계 사용 불가. "
            "(PR-S1 RLS 차단)"
        )
        return
    # select * 로 받아서 컬럼 부재(예: db/06 미적용)에 내성. 아래 모든 접근은
    # r.get("...") 로 안전 처리되므로 신규 컬럼이 없어도 동작 유지.
    # PostgREST 자체 에러(스키마 캐시 stale, RLS 등) 도 친화적으로 표시.
    try:
        rows = (
            admin_sb.table("query_logs")
              .select("*")
              .gte("ts", since)
              .execute()
              .data or []
        )
    except Exception as e:
        st.error(
            "⚠️ query_logs 조회에 실패했습니다. "
            "db/04~06 마이그레이션 적용 여부 또는 PostgREST 스키마 캐시(`notify pgrst, 'reload schema';`)를 확인해 주세요."
        )
        with st.expander("기술 세부정보", expanded=False):
            st.code(str(e))
        return
    if not rows:
        st.info("기간 내 질의 로그가 없습니다.")
        return

    # CSV 다운로드 — 회사 이관 시점 베타 결과 보고서 작성용
    st.download_button(
        f"📥 query_logs CSV 다운로드 ({len(rows)} rows, {days}일)",
        data=_rows_to_csv_bytes(rows),
        file_name=f"query_logs_{dt.date.today().isoformat()}.csv",
        mime="text/csv",
    )

    # 사규 카테고리별 인용 빈도 (검색 hit 기준)
    # query_logs.category(사용자 selectbox) 가 아니라 hit_categories(검색
    # 결과 chunks.categories 평탄화) 로 집계. multi-category chunk 는 각
    # 카테고리에 중복 카운트 — 사규 보강 우선순위 산출 시 정확도 우선.
    import itertools as _it
    hit_iter = _it.chain.from_iterable(
        (r.get("hit_categories") or []) for r in rows
    )
    cat_counts = Counter(c for c in hit_iter if c)
    st.markdown("#### 사규 카테고리별 인용 빈도 (검색 hit 기준)")
    if cat_counts:
        st.bar_chart(cat_counts)
    else:
        st.caption("hit_categories 데이터 없음 — db/08·09 마이그레이션 적용 후 신규 질의부터 집계됩니다.")
    st.caption(
        "1건 = 1 chunk hit. multi-category 사규는 각 카테고리에 중복 카운트. "
        "검색 실패(hit 0건)는 자동 제외."
    )

    # 일자별 카테고리 인용 추이
    series: dict[str, Counter[str]] = defaultdict(Counter)
    for r in rows:
        d = (r.get("ts") or "")[:10]
        if not d:
            continue
        for c in (r.get("hit_categories") or []):
            if c:
                series[d][c] += 1
    st.markdown("#### 일자별 카테고리 인용 추이")
    if series:
        flat = [{"date": d, **dict(c)} for d, c in sorted(series.items())]
        st.line_chart(flat, x="date")
    else:
        st.caption("hit_categories 데이터 없음.")

    # 부서별 슬라이스 (k-anonymity: 5 미만은 마스킹)
    # SSO 미도입 단계에서는 dept_hash 가 INSERT 시 미기입이라 의미 있는 결과가
    # 나오지 않음. 집계 로직은 그대로 두고 expander 로 접어둔다 — SSO 연동 시
    # 자동 활성화.
    with st.expander("🔒 부서별 통계 (SSO 도입 후 활성화)", expanded=False):
        st.info(
            "SSO 미도입 단계에서는 부서 식별 정보(dept_hash)가 채워지지 않아 "
            "표본이 없습니다. SSO 연동 후 자동 활성화됩니다."
        )
        st.markdown("#### 부서별 (k=5 보장)")
        dept_counts = Counter(r.get("dept_hash") or "(미식별)" for r in rows)
        safe = {k: v for k, v in dept_counts.items() if v >= 5}
        suppressed = sum(1 for v in dept_counts.values() if v < 5)
        if safe:
            st.bar_chart(safe)
        st.caption(f"k<5 슬라이스 {suppressed}건은 익명성 보호를 위해 표시하지 않습니다.")

    # 심각 사안 비율
    crit = sum(1 for r in rows if r.get("is_critical"))
    st.metric("심각 사안 비율", f"{(crit/len(rows))*100:.1f}%", delta=f"{crit}건")

    # 사용자 피드백 분포 (베타 답변 품질 KPI)
    st.markdown("#### 👍 / 👎 사용자 피드백")
    fb_up   = sum(1 for r in rows if r.get("feedback") == 1)
    fb_down = sum(1 for r in rows if r.get("feedback") == -1)
    fb_total = fb_up + fb_down
    c1, c2, c3 = st.columns(3)
    c1.metric("응답 수집률", f"{(fb_total/len(rows))*100:.1f}%",
              delta=f"{fb_total}/{len(rows)}건")
    c2.metric("👍 비율",
              f"{(fb_up/fb_total*100):.1f}%" if fb_total else "—",
              delta=f"{fb_up}건")
    c3.metric("👎 비율",
              f"{(fb_down/fb_total*100):.1f}%" if fb_total else "—",
              delta=f"{fb_down}건",
              delta_color="inverse")
    if fb_total < 10:
        st.caption("표본 부족 — 베타 참가자 의견을 더 모은 뒤 해석하세요.")

    # Provider 분포 (Gemini / Claude). fallback 발동률로 primary 안정성도 가늠.
    st.markdown("#### 🤖 챗봇 Provider 분포")
    prov_counts = Counter((r.get("chat_provider") or "(미식별)") for r in rows)
    if prov_counts:
        st.bar_chart(prov_counts)
    # provider 별 👍 비율 비교
    by_prov: dict[str, list[int]] = defaultdict(list)
    for r in rows:
        if r.get("feedback") in (1, -1):
            by_prov[r.get("chat_provider") or "(미식별)"].append(int(r["feedback"]))
    if by_prov:
        prov_table = []
        for p, vs in by_prov.items():
            up = sum(1 for v in vs if v == 1)
            down = sum(1 for v in vs if v == -1)
            tot = up + down
            prov_table.append({
                "provider": p,
                "응답 수": tot,
                "👍 %": f"{(up/tot*100):.1f}" if tot else "—",
                "👎 %": f"{(down/tot*100):.1f}" if tot else "—",
            })
        st.dataframe(prov_table, use_container_width=True, hide_index=True)

    # ── 응답 시간 분포 ──────────────────────────────────────
    # elapsed_ms 가 NULL 인 row(베타 보강 이전 데이터)는 집계 제외.
    st.markdown("#### ⏱️ 응답 시간 분포")
    elapsed_vals = [r.get("elapsed_ms") for r in rows if r.get("elapsed_ms") is not None]
    if elapsed_vals:
        import statistics as _stats
        sorted_e = sorted(elapsed_vals)
        n = len(sorted_e)
        p50 = sorted_e[int(n * 0.5)] if n else 0
        p95 = sorted_e[min(int(n * 0.95), n - 1)] if n else 0
        avg = _stats.mean(sorted_e) if sorted_e else 0
        m1, m2, m3 = st.columns(3)
        m1.metric("p50 (중앙값)", f"{p50:,} ms")
        m2.metric("p95", f"{p95:,} ms")
        m3.metric("평균", f"{avg:,.0f} ms")
        try:
            import plotly.express as px
            fig = px.histogram(elapsed_vals, nbins=20)
            fig.update_layout(
                xaxis_title="응답 시간 (ms)",
                yaxis_title="건수",
                showlegend=False,
                margin=dict(l=20, r=20, t=20, b=20),
            )
            st.plotly_chart(fig, use_container_width=True)
        except Exception as _e:
            st.caption(f"(plotly 차트 표시 실패 — 보조 KPI 만 표시) {_e}")
    else:
        st.info("응답 시간 데이터가 없습니다. db/07_radar_metrics.sql 마이그레이션 적용 여부를 확인하세요.")

    # ── Fallback 발동률 ────────────────────────────────────
    # primary LLM 이 transient 실패해 fallback provider 로 전환된 비율.
    # used_fallback 컬럼이 NULL/없는 과거 row 는 false 로 간주.
    st.markdown("#### 🔁 Fallback 발동률")
    fb_rows = [r for r in rows if r.get("used_fallback") is True]
    fb_pct = (len(fb_rows) / len(rows)) * 100 if rows else 0.0
    fc1, fc2 = st.columns([1, 2])
    fc1.metric("Fallback 발동 비율", f"{fb_pct:.1f}%", delta=f"{len(fb_rows)}/{len(rows)}건")
    # 일자별 fallback 건수
    fb_series: Counter[str] = Counter()
    for r in fb_rows:
        d = (r.get("ts") or "")[:10]
        if d:
            fb_series[d] += 1
    if fb_series:
        flat_fb = [{"date": d, "fallback 건수": c} for d, c in sorted(fb_series.items())]
        with fc2:
            st.line_chart(flat_fb, x="date")
    else:
        with fc2:
            st.caption("기간 내 fallback 발동 없음.")

    # ── 저신뢰도 응답률 ────────────────────────────────────
    # hit_chunk_ids 길이 0 = 사규 미발견 = 저신뢰도. 응답 문구 매칭 대신
    # 검색 hit 기준이 안정적.
    st.markdown("#### 📉 저신뢰도 응답률")
    def _is_low_conf(r: dict) -> bool:
        hits = r.get("hit_chunk_ids") or []
        return len(hits) == 0
    low_rows = [r for r in rows if _is_low_conf(r)]
    low_pct = (len(low_rows) / len(rows)) * 100 if rows else 0.0
    lc1, lc2 = st.columns([1, 2])
    lc1.metric("저신뢰도 응답 비율", f"{low_pct:.1f}%", delta=f"{len(low_rows)}/{len(rows)}건")
    # 사용자 선택 카테고리별 저신뢰도 비율 (표본 5건 미만 마스킹)
    # 의도된 분리: 본 패널은 hit_categories 가 아니라 사용자가 selectbox 로
    # 선택한 카테고리 기준. 검색 실패(hit 0건) 시 hit_categories 가 비어
    # 카테고리 식별 불가 → 사용자 선택값으로만 분포 가능.
    cat_total: Counter[str] = Counter()
    cat_low: Counter[str] = Counter()
    for r in rows:
        c = r.get("category") or "(미지정)"
        cat_total[c] += 1
        if _is_low_conf(r):
            cat_low[c] += 1
    cat_table = []
    for c, tot in cat_total.items():
        if tot < 5:
            cat_table.append({"카테고리": c, "저신뢰도 비율(%)": 0, "표본": "(표본 부족)"})
        else:
            cat_table.append({
                "카테고리": c,
                "저신뢰도 비율(%)": round((cat_low[c] / tot) * 100, 1),
                "표본": f"{cat_low[c]}/{tot}",
            })
    with lc2:
        st.markdown("##### 사용자가 어느 카테고리로 질의했을 때 검색 실패했는가")
        st.dataframe(cat_table, use_container_width=True, hide_index=True)
    st.caption(
        "저신뢰도 = 검색된 사규 청크 0건. hit 카테고리 식별 불가하므로 "
        "사용자 선택 카테고리 기준. 이 비율이 높은 카테고리는 사규 DB 보강 우선순위."
    )


def _tab_review(sb):
    st.subheader("🔬 Phase 3.5 도메인 검수")
    st.caption(
        "윤리·CSR·안전·정보보안팀이 검증 항목을 등록하고, 회차 단위로 자동 채점합니다. "
        "통과 기준 미달 시 Phase 3 회귀를 검토하세요."
    )

    sub_add, sub_csv, sub_list, sub_run, sub_runs = st.tabs(
        ["➕ 단건 등록", "📂 CSV 일괄", "📋 샘플 목록", "▶ 회차 실행", "📊 회차 결과"]
    )

    # ── 단건 등록 ──────────────────────────────────────────
    with sub_add:
        with st.form("review_add"):
            c1, c2 = st.columns(2)
            with c1:
                domain = st.selectbox(
                    "검수 도메인",
                    options=["윤리", "CSR", "안전", "정보보안", "공정거래",
                             "재무", "영업", "총무", "환경", "기타"],
                )
                category = st.selectbox(
                    "질의 카테고리", options=("자동",) + CATEGORIES, index=0
                )
                expected_critical = st.checkbox("심각 사안 응답 모드 트리거 기대")
                expected_kind = st.selectbox(
                    "심각 사안 종류 (선택)",
                    options=["", "safety", "harassment"],
                    disabled=not expected_critical,
                )
            with c2:
                created_by = st.text_input("작성자 (검수자명/팀)", value="")
                expected_citation = st.text_input(
                    "기대 출처 패턴 (예: 윤리강령 제4조)",
                    value="",
                )
                expected_keywords_raw = st.text_area(
                    "기대 키워드 (쉼표 구분, 답변에 포함되어야 함)",
                    value="",
                    height=80,
                )
                forbidden_keywords_raw = st.text_area(
                    "금지 키워드 (쉼표 구분, 답변에 포함되면 fail)",
                    value="",
                    height=60,
                    help="예: 인사 행정 질문에 'CSR팀' 이 등장하면 라우팅 오작동.",
                )
            question = st.text_area("평가용 질문", height=120)
            notes = st.text_area("메모 (선택)", height=80)
            submit = st.form_submit_button("등록", type="primary")

        if submit:
            if not question.strip():
                st.error("질문을 입력하세요.")
            else:
                kws  = [k.strip() for k in expected_keywords_raw.split(",")  if k.strip()]
                fkws = [k.strip() for k in forbidden_keywords_raw.split(",") if k.strip()]
                payload: dict = {
                    "category": None if category == "자동" else category,
                    "question": question.strip(),
                    "expected_keywords": kws,
                    "expected_citation": expected_citation.strip() or None,
                    "expected_critical": bool(expected_critical),
                    "expected_critical_kind": expected_kind or None,
                    "domain": domain,
                    "notes": notes.strip() or None,
                    "created_by": created_by.strip() or None,
                }
                if fkws:
                    payload["forbidden_keywords"] = fkws
                try:
                    sb.table("review_samples").insert(payload).execute()
                    st.success("샘플이 등록되었습니다.")
                except Exception as e:
                    if "forbidden_keywords" in str(e):
                        # db/07 미적용 — 컬럼 빼고 재시도
                        payload.pop("forbidden_keywords", None)
                        sb.table("review_samples").insert(payload).execute()
                        st.success("샘플이 등록되었습니다. (db/07 미적용 → 금지 키워드 무시)")
                    else:
                        raise
                _audit(_supabase_admin(), action="review_sample_add",
                       target=question.strip()[:60],
                       details={"domain": domain, "expected_critical": bool(expected_critical)})

    # ── CSV 일괄 ───────────────────────────────────────────
    with sub_csv:
        st.markdown(
            "**CSV 컬럼:** `domain, category, question, expected_keywords, "
            "expected_citation, expected_critical, expected_critical_kind, "
            "forbidden_keywords, notes`  \n"
            "`expected_keywords` / `forbidden_keywords` 는 `;` 로 구분, "
            "`expected_critical` 은 `true/false`."
        )

        from core.eval_template import REVIEW_CSV_COLUMNS, REVIEW_CSV_EXAMPLE_ROWS

        col_dl, col_help = st.columns([1, 3])
        with col_dl:
            st.download_button(
                "📥 CSV 양식 다운로드",
                data=_rows_to_csv_bytes(REVIEW_CSV_EXAMPLE_ROWS),
                file_name="DF_COMPASS_검수양식.csv",
                mime="text/csv",
                help="검수자에게 배포할 양식. UTF-8(BOM) 인코딩으로 Excel 한글 깨짐 없음. 예시 3건 포함.",
                use_container_width=True,
            )
        with col_help:
            with st.expander("ℹ️ 양식 작성 가이드", expanded=False):
                st.markdown(
                    """
**컬럼 9개 (모두 선택 — `question`만 필수)**

| 컬럼 | 설명 | 예시 |
|---|---|---|
| `domain` | 검수 도메인 (검수자 영역) | 윤리 / CSR / 안전 / 정보보안 / 공정거래 / 재무 / 영업 / 총무 / 환경 / 기타 |
| `category` | 사규 카테고리 | 공통 / CSR / 공정거래 / 정보보안 / 안전 / 재무 / 영업 / 총무 / 환경 |
| `question` | 검수용 질문 (필수) | 자유 텍스트 |
| `expected_keywords` | 답변에 등장해야 하는 키워드 | `선물;수수;신고` (`;` 세미콜론 구분) |
| `expected_citation` | 답변에 인용돼야 하는 사규/규정명 | `윤리강령` |
| `expected_critical` | 심각 사안 응답 모드 발동 기대 | `true` / `false` |
| `expected_critical_kind` | 심각 사안 종류 (`expected_critical=true` 시 권장) | `safety` / `harassment` / 빈 칸 |
| `forbidden_keywords` | 답변에 등장하면 안 되는 키워드 | `;` 세미콜론 구분 |
| `notes` | 검수자 메모 | 자유 텍스트 |

**작성 규칙**

- 한 행 = 한 검수 케이스
- 리스트 컬럼(`expected_keywords`, `forbidden_keywords`)은 반드시 `;` 세미콜론 구분 (콤마는 CSV 셀 구분자와 충돌하므로 사용 금지)
- `expected_critical`, `forbidden_keywords` 등 boolean·리스트는 빈 셀 허용
- 다운로드 양식의 예시 3건은 참고용. **실제 검수 시 삭제 후 작성하거나 덮어쓰기**
- 저장 시 Excel "CSV UTF-8 (쉼표로 분리)" 형식 권장. 양식이 BOM 포함 UTF-8이라 그대로 열고 저장하면 인코딩 유지됨
                    """
                )

        upl = st.file_uploader("CSV 업로드", type=["csv"])
        if upl:
            raw = upl.read()
            # Encoding fallback — UTF-8 BOM → UTF-8 → EUC-KR (한국 Excel 기본).
            # 어느 것도 실패하면 친화 메시지로 안내, traceback 노출 차단.
            text = None
            for enc in ("utf-8-sig", "utf-8", "euc-kr", "cp949"):
                try:
                    text = raw.decode(enc)
                    break
                except UnicodeDecodeError:
                    continue
            if text is None:
                st.error(
                    "⚠️ CSV 인코딩을 인식할 수 없습니다 (UTF-8 / EUC-KR 둘 다 실패). "
                    "Excel 에서 'CSV UTF-8' 형식으로 다시 저장해 주세요."
                )
                st.stop()
            reader = csv.DictReader(io.StringIO(text))
            rows: list[dict] = []
            for r in reader:
                cat = (r.get("category") or "").strip()
                fkws = [k.strip() for k in (r.get("forbidden_keywords") or "").split(";") if k.strip()]
                row = {
                    "domain": (r.get("domain") or "").strip() or None,
                    "category": cat if cat in CATEGORIES else None,
                    "question": (r.get("question") or "").strip(),
                    "expected_keywords": [
                        k.strip() for k in (r.get("expected_keywords") or "").split(";")
                        if k.strip()
                    ],
                    "expected_citation": (r.get("expected_citation") or "").strip() or None,
                    "expected_critical":
                        str(r.get("expected_critical","")).strip().lower() in ("1","true","y","yes"),
                    "expected_critical_kind":
                        (r.get("expected_critical_kind") or "").strip() or None,
                    "notes": (r.get("notes") or "").strip() or None,
                }
                if fkws:
                    row["forbidden_keywords"] = fkws
                rows.append(row)
            rows = [r for r in rows if r["question"]]
            st.write(f"미리보기: {len(rows)} 건")
            st.dataframe(rows[:20], use_container_width=True)
            if rows and st.button("일괄 등록", type="primary"):
                BATCH = 50
                try:
                    for i in range(0, len(rows), BATCH):
                        sb.table("review_samples").insert(rows[i:i+BATCH]).execute()
                    st.success(f"{len(rows)} 건 등록 완료")
                except Exception as e:
                    if "forbidden_keywords" in str(e):
                        # db/07 미적용 — 컬럼 빼고 재시도
                        for r in rows:
                            r.pop("forbidden_keywords", None)
                        for i in range(0, len(rows), BATCH):
                            sb.table("review_samples").insert(rows[i:i+BATCH]).execute()
                        st.success(f"{len(rows)} 건 등록 완료 (db/07 미적용 → 금지 키워드 무시)")
                    else:
                        raise

    # ── 샘플 목록 ──────────────────────────────────────────
    with sub_list:
        only_active = st.toggle("active 만 표시", value=True, key="rv_active")
        q = sb.table("review_samples").select("*").order("id", desc=True)
        if only_active:
            q = q.eq("is_active", True)
        rows = q.execute().data or []
        st.write(f"총 {len(rows)} 건")
        if rows:
            st.dataframe(rows, use_container_width=True)
            ids_to_disable = st.multiselect(
                "비활성화할 샘플 ID", options=[r["id"] for r in rows]
            )
            if ids_to_disable and st.button("비활성화"):
                sb.table("review_samples").update({"is_active": False}).in_(
                    "id", ids_to_disable
                ).execute()
                st.success(f"{len(ids_to_disable)} 건 비활성화")

            # forbidden_keywords 인라인 편집 — 회차 운영 중 false-positive
            # 발견 시 admin 이 즉시 보강 가능. ';' 로 구분.
            st.markdown("---")
            st.markdown("#### 🚫 금지 키워드(forbidden_keywords) 인라인 편집")
            row_for_edit = st.selectbox(
                "수정할 샘플",
                options=["(선택)"] + [f"#{r['id']} {r.get('question','')[:60]}" for r in rows],
                key="rv_fkw_select",
            )
            if row_for_edit != "(선택)":
                target_id = int(row_for_edit.split()[0].lstrip("#"))
                target_row = next((r for r in rows if r["id"] == target_id), None)
                if target_row is not None:
                    cur_fkw = target_row.get("forbidden_keywords") or []
                    new_fkw_raw = st.text_input(
                        "금지 키워드 (쉼표 또는 세미콜론 구분)",
                        value=", ".join(cur_fkw),
                        key=f"rv_fkw_input_{target_id}",
                    )
                    if st.button("저장", key=f"rv_fkw_save_{target_id}"):
                        new_list = [k.strip() for k in re.split(r"[,;]", new_fkw_raw) if k.strip()]
                        try:
                            sb.table("review_samples").update(
                                {"forbidden_keywords": new_list}
                            ).eq("id", target_id).execute()
                            _audit(_supabase_admin(), action="forbidden_keywords_update",
                                   target=str(target_id),
                                   details={"before": cur_fkw, "after": new_list})
                            st.success(f"#{target_id} 갱신: {new_list or '(비움)'}")
                            st.rerun()
                        except Exception as e:
                            if "forbidden_keywords" in str(e):
                                st.error("⚠️ db/07 미적용 — `forbidden_keywords` 컬럼이 없습니다.")
                            else:
                                st.error(f"실패: {e}")

    # ── 회차 실행 ──────────────────────────────────────────
    with sub_run:
        st.caption("선택한 샘플(또는 active 전체) 에 대해 챗봇을 실행하고 4지표로 자동 채점합니다.")
        active = (
            sb.table("review_samples").select("id,domain,question,category")
              .eq("is_active", True).order("id").execute().data or []
        )
        if not active:
            st.info("active 샘플이 없습니다.")
        else:
            opts = {f"#{r['id']} [{r.get('domain') or '-'}] {r['question'][:60]}": r["id"]
                    for r in active}
            chosen = st.multiselect("실행할 샘플 (비우면 전체)", list(opts.keys()))
            triggered_by = st.text_input("실행자", value="")
            if st.button("▶ 검수 실행", type="primary"):
                ids = [opts[k] for k in chosen] if chosen else None
                # 진행 표시 — 50+ 샘플 회차 시 사용자에게 진행 상태 노출.
                # 페이지가 죽지 않았다는 신호 + 중간 ETA 가늠.
                progress_box = st.empty()
                bar = st.progress(0.0, text="검수 시작...")

                def _on_progress(done: int, total: int) -> None:
                    pct = (done / total) if total else 0.0
                    bar.progress(pct, text=f"검수 진행 {done}/{total}")

                try:
                    res = run_review(
                        sb, sample_ids=ids,
                        triggered_by=triggered_by or None,
                        progress_cb=_on_progress,
                    )
                finally:
                    bar.empty()
                if not res.get("run_id"):
                    st.warning(res.get("message"))
                else:
                    st.success(f"회차 #{res['run_id']} 종료 — "
                               f"통과 {res['passed']}/{res['total']}")
                    st.json(res["metrics"])

    # ── 회차 결과 ──────────────────────────────────────────
    with sub_runs:
        runs = (
            sb.table("review_runs").select("*").order("id", desc=True).limit(20)
              .execute().data or []
        )
        if not runs:
            st.info("실행 이력이 없습니다.")
            return
        run_label = {f"#{r['id']} {r['started_at'][:19]} ({r['passed']}/{r['total']})": r
                     for r in runs}
        sel = st.selectbox("회차 선택", list(run_label.keys()))
        run = run_label[sel]
        col1, col2, col3 = st.columns(3)
        m = run.get("metrics") or {}
        col1.metric("통과율", f"{(m.get('pass_rate',0)*100):.1f}%")
        col2.metric("정확도 평균", f"{(m.get('accuracy_avg',0)*100):.1f}%")
        col3.metric("핫라인 누락률", f"{(m.get('hotline_missing_avg',0)*100):.1f}%")

        breached = threshold_breached(m, run.get("threshold") or {})
        if breached:
            st.error(
                "🚨 통과 기준 미달 항목: " + ", ".join(breached)
                + " — Phase 3 회귀 검토 필요"
            )
        else:
            st.success("✅ 모든 통과 기준 충족")

        results = (
            sb.table("review_results").select("*")
              .eq("run_id", run["id"]).order("id").execute().data or []
        )
        st.dataframe(results, use_container_width=True)
        # 실패 사유 분포
        all_reasons = [r for x in results for r in (x.get("failure_reasons") or [])]
        if all_reasons:
            st.markdown("#### 실패 사유 분포")
            st.bar_chart(Counter(all_reasons))


def _tab_hotlines(sb):
    st.subheader("📞 핫라인 / 안내 문구 관리")
    st.caption(
        "사내 익명제보 URL · 외부 상담채널 · 인사 라우팅 문구 등을 코드 수정 없이 즉시 반영합니다. "
        "인사 챗봇 오픈 시 `hr_chatbot_url` 만 채우면 자동 전환됩니다."
    )

    # hotline_config 는 RLS 적용 테이블. read · write 모두 service_role 키로
    # 만든 admin 클라이언트를 사용한다. anon 키는 RLS 정책상 SELECT 도
    # 차단되어 폼 prefill 이 비기 때문 (사용자 측 app.py 의 load_hotlines
    # read 만 별도 anon SELECT 정책으로 허용).
    admin_sb = _supabase_admin()
    if admin_sb is None:
        st.error(
            "SUPABASE_SERVICE_ROLE_KEY secret 이 설정되지 않았습니다. "
            "Streamlit Cloud → Manage app → Settings → Secrets 에서 추가 후 Reboot 하세요."
        )
        return

    rows = admin_sb.table("hotline_config").select("*").order("key").execute().data or []
    existing = {r["key"]: r for r in rows}

    LABELS = {
        "internal_report_url": "사내 익명 제보채널 URL",
        "external_hotline":    "외부 상담채널 (예: 고용노동부 1350)",
        "ethics_hotline_url":  "신세계면세점 핫라인 제보하기 URL",
        "hr_contact_text":     "인사 행정 라우팅 문구 (인사 규정·복리후생)",
        "csr_contact_text":    "신고·조사 라우팅 문구 (CSR팀 / 신세계면세점 핫라인)",
        "hr_chatbot_url":      "인사 챗봇 URL (채우면 자동 전환)",
    }

    with st.form("hotline_form"):
        edited: dict[str, str] = {}
        for key, label in LABELS.items():
            cur = (existing.get(key) or {}).get("value", "")
            if key == "hr_contact_text":
                edited[key] = st.text_area(label, value=cur, height=80)
            else:
                edited[key] = st.text_input(label, value=cur)
        submit = st.form_submit_button("저장", type="primary")

    if submit:
        if admin_sb is None:
            st.error(
                "SUPABASE_SERVICE_ROLE_KEY secret 이 설정되지 않았습니다. "
                "Streamlit Cloud → Manage app → Settings → Secrets 에서 추가하세요."
            )
            return
        # URL scheme 화이트리스트 — javascript:/data:/file: 등 차단 (XSS 방지).
        # 키 이름이 '_url' 로 끝나는 항목만 검증. 빈 값은 허용 (default fallback).
        invalid_urls: list[str] = []
        for key, val in edited.items():
            if key.endswith("_url") and val.strip():
                v = val.strip().lower()
                if not (v.startswith("https://") or v.startswith("http://")):
                    invalid_urls.append(f"{key}: '{val.strip()[:60]}'")
        if invalid_urls:
            st.error(
                "⚠️ URL 은 https:// (또는 http://) 로 시작해야 합니다. "
                "javascript: / data: / file: 등은 보안상 차단됩니다.\n\n"
                + "\n".join(f"- {u}" for u in invalid_urls)
            )
            return

        ts = dt.datetime.utcnow().isoformat()
        before_map = {k: (existing.get(k) or {}).get("value", "") for k in edited}
        for key, val in edited.items():
            admin_sb.table("hotline_config").upsert({
                "key": key,
                "value": val.strip(),
                "description": LABELS[key],
                "updated_at": ts,
            }).execute()
        changed = {k: {"before": before_map.get(k, ""), "after": v.strip()}
                   for k, v in edited.items()
                   if v.strip() != before_map.get(k, "")}
        if changed:
            _audit(admin_sb, action="hotline_update", target="hotline_config",
                   details={"changed": changed})
        st.success("저장되었습니다. (사용자 챗봇은 다음 응답부터 즉시 반영)")

    st.markdown("---")
    st.markdown("#### ➕ 사용자 정의 키 추가")
    with st.form("hotline_add"):
        c1, c2 = st.columns([1,2])
        with c1:
            new_key = st.text_input("key (영문/언더스코어)", value="")
        with c2:
            new_val = st.text_input("value", value="")
        new_desc = st.text_input("설명 (선택)", value="")
        if st.form_submit_button("추가"):
            if not new_key.strip():
                st.error("key 를 입력하세요.")
            elif admin_sb is None:
                st.error(
                    "SUPABASE_SERVICE_ROLE_KEY secret 이 설정되지 않았습니다."
                )
            else:
                admin_sb.table("hotline_config").upsert({
                    "key": new_key.strip(),
                    "value": new_val.strip(),
                    "description": new_desc.strip() or None,
                }).execute()
                st.success("추가되었습니다.")


def _tab_keywords(sb):
    st.subheader("🚨 심각 사안 키워드 사전")
    st.caption(
        "안전(safety) / 괴롭힘·성희롱(harassment) 트리거 키워드를 직접 관리합니다. "
        "도메인 전문가 검수 후 보강하세요."
    )
    rows = (
        sb.table("critical_keywords").select("*")
          .order("kind").order("keyword").execute().data or []
    )
    safety = [r for r in rows if r["kind"] == "safety"]
    harass = [r for r in rows if r["kind"] == "harassment"]

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("#### 🦺 safety")
        st.dataframe(safety, use_container_width=True, hide_index=True)
    with c2:
        st.markdown("#### 🛑 harassment")
        st.dataframe(harass, use_container_width=True, hide_index=True)

    with st.form("kw_add"):
        kc1, kc2, kc3 = st.columns([1, 2, 1])
        with kc1:
            kind = st.selectbox("종류", options=["safety", "harassment"])
        with kc2:
            keyword = st.text_input("키워드")
        with kc3:
            active = st.checkbox("활성", value=True)
        if st.form_submit_button("추가", type="primary"):
            if not keyword.strip():
                st.error("키워드를 입력하세요.")
            else:
                sb.table("critical_keywords").upsert({
                    "kind": kind, "keyword": keyword.strip(), "is_active": active,
                }).execute()
                _audit(_supabase_admin(), action="critical_keyword_upsert",
                       target=f"{kind}/{keyword.strip()}",
                       details={"is_active": active})
                st.success("추가/갱신되었습니다.")
                st.rerun()

    with st.expander("키워드 비활성화 / 활성화"):
        all_kws = [f"[{r['kind']}] {r['keyword']} ({'on' if r['is_active'] else 'off'})"
                   for r in rows]
        idx = st.multiselect("선택", options=list(range(len(rows))),
                             format_func=lambda i: all_kws[i])
        target_state = st.radio("상태", options=["활성화", "비활성화"], horizontal=True)
        if st.button("적용"):
            new_state = (target_state == "활성화")
            admin_sb = _supabase_admin()
            for i in idx:
                sb.table("critical_keywords").update(
                    {"is_active": new_state}
                ).eq("id", rows[i]["id"]).execute()
                _audit(admin_sb, action="critical_keyword_toggle",
                       target=f"{rows[i]['kind']}/{rows[i]['keyword']}",
                       details={"is_active": new_state})
            st.success(f"{len(idx)} 건 갱신")
            st.rerun()


# ── PR-Quality-2: 사규 vocabulary 추출 (paraphrase 변형 차단) ─────
# Supabase chunks 전체 → Gemini 1회 호출 → 핵심 명사 list. 사규는 1년
# stable → 1회 작업으로 끝. 산출물은 vocabulary.json 으로 commit, 다음
# 부팅부터 SYSTEM_PROMPT 의 [사규 vocabulary 강제] 섹션에 자동 inject.
_VOCAB_MAX_WORDS = 200
_VOCAB_CHUNK_FETCH_LIMIT = 5000  # 사규 18개 기준 충분 — pagination 포함


def _fetch_all_chunks_text(admin_sb) -> tuple[str, int]:
    """전체 active 사규/사례 청크 text 를 join 해 단일 문자열 반환.

    Supabase 기본 1000행 제한을 회피하기 위해 .range() 페이지네이션.
    Returns (joined_text, chunk_count).
    """
    page = 1000
    parts: list[str] = []
    count = 0
    for offset in range(0, _VOCAB_CHUNK_FETCH_LIMIT, page):
        rows = (
            admin_sb.table("nexus_chunks")
            .select("text")
            .range(offset, offset + page - 1)
            .execute()
            .data or []
        )
        if not rows:
            break
        for r in rows:
            t = (r.get("text") or "").strip()
            if t:
                parts.append(t)
                count += 1
        if len(rows) < page:
            break
    return "\n\n".join(parts), count


def _extract_vocab_via_gemini(chunks_text: str) -> list[str]:
    """Gemini 1회 호출로 핵심 명사·고유명사·전문용어 list 추출.

    JSON array 만 출력하도록 지시하지만 LLM 이 markdown fence 등을
    감싸는 경우가 있어 첫 [ ... ] 블록을 정규식으로 추출 후 파싱.
    """
    from google import genai
    from google.genai import types
    s = settings()
    if not s.gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY 미설정")
    cli = genai.Client(api_key=s.gemini_api_key)

    prompt = (
        "다음 사규 텍스트에서 핵심 명사·고유명사·전문용어 list 를 추출하세요.\n"
        f"- 최대 {_VOCAB_MAX_WORDS}개\n"
        "- 정확한 사규 용어 그대로 (조사·어미 제거, 명사 원형)\n"
        "- 짝 단어 (자진/익명, 내부/외부, 정기/수시, 사전/사후 등) 는\n"
        "  의미가 완전히 다르므로 구분해서 모두 포함\n"
        "- 일반 단어 ('회사', '직원' 등 너무 흔한 단어) 는 제외\n"
        "- 출력은 JSON array 한 가지 형식만. 다른 텍스트·설명·markdown 금지.\n"
        "  예: [\"안전관리\", \"자진 신고\", \"법인카드\", \"CREDO\"]\n\n"
        "<사규 텍스트>\n"
        f"{chunks_text}\n"
        "</사규 텍스트>"
    )
    cfg = types.GenerateContentConfig(temperature=0)
    res = cli.models.generate_content(
        model=s.chat_model, contents=prompt, config=cfg,
    )
    text = (res.text or "").strip()
    m = re.search(r"\[[\s\S]*\]", text)
    if not m:
        raise RuntimeError(f"Gemini 응답에서 JSON array 추출 실패: {text[:300]}")
    arr = json.loads(m.group(0))
    if not isinstance(arr, list):
        raise RuntimeError("Gemini 응답이 JSON array 아님")
    out: list[str] = []
    seen: set[str] = set()
    for item in arr:
        if not isinstance(item, str):
            continue
        w = item.strip()
        if not w or w in seen:
            continue
        seen.add(w)
        out.append(w)
    return out[:_VOCAB_MAX_WORDS]


def _tab_vocabulary(sb):
    st.subheader("🔤 사규 vocabulary 추출")
    st.caption(
        "PR-Quality-2 — 사규 핵심 용어 사전. SYSTEM_PROMPT 의 [사규 vocabulary "
        "강제] 섹션에 자동 inject 되어 paraphrase 변형 (안전관리 → 익명 등) 을 "
        "차단합니다. 사규는 1년 stable → 1회 추출로 충분."
    )

    from core.vocabulary import VOCABULARY_PATH, load_vocabulary
    current = load_vocabulary()

    st.markdown(f"**현재 vocabulary**: {len(current)} 개 단어")
    if current:
        with st.expander("현재 list 보기"):
            st.code(json.dumps(current, ensure_ascii=False, indent=2), language="json")
    else:
        st.info("아직 vocabulary 가 비어 있습니다. 아래 버튼으로 추출하세요.")

    st.markdown("---")
    st.markdown("### 📤 추출 (Gemini 1회 호출)")
    st.warning(
        "💰 LLM 호출 비용 — 1회만. 약 50~100K input 토큰 + 5K output 토큰 → "
        "**500~1000원 추정**. 사규 stable 하므로 추가 추출은 사규 추가·개정 "
        "시점에만 필요합니다."
    )

    extract_clicked = st.button(
        "🔤 사규 vocabulary 추출", type="primary", key="vocab_extract_btn",
    )
    if extract_clicked:
        admin_sb = _supabase_admin()
        if admin_sb is None:
            st.error(
                "SUPABASE_SERVICE_ROLE_KEY 미설정 — vocabulary 추출은 admin 권한 필요."
            )
        else:
            try:
                with st.spinner("청크 fetch 중…"):
                    joined, chunk_count = _fetch_all_chunks_text(admin_sb)
                if chunk_count == 0:
                    st.warning("적재된 사규 청크가 없습니다.")
                else:
                    st.caption(
                        f"청크 {chunk_count} 건 / 약 {len(joined):,} 자 → Gemini 호출"
                    )
                    with st.spinner("Gemini 호출 중… (수십 초 소요)"):
                        extracted = _extract_vocab_via_gemini(joined)
                    st.session_state["_extracted_vocab"] = extracted
                    _audit(
                        admin_sb,
                        action="vocabulary_extract",
                        details={"count": len(extracted), "chunk_count": chunk_count},
                    )
                    st.success(f"✅ {len(extracted)} 개 단어 추출 완료. 검토·보강하세요.")
            except Exception as e:
                st.error(f"추출 실패: {e}")

    extracted = st.session_state.get("_extracted_vocab")
    if extracted:
        st.markdown("### ✏️ 검토 / 보강")
        st.caption(
            "추출된 list 를 직접 편집해 finalize. JSON array 형식 유지. "
            "한 줄에 하나씩 권장 (가독성)."
        )
        default_text = json.dumps(extracted, ensure_ascii=False, indent=2)
        edited = st.text_area(
            "vocabulary (JSON array)",
            value=default_text,
            height=400,
            key="vocab_edit_area",
        )
        try:
            parsed = json.loads(edited)
            if not isinstance(parsed, list) or not all(isinstance(x, str) for x in parsed):
                st.error("JSON array of strings 형식 아님.")
            else:
                # dedup + strip
                clean: list[str] = []
                seen: set[str] = set()
                for w in parsed:
                    s2 = w.strip()
                    if s2 and s2 not in seen:
                        seen.add(s2)
                        clean.append(s2)
                st.caption(f"검증된 단어 수: **{len(clean)}** (dedup 후)")
                payload = json.dumps(clean, ensure_ascii=False, indent=2) + "\n"
                st.download_button(
                    "📥 vocabulary.json 다운로드",
                    data=payload.encode("utf-8"),
                    file_name="vocabulary.json",
                    mime="application/json",
                    key="vocab_download_btn",
                )
                st.info(
                    f"다운로드 받은 파일을 `core/vocabulary.json` 위치에 덮어쓴 뒤 "
                    f"git commit·push 하세요. 다음 부팅부터 SYSTEM_PROMPT 에 자동 "
                    f"반영됩니다.\n\n현재 파일 경로: `{VOCABULARY_PATH}`"
                )
        except json.JSONDecodeError as e:
            st.error(f"JSON 파싱 오류: {e}")


def _tab_consents(sb):
    st.subheader("📜 베타 참가자 동의 기록")
    st.caption(
        "정식 OPEN 전 베타 단계의 참가자별 사전 동의 기록입니다. "
        "회사 계정 이관 시 본 기록은 함께 폐기되며, 참가자 요청 시 개별 삭제 가능합니다."
    )
    try:
        rows = (
            sb.table("beta_consents").select("*")
              .order("consented_at", desc=True).limit(500)
              .execute().data or []
        )
    except Exception as e:
        st.error(
            "⚠️ beta_consents 조회에 실패했습니다. "
            "db/05_beta_consents.sql 적용 여부를 확인해 주세요."
        )
        with st.expander("기술 세부정보", expanded=False):
            st.code(str(e))
        return
    if not rows:
        st.info("아직 동의 기록이 없습니다.")
        return

    from collections import Counter as _Counter
    by_ver = _Counter(r.get("consent_version") or "?" for r in rows)
    by_env = _Counter(r.get("env") or "?" for r in rows)
    c1, c2, c3 = st.columns(3)
    c1.metric("총 동의 건수", f"{len(rows)}건")
    c2.metric("최신 버전 동의자",
              f"{by_ver.most_common(1)[0][1] if by_ver else 0}명",
              delta=by_ver.most_common(1)[0][0] if by_ver else "—")
    c3.metric("환경 분포",
              ", ".join(f"{k}:{v}" for k, v in by_env.most_common(3)) or "—")

    st.dataframe(rows, use_container_width=True)

    st.download_button(
        f"📥 beta_consents CSV 다운로드 ({len(rows)} rows)",
        data=_rows_to_csv_bytes(rows),
        file_name=f"beta_consents_{dt.date.today().isoformat()}.csv",
        mime="text/csv",
    )

    st.markdown("---")
    st.markdown("#### 🗑️ 동의 철회 / 삭제")
    ids = [r["id"] for r in rows]
    targets = st.multiselect(
        "삭제할 동의 기록 ID",
        options=ids,
        format_func=lambda i: next(
            f"#{r['id']} {r.get('participant','')} ({r.get('consent_version','')})"
            for r in rows if r["id"] == i
        ),
    )
    admin_sb = _supabase_admin()
    if targets and st.button("선택 삭제", type="primary"):
        if admin_sb is None:
            st.error("SUPABASE_SERVICE_ROLE_KEY 미설정 — 삭제 불가.")
        else:
            for tid in targets:
                admin_sb.table("beta_consents").delete().eq("id", tid).execute()
                _audit(admin_sb, action="beta_consent_delete",
                       target=str(tid))
            st.success(f"{len(targets)}건 삭제 완료")
            st.rerun()


def _tab_eval(sb):
    """PR-Q1.1: Retrieval Eval 진입점 — 브라우저 클릭 한 번으로 실행.

    eval/runner.py 의 run_all() 호출 → progress + 결과 표시 + JSON 다운로드.
    LLM 호출 X (retrieval 만). best_score 분포로 NEXUS_CONFIDENCE_HIGH /
    MEDIUM 튜닝 baseline 산출.

    sb 인자는 시그니처 일관성 유지 — runner 가 별도로 supabase_client() 를
    호출 (Streamlit secrets fallback 동일 경로).
    """
    st.subheader("🔍 Retrieval Eval")
    st.caption(
        "fixture 10개에 대해 hybrid_search 만 호출 (LLM 미호출). "
        "best_score 분포 = NEXUS_CONFIDENCE_HIGH / MEDIUM 튜닝 baseline. "
        "fixture 의 expected_sources 는 starter 추측치 — P/R 점수는 정정 후 신뢰."
    )

    last = st.session_state.get("eval_last_summary")

    col1, col2 = st.columns([1, 4])
    run_clicked = col1.button("▶ Eval 실행", key="eval_run_btn")
    if last is not None and not run_clicked:
        col2.caption(f"마지막 실행: {last.get('timestamp', '?')}")

    if run_clicked:
        try:
            from eval.runner import run_all
            from dataclasses import asdict
        except Exception as e:
            st.error(f"runner 임포트 실패: {e}")
            return

        progress_text = st.empty()
        progress_bar = st.progress(0)

        def _on_progress(i, total, r):
            progress_text.markdown(
                f"`{i}/{total}` — **{r.id}** ({r.category}) → "
                f"best_score `{r.best_score:.4f}` "
                f"{'✅' if r.passed else '❌'}"
            )
            progress_bar.progress(i / total)

        try:
            summary = run_all(on_progress=_on_progress)
        except RuntimeError as e:
            progress_text.empty()
            progress_bar.empty()
            st.error(f"Eval 실패: {e}")
            return
        except Exception as e:
            progress_text.empty()
            progress_bar.empty()
            st.exception(e)
            return

        progress_text.success(f"✅ 완료 — {summary.total}/{summary.total}")
        progress_bar.empty()
        # session_state 에 dict 로 저장 (rerun 후 dataclass 직렬화 안전).
        st.session_state["eval_last_summary"] = asdict(summary)
        last = st.session_state["eval_last_summary"]

    if last is None:
        st.info("아직 실행 결과 없음. ▶ Eval 실행 클릭.")
        return

    # 요약 — metric 박스 3개
    st.markdown("#### 요약")
    c1, c2, c3 = st.columns(3)
    c1.metric("Pass / Total", f"{last['passed']}/{last['total']}")
    c2.metric(
        "avg P / R",
        f"{last['avg_precision']:.2f} / {last['avg_recall']:.2f}",
    )
    c3.metric(
        "best_score (min·avg·max)",
        f"{last['score_min']:.4f} · {last['score_avg']:.4f} · {last['score_max']:.4f}",
    )

    # by category
    st.markdown("#### 카테고리별")
    cat_rows = []
    for cat, m in (last.get("by_category") or {}).items():
        cat_rows.append({
            "category": cat,
            "pass / total": f"{m['passed']}/{m['total']}",
            "avg P": f"{m['avg_precision']:.2f}",
            "avg R": f"{m['avg_recall']:.2f}",
            "score_avg": f"{m['score_avg']:.4f}",
        })
    if cat_rows:
        st.dataframe(cat_rows, hide_index=True, use_container_width=True)

    # per-fixture 표
    st.markdown("#### per-fixture")
    rows = []
    for r in (last.get("fixtures") or []):
        q = str(r.get("question", ""))
        rows.append({
            "id": r.get("id"),
            "category": r.get("category"),
            "question": q[:40] + ("…" if len(q) > 40 else ""),
            "P": f"{r.get('precision', 0):.2f}",
            "R": f"{r.get('recall', 0):.2f}",
            "best_score": f"{r.get('best_score', 0):.4f}",
            "hit": r.get("hit_count", 0),
            "pass": "✅" if r.get("passed") else "❌",
        })
    if rows:
        st.dataframe(rows, hide_index=True, use_container_width=True)

    # JSON 다운로드 — session_state dict 그대로 직렬화
    import json as _json
    ts_safe = str(last.get("timestamp", "unknown")).replace(":", "-")
    st.download_button(
        "📥 결과 JSON 다운로드",
        data=_json.dumps(last, ensure_ascii=False, indent=2).encode("utf-8"),
        file_name=f"eval_{ts_safe}.json",
        mime="application/json",
        key="eval_download_json",
    )


def _tab_pii(sb):
    """PR-Q5: PII filter 빠른 검증 도구.

    Streamlit cloud 재배포 없이 운영자가 query 변형을 즉시 확인할 수 있게
    한다. mask_pii 가 의도치 않게 일반 명사구 ("안전관리 책임자" 등) 를 잡지
    않는지, 진짜 PII (성씨+직책, 이메일, 전화번호 등) 는 정상 마스킹되는지
    한 화면에서 비교.

    sb 인자는 다른 탭과 시그니처 일관성 유지용 (DB 접근 없음).
    """
    import streamlit as st
    from core.pii_filter import mask_pii

    st.subheader("🔐 PII 필터 테스트")
    st.caption(
        "입력한 텍스트가 LLM·DB 에 저장되기 전 어떻게 마스킹되는지 확인합니다. "
        "mask 결과가 사용자 의도와 다르다면 false-positive 사례로 별도 보고."
    )

    presets = {
        "(직접 입력)": "",
        "PR-Q5 검증 1": "매장 안전관리 책임자?",
        "PR-Q5 검증 2": "자진 신고할 때?",
        "PR-Q5 검증 3": "괴롭힘 신고 절차",
        "PR-Q5 검증 4": "법인카드 사용 한도",
        "성씨+직책": "박 부장님 문의 드립니다",
        "풀네임+직책": "김민수 차장에게 보고",
        "이름 동반 매니저": "김 매니저 부정 행위 제보",
        "복성": "남궁민 팀장 회의",
        "이메일/전화 PII": "hong@example.com / 010-1234-5678",
        "사번": "사번 182491 직원",
        "부서명+이름": "재무팀 김 부장 결재",
    }
    preset = st.selectbox(
        "프리셋", list(presets.keys()), index=0, key="pii_test_preset",
    )
    default_text = presets[preset]
    text = st.text_area(
        "입력 텍스트",
        value=default_text,
        height=120,
        key=f"pii_test_input_{preset}",
        help="여러 줄 입력 가능. 빈 줄은 그대로 유지됩니다.",
    )

    extra_raw = st.text_input(
        "추가 마스킹 단어 (쉼표 구분, 옵션)",
        value="",
        key="pii_test_extra",
        help="예: '내부코드명, 프로젝트명'",
    )

    if st.button("마스킹 적용", type="primary", key="pii_test_run"):
        if not (text or "").strip():
            st.warning("입력 텍스트가 비어 있습니다.")
        else:
            extras = [t.strip() for t in (extra_raw or "").split(",") if t.strip()]
            masked = mask_pii(text, extras)
            col_in, col_out = st.columns(2)
            with col_in:
                st.caption("입력")
                st.code(text, language=None)
            with col_out:
                st.caption("마스킹 결과")
                st.code(masked, language=None)
            if masked == text:
                st.info("변경 없음 — 마스킹 대상 패턴이 검출되지 않았습니다.")
            else:
                st.success("마스킹 적용 완료.")

    with st.expander("🔍 현재 마스킹 정책 요약", expanded=False):
        st.markdown(
            "- **이메일·주민번호·휴대폰·일반전화·신용카드·계좌번호·차량번호**: "
            "표준 패턴으로 즉시 마스킹.\n"
            "- **사번**: '사번 ABC123' 같이 키워드 동반 또는 standalone 6자리 숫자.\n"
            "- **한국어 인명 + 직책**: 한국 표준 성씨 (단음절 ~60종 + 복성 7종) + "
            "선택적 1~2 자 이름 + 직책 (`부장`, `대리`, `매니저` 등) 만 매칭. "
            "일반 명사구 (`안전관리`, `책임자`, `수석` 등) 는 매칭 안 함.\n"
            "- **부서명**: `XX팀 / XX실 / XX본부` 등 접미어 패턴.\n"
            "- **직급(밴드)**: `밴드3`, `band 5`, `b1` 등.\n"
            "- **추가 단어**: 호출자가 `extra_terms` 로 임의 어휘 마스킹 가능."
        )


def _tab_search_compare(sb):
    """🔬 검색 비교 (Old vs New) — DF COMPASS Tier 1+2 디버그.

    USE_HYBRID_SEARCH 토글을 한 번의 입력으로 양쪽 다 호출해 결과를
    좌(Old: 기존 RPC, 쿼리 재작성 없음) / 우(New: query rewrite + 신규
    nexus_hybrid_search_v2) 로 비교한다. 각 경로 elapsed_ms 표기.

    어드민 게이트는 main() 의 _require_auth() 에 의해 이미 통과된 상태.
    """
    import time as _time
    import streamlit as st
    from core import retriever as _retriever
    from core.nexus_query_rewriter import (
        rewrite_query_for_retrieval,
        nexus_build_keyword_tsquery,
        nexus_classify_to_incident_nodes,
        REWRITE_MODEL_INFO,
    )

    st.subheader("🔬 검색 비교 (Old vs New)")
    st.caption(
        "동일 질문에 대해 기존 경로(USE_HYBRID_SEARCH=False)와 "
        "신규 경로(True, query rewrite + nexus_hybrid_search_v2) 결과를 "
        "나란히 비교합니다. 각 경로 top-5 와 소요 시간(ms) 표시."
    )

    # ── Pre-flight: Force-include RPC 검증 ────────────────
    with st.expander("🔬 Pre-flight: Force-include RPC 검증 (배포 후 가장 먼저)"):
        test_nodes_str = st.text_input(
            "테스트 노드 (콤마 구분)",
            value="고객상해, 응급대응, 인사사고, 직원상해, 고객관리, 시설안전, 안전관리",
            key="rpc_test_nodes",
        )
        if st.button("🚀 RPC 호출 테스트", key="rpc_test_btn"):
            test_nodes = [n.strip() for n in test_nodes_str.split(",") if n.strip()]
            if sb is None:
                st.error("Supabase 미설정.")
            else:
                # 1) Main RPC
                try:
                    resp = sb.rpc(
                        "nexus_force_include_chunks_by_incident_nodes",
                        {"p_nodes": test_nodes},
                    ).execute()
                    chunks = resp.data or []
                    st.success(f"✅ Main RPC 정상 — {len(chunks)} chunks 반환")
                    doc_dist: dict = {}
                    for c in chunks:
                        title = c.get("doc_title") or "?"
                        doc_dist[title] = doc_dist.get(title, 0) + 1
                    if doc_dist:
                        st.markdown("**Doc 별 분포**:")
                        for title, count in sorted(doc_dist.items(), key=lambda x: -x[1]):
                            st.text(f"  {title}: {count} chunks")
                except Exception as e:
                    st.error(f"❌ Main RPC 실패: {type(e).__name__}: {e}")
                    st.warning(
                        "→ Layer 2 (direct table) / Layer 3 (hardcoded title) fallback 가 라이브에서 동작 예정."
                    )
                # 2) Diagnostic RPC
                try:
                    resp2 = sb.rpc(
                        "nexus_diagnose_incident_node_matching",
                        {"p_nodes": test_nodes},
                    ).execute()
                    diag = resp2.data or []
                    matched_diag = [d for d in diag if d.get("matched_nodes")]
                    st.markdown(
                        f"**Diagnostic RPC**: `{len(matched_diag)}` 매칭 / "
                        f"`{len(diag)}` 전체 active+tagged"
                    )
                    for d in matched_diag:
                        st.text(
                            f"  {d.get('doc_title')} ← {d.get('matched_nodes')} "
                            f"({d.get('total_chunks')} chunks)"
                        )
                except Exception as e:
                    st.error(f"❌ Diagnostic RPC 실패: {type(e).__name__}: {e}")

    # ── 결정성 검증 ───────────────────────────────────────
    with st.expander("🎯 결정성 검증 (같은 query 다회 호출 비교)"):
        determinism_query = st.text_input(
            "검증할 query",
            value="고객이 매장에서 넘어졌어",
            key="determinism_query",
        )
        num_calls = st.number_input(
            "호출 횟수",
            min_value=2, max_value=5, value=3, key="determinism_calls",
        )
        if st.button("🔁 결정성 테스트 실행", key="determinism_run_btn"):
            if sb is None:
                st.error("Supabase 미설정.")
            else:
                results: list = []
                for i in range(int(num_calls)):
                    try:
                        r = _retriever.hybrid_search(
                            sb, question=determinism_query,
                            categories=None, top_k=5,
                        )
                        results.append({
                            "chunk_ids": [c.get("chunk_id") for c in r],
                            "doc_ids": [c.get("document_id") for c in r],
                            "unique_docs": {c.get("document_id") for c in r},
                        })
                    except Exception as e:
                        st.error(f"호출 {i+1} 실패: {e}")
                        results.append(None)
                valid = [r for r in results if r]
                if len(valid) < 2:
                    st.error("유효한 호출 결과 부족.")
                else:
                    ref_chunks = valid[0]["chunk_ids"]
                    all_chunks_match = all(
                        r["chunk_ids"] == ref_chunks for r in valid
                    )
                    ref_docs = valid[0]["unique_docs"]
                    all_docs_match = all(
                        r["unique_docs"] == ref_docs for r in valid
                    )
                    if all_chunks_match and all_docs_match:
                        st.success(
                            f"✅ 결정성 보장 — {len(valid)}회 호출 모두 "
                            f"동일 chunk 순서 + 동일 doc set "
                            f"({len(ref_docs)} unique docs)"
                        )
                    elif all_docs_match:
                        st.warning(
                            f"⚠️ Doc set 은 일관 ({len(ref_docs)} docs) — "
                            f"chunk 순서만 변동. 정렬 tiebreaker 점검 필요."
                        )
                        for i, r in enumerate(valid):
                            st.text(f"Call {i+1}: {r['chunk_ids']}")
                    else:
                        st.error(
                            f"❌ 비결정성 감지 — 호출 별 doc set 다름"
                        )
                        for i, r in enumerate(valid):
                            st.text(f"Call {i+1} docs: {r['unique_docs']}")

    q = st.text_input("질문", key="search_compare_q",
                      placeholder="예: 거래처가 명절 선물을 보내왔어요. 어떻게 하나요?")
    run = st.button("▶ 비교 실행", key="search_compare_run", type="primary")

    # 질문 변경 시 이전 결과 자동 reset (옛 결과 노출 방지).
    _last_q = st.session_state.get("cmp_last_question", "")
    if q and q != _last_q:
        st.session_state.pop("cmp_results", None)
        st.session_state.pop("cmp_synth_result", None)
        st.session_state["cmp_last_question"] = q

    # 비교 실행 → 결과를 session_state 에 저장.
    if run and q.strip():
        if sb is None:
            st.error("Supabase 미설정 — 검색 호출 불가.")
            return

        K = 5
        saved_flag = _retriever.USE_HYBRID_SEARCH

        # ── Old (기존 RPC, 쿼리 원문 그대로) ───────────────────
        old_err = None
        old_rows: list[dict] = []
        old_ms = 0.0
        try:
            _retriever.USE_HYBRID_SEARCH = False
            t0 = _time.perf_counter()
            old_rows = _retriever.hybrid_search(
                sb, question=q, categories=None, top_k=K,
            )
            old_ms = (_time.perf_counter() - t0) * 1000.0
        except Exception as e:
            old_err = str(e)
        finally:
            _retriever.USE_HYBRID_SEARCH = saved_flag

        # ── New (query rewrite + 신규 RPC) ─────────────────────
        new_err = None
        new_rows: list[dict] = []
        new_ms = 0.0
        rewritten = ""
        raw_response = ""
        try:
            rewritten, raw_response = rewrite_query_for_retrieval(q, return_debug=True)
            _retriever.USE_HYBRID_SEARCH = True
            t0 = _time.perf_counter()
            new_rows = _retriever.hybrid_search(
                sb, question=q, categories=None, top_k=K,
            )
            new_ms = (_time.perf_counter() - t0) * 1000.0
        except Exception as e:
            new_err = str(e)
        finally:
            _retriever.USE_HYBRID_SEARCH = saved_flag

        st.session_state["cmp_results"] = {
            "question": q,
            "K": K,
            "old_rows": old_rows, "old_ms": old_ms, "old_err": old_err,
            "new_rows": new_rows, "new_ms": new_ms, "new_err": new_err,
            "rewritten": rewritten, "raw_response": raw_response,
        }
        # 비교 새로 실행 시 이전 synth 결과 무효화.
        st.session_state.pop("cmp_synth_result", None)

    # 렌더링은 session_state 기반 (Streamlit rerun 안전).
    cmp = st.session_state.get("cmp_results")
    if not cmp:
        return

    q = cmp["question"]
    K = cmp["K"]
    old_rows = cmp["old_rows"]; old_ms = cmp["old_ms"]; old_err = cmp["old_err"]
    new_rows = cmp["new_rows"]; new_ms = cmp["new_ms"]; new_err = cmp["new_err"]
    rewritten = cmp["rewritten"]; raw_response = cmp["raw_response"]

    col_old, col_new = st.columns(2)

    with col_old:
        st.markdown(f"#### Old (기존, vector_only* — {old_ms:.0f} ms)")
        st.caption("retrieval_mode = `vector_only` (= 기존 nexus_hybrid_search RPC, 쿼리 재작성 없음)")
        if old_err:
            st.error(f"실패: {old_err}")
        elif not old_rows:
            st.info("결과 0건.")
        else:
            for i, r in enumerate(old_rows[:K], 1):
                with st.container(border=True):
                    st.markdown(
                        f"**{i}. {r.get('doc_title') or '(제목없음)'}** · "
                        f"`{r.get('article_no') or '-'}`"
                    )
                    st.caption(
                        f"similarity (score) = {float(r.get('score') or 0.0):.4f}"
                    )
                    txt = (r.get("text") or "").strip().replace("\n", " ")
                    st.write(txt[:200] + ("…" if len(txt) > 200 else ""))

    with col_new:
        st.markdown(f"#### New (Tier 1+2 — {new_ms:.0f} ms)")
        st.caption("retrieval_mode = `hybrid`")
        # 디버깅용 4줄 — 어느 단계가 실패하는지 한눈에 식별.
        _mi = REWRITE_MODEL_INFO
        st.markdown(
            f"**Gemini model / params**: `{_mi.get('model')}` · "
            f"max_output_tokens=`{_mi.get('max_output_tokens')}` · "
            f"temperature=`{_mi.get('temperature')}`"
        )
        st.markdown("**Gemini raw response (앞 500자)**:")
        st.code((raw_response or "")[:500] or "(empty)", language="text")
        st.markdown(f"**rewritten_query (postprocessed)**: `{rewritten}`")
        st.markdown(
            f"**tsquery passed to RPC**: `{nexus_build_keyword_tsquery(rewritten, original=q)}`"
        )
        # Incident-aware rerank — 사용자 질문에서 분류된 노드 노출.
        _classified = sorted(
            set(nexus_classify_to_incident_nodes(q or ""))
            | set(nexus_classify_to_incident_nodes(rewritten or ""))
        )
        st.markdown(
            f"**User incident nodes**: `{_classified or '(없음)'}`"
        )
        # Track C v2 — top-5 안의 intent force-include 청크 수 / 매칭 doc 수 요약 + source layer.
        _intent_force_chunks = [r for r in (new_rows or []) if r.get("force_included_by_intent")]
        _intent_force_docs = {r.get("document_id") for r in _intent_force_chunks if r.get("document_id")}
        _src = next(
            (r.get("force_include_source") for r in _intent_force_chunks if r.get("force_include_source")),
            "none",
        )
        if len(_intent_force_chunks) == 0:
            st.error(
                "❌ Force-include 0 chunks (top-5 기준) — **Track C 미작동 가능성**. "
                "위 Pre-flight RPC 검증 실행하세요."
            )
        else:
            st.success(
                f"✅ Force-include 작동 — "
                f"`{len(_intent_force_chunks)}` chunks · "
                f"`{len(_intent_force_docs)}` docs (top-5 기준) · "
                f"source `{_src}`"
            )

        _displayed_doc_dist: dict = {}
        for r in (new_rows or [])[:K]:
            title = r.get("doc_title") or "?"
            _displayed_doc_dist[title] = _displayed_doc_dist.get(title, 0) + 1
        with st.expander(
            f"📑 Top-{K} doc set ({len(set(_displayed_doc_dist.keys()))} unique docs)"
        ):
            for title, count in sorted(_displayed_doc_dist.items(), key=lambda x: -x[1]):
                st.text(f"  {title}: {count} chunks")
        if new_err:
            st.error(f"실패: {new_err}")
        elif not new_rows:
            st.info("결과 0건.")
        else:
            for i, r in enumerate(new_rows[:K], 1):
                with st.container(border=True):
                    st.markdown(
                        f"**{i}. {r.get('doc_title') or '(제목없음)'}** · "
                        f"`{r.get('article_no') or '-'}`"
                    )
                    boost_caption = ""
                    if r.get("incident_boost_applied"):
                        matched = ", ".join(r.get("matched_incident_nodes") or [])
                        boost_caption = f" · ⚡ +{_retriever.INCIDENT_BOOST:.2f} (매칭: {matched})"
                    st.caption(
                        f"rrf_score = {float(r.get('score') or 0.0):.4f}{boost_caption}"
                    )
                    if r.get("emergency_chunk_boost_applied"):
                        kws = ", ".join(r.get("matched_emergency_keywords") or [])
                        st.caption(
                            f"🚑 +{_retriever.EMERGENCY_CHUNK_BOOST:.2f} 응급키워드 매칭: {kws}"
                        )
                    _proc_count = int(r.get("procedure_keyword_count") or 0)
                    if _proc_count > 0:
                        _proc_matched = r.get("matched_procedure_keywords") or []
                        _bonus = _retriever.PROCEDURE_KEYWORD_WEIGHT * _proc_count
                        _preview = ", ".join(_proc_matched[:5])
                        _suffix = f" 외 {_proc_count - 5}개" if _proc_count > 5 else ""
                        st.caption(
                            f"📋 +{_bonus:.2f} 절차키워드 `{_proc_count}`개 매칭: {_preview}{_suffix}"
                        )
                    if r.get("chunk_incident_boost_applied"):
                        nodes = ", ".join(r.get("matched_chunk_incident_nodes") or [])
                        st.caption(
                            f"⚡⚡ chunk-level +{_retriever.INCIDENT_BOOST:.2f} (매칭: {nodes})"
                        )
                    if r.get("force_included"):
                        st.caption(
                            f"🔒 Force-included +{_retriever.EMERGENCY_FORCE_INCLUDE_BOOST:.2f} (chunk-level incident node 매칭)"
                        )
                    if r.get("force_included_by_intent"):
                        _src_chunk = r.get("force_include_source") or "?"
                        st.caption(
                            f"🔒 Intent force-include +{_retriever.FORCE_INCLUDE_DOC_BOOST:.2f} "
                            f"(source=`{_src_chunk}`)"
                        )
                    txt = (r.get("text") or "").strip().replace("\n", " ")
                    st.write(txt[:200] + ("…" if len(txt) > 200 else ""))

    # ── Synthesis 검증 (Layer 4) — session_state 기반 ──────
    with st.expander("🔍 Synthesis 검증 (LLM 답변 + 구조화 자동 보정)"):
        verify_via_live = st.checkbox(
            "라이브 흐름으로 검증 (ask() 전체 파이프라인 — 후처리 + validator 포함)",
            value=False,
            key="synth_verify_live_mode",
        )
        if st.button("🤖 답변 생성 + 구조화 검증", key="synth_verify_btn"):
            try:
                from core.prompts import SYSTEM_PROMPT, build_user_prompt
                from core.chatbot import _gen_gemini, ask as _live_ask
                from core.synthesis_validator import (
                    validate_and_repair_answer,
                    extract_force_included_titles,
                    _build_structured_regulation_section,
                    _universal_sop_chunks,
                )

                if verify_via_live:
                    # 라이브 흐름 — retrieval + ask 전체. validator 가 이미 ask 내부에서
                    # 호출됐으므로 여기서는 결과만 받아 검증·표시.
                    ans = _live_ask(sb, question=q)
                    repaired = ans.text
                    repairs: list = ["live mode: validator already applied inside ask()"]
                    _model = "live (ask pipeline)"
                else:
                    user_prompt = build_user_prompt(q, list(new_rows or []))
                    raw_text, _, _model = _gen_gemini(
                        SYSTEM_PROMPT, user_prompt, include_thinking=False,
                    )
                    _user_nodes = nexus_classify_to_incident_nodes(q or "")
                    repaired, repairs = validate_and_repair_answer(
                        raw_text, chunks=new_rows, user_incident_nodes=_user_nodes,
                    )
                _user_nodes = nexus_classify_to_incident_nodes(q or "")
                _force_titles = extract_force_included_titles(new_rows)
                st.session_state["cmp_synth_result"] = {
                    "model": _model,
                    "raw_text": raw_text,
                    "repaired": repaired,
                    "repairs": repairs,
                    "user_nodes": _user_nodes,
                    "force_titles": _force_titles,
                    "sop_map": _universal_sop_chunks(new_rows or []),
                    "structured": _build_structured_regulation_section(
                        new_rows or [], user_incident_nodes=_user_nodes,
                    ),
                }
            except Exception as e:
                st.error(f"답변 생성 실패: {type(e).__name__}: {e}")
                import traceback
                st.code(traceback.format_exc())

        # synth 결과 렌더링도 session_state 기반 (rerun 안전).
        sr = st.session_state.get("cmp_synth_result")
        if sr:
            st.success(f"✅ 답변 생성 완료 (model=`{sr['model']}`)")
            if sr["repairs"]:
                st.warning(f"🛠 자동 보정 적용: {len(sr['repairs'])}건")
                for rep in sr["repairs"]:
                    st.text(f"  • {rep}")
            else:
                st.info("자동 보정 없음 — LLM 답변이 규칙을 통과.")

            st.markdown("**답변 본문 (보정 후):**")
            st.markdown(sr["repaired"])

            sop_map = sr["sop_map"]
            col_a, col_b = st.columns(2)
            col_a.metric(
                "일반 사건사고 청크",
                len(sop_map["(공통) 일반 사건사고 보고지침"]),
            )
            col_b.metric(
                "중대 사건사고 청크",
                len(sop_map["(공통) 중대 사건사고 보고지침"]),
            )

            if sr["structured"]:
                st.markdown("**구조화 추출 결과 (validator 가 주입 시도하는 내용):**")
                st.code(sr["structured"], language=None)
            else:
                st.warning("⚠️ 구조화 추출 실패 — universal SOP 청크 부족 또는 매칭 0건")

            checks = (
                ("▼ 사건 분류", "분류"),
                ("▼ 일반 vs 중대", "판정 기준"),
                ("▼ 일반 사건사고 보고 절차", "일반 절차"),
                ("▼ 중대 사건사고 보고 절차", "중대 절차"),
            )
            st.markdown("**4단계 구조 포함 여부 (보정 후 답변 기준):**")
            for marker, label in checks:
                if marker in sr["repaired"]:
                    st.text(f"  ✅ {label} 포함")
                else:
                    st.text(f"  ❌ {label} 누락")

            st.markdown(f"**Force-included docs**: `{sr['force_titles'] or '(없음)'}`")
            cited_count = sum(1 for t in sr["force_titles"] if t in sr["repaired"])
            if sr["force_titles"]:
                if cited_count == len(sr["force_titles"]):
                    st.success(
                        f"✅ 모든 force-included doc 인용됨 "
                        f"({cited_count}/{len(sr['force_titles'])})"
                    )
                elif cited_count > 0:
                    st.warning(
                        f"⚠️ 부분 인용 ({cited_count}/{len(sr['force_titles'])})"
                    )
                else:
                    st.error(
                        "❌ Force-included doc 0개 인용"
                    )

            forbidden_found: list = []
            for pat in (
                "[참조: 검색 결과 없음]",
                "관련 사규에서 확인되지 않습니다",
                "해당 유형 문서가 검색되지 않았습니다",
            ):
                if pat in sr["repaired"]:
                    forbidden_found.append(pat)
            if forbidden_found:
                st.error(f"❌ FORBIDDEN PATTERNS 잔존: {forbidden_found}")
            else:
                st.success("✅ FORBIDDEN PATTERNS 없음")

    # ── Claude Opus judge 검증 (Phase 0) ─────────────────
    with st.expander("🧑‍⚖️ Claude Opus judge 검증 (Phase 0)", expanded=False):
        st.markdown(
            "Gemini 답변 + 검색 청크를 Claude Opus 가 청크와 매칭 검증.  \n"
            "Phase 0: customer injury (인사사고/고객상해) 만 golden 매핑 정의됨."
        )

        judge_question = st.text_input(
            "검증할 질문",
            value=q if "cmp_results" in st.session_state else "",
            key="claude_judge_question",
        )

        col_j1, col_j2 = st.columns([1, 3])
        with col_j1:
            run_judge = st.button(
                "🧑‍⚖️ 실행", key="claude_judge_run", type="primary",
            )
        with col_j2:
            st.caption(
                "Live ask() 호출 → 답변 + 청크 → Claude Opus judge → VerificationReport"
            )

        if run_judge and judge_question:
            try:
                from core.chatbot import ask as _live_ask
                from core.retriever import hybrid_search as _hybrid_search
                from core.verification.claude_judge import verify_with_claude
                from core.verification.reports import render_report_markdown
                from core.taxonomy.golden_citations import lookup_golden

                with st.spinner("Gemini 답변 생성 + 청크 검색..."):
                    if sb is None:
                        st.error("Supabase 미설정 — 검증 불가.")
                        st.stop()
                    ans_obj = _live_ask(
                        sb, question=judge_question, category=None,
                    )
                    live_answer = ans_obj.text or ""
                    live_chunks = ans_obj.contexts or []
                    if not live_chunks:
                        # fallback — ask 가 contexts 비었으면 직접 retrieval
                        live_chunks = _hybrid_search(
                            sb, question=judge_question,
                            categories=None, top_k=10,
                        )
                    incident_nodes = sorted(set(
                        nexus_classify_to_incident_nodes(judge_question or "")
                    ))

                st.markdown("---")
                st.markdown("### 📝 Gemini 답변")
                st.markdown(live_answer or "*(빈 답변)*")
                st.caption(
                    f"청크 {len(live_chunks)}개 · incident_nodes: {incident_nodes}"
                )

                golden = lookup_golden(incident_nodes)
                if not golden:
                    st.warning(
                        f"⚠️ incident_nodes {incident_nodes} 에 매칭되는 golden 미정의. "
                        f"Phase 0 지원 카테고리: customer_injury (고객상해/인사사고). "
                        f"검증 진행되지만 coverage_gaps 검사는 skip."
                    )
                else:
                    st.info(f"🎯 Golden 매핑: **{golden.get('description', '')}**")

                # === 🔬 진단 (PR diag/phase-0-chunk-count-discovery) ===
                # 같은 incident_nodes 인데 phrasing 마다 chunk 수가 다른 원인 분기:
                #   (A) retriever bug — hybrid_search 자체가 universal SOP 누락
                #   (B) admin bug — admin 추출 단계에서 chunks 손실
                st.markdown("---")
                st.markdown("### 🔬 진단 — chunk extraction path")
                st.write(
                    f"**ask() return type:** `{type(ans_obj).__name__}` "
                    f"(Answer dataclass)"
                )
                _ans_attrs = {
                    "text": f"str(len={len(ans_obj.text or '')})",
                    "contexts": (
                        f"list[{len(ans_obj.contexts or [])}]"
                        if isinstance(ans_obj.contexts, list)
                        else type(ans_obj.contexts).__name__
                    ),
                    "is_critical": ans_obj.is_critical,
                    "elapsed": f"{ans_obj.elapsed:.2f}s",
                }
                for _k, _v in _ans_attrs.items():
                    st.write(f"  - `{_k}`: {_v}")
                if ans_obj.contexts and isinstance(ans_obj.contexts[0], dict):
                    st.write(
                        f"  - sample chunk keys: "
                        f"`{sorted(ans_obj.contexts[0].keys())}`"
                    )

                st.write(
                    f"\n**Claude judge 로 전달된 live_chunks:** "
                    f"`{len(live_chunks) if live_chunks else 0}`개"
                )
                if live_chunks:
                    for _i, _c in enumerate(live_chunks):
                        if not isinstance(_c, dict):
                            continue
                        _cid = _c.get("id") or _c.get("chunk_id") or "?"
                        _cid_short = str(_cid)[:8] if _cid != "?" else "?"
                        st.write(
                            f"  {_i+1}. **{_c.get('doc_title', '?')}** / "
                            f"chunk_idx=`{_c.get('chunk_idx', '?')}` / "
                            f"id=`{_cid_short}` / "
                            f"text_len={len(_c.get('text', '') or '')}"
                        )

                # direct hybrid_search 비교 호출
                _direct_chunks: list = []
                try:
                    _direct_chunks = _hybrid_search(
                        sb, question=judge_question,
                        categories=None, top_k=10,
                    )
                    st.write(
                        f"\n**direct hybrid_search(top_k=10):** "
                        f"`{len(_direct_chunks)}`개"
                    )
                    _direct_titles = sorted({
                        c.get("doc_title", "?") for c in _direct_chunks
                        if isinstance(c, dict)
                    })
                    for _t in _direct_titles:
                        _count = sum(
                            1 for c in _direct_chunks
                            if isinstance(c, dict) and c.get("doc_title") == _t
                        )
                        st.write(f"  - {_t}: {_count}개")
                except Exception as _diag_e:
                    st.write(f"  ⚠️ direct hybrid_search 실패: {_diag_e}")

                # Universal SOP 분기 판정
                _UNIVERSAL_SOP_TITLES = {
                    "(공통) 일반 사건사고 보고지침",
                    "(공통) 중대 사건사고 보고지침",
                }
                _live_universal = {
                    c.get("doc_title") for c in (live_chunks or [])
                    if isinstance(c, dict)
                } & _UNIVERSAL_SOP_TITLES
                _direct_universal = {
                    c.get("doc_title") for c in _direct_chunks
                    if isinstance(c, dict)
                } & _UNIVERSAL_SOP_TITLES
                st.write("\n**Universal SOP 포함 여부**")
                st.write(
                    f"  - live_chunks (judge 입력): {_live_universal or '❌ 없음'}"
                )
                st.write(
                    f"  - direct hybrid_search: {_direct_universal or '❌ 없음'}"
                )

                # 결론 시그널
                if not _live_universal and _direct_universal:
                    st.error(
                        "🚨 (B) admin 도구 bug — direct hybrid_search 는 "
                        "universal SOP 가져오는데 live_chunks 추출이 누락. "
                        "admin extraction 수정 필요."
                    )
                elif not _live_universal and not _direct_universal:
                    st.error(
                        "🚨 (A) retriever bug — hybrid_search 자체가 "
                        "universal SOP 리턴 안 함. retriever enrichment "
                        "일관성 수정 필요."
                    )
                elif _live_universal == _direct_universal:
                    st.success(
                        "✅ admin 추출 = direct hybrid_search 일치 — "
                        "phrasing 별 retrieval variance 자체는 진짜 "
                        "(다른 원인 조사 필요)"
                    )
                else:
                    st.warning(
                        f"⚠️ 부분 불일치 — live={_live_universal} / "
                        f"direct={_direct_universal}"
                    )
                st.markdown("---")
                # === 진단 끝 — 기존 verify_with_claude 호출 이어짐 ===

                with st.spinner("Claude Opus judge 호출 중..."):
                    report = verify_with_claude(
                        query=judge_question,
                        chunks=live_chunks,
                        answer=live_answer,
                        golden_citations=golden,
                        incident_nodes=incident_nodes,
                    )

                st.markdown("---")
                st.markdown(render_report_markdown(report))

                with st.expander("🔬 Raw Claude response (디버그)"):
                    st.code(report.raw_response or "<none>", language="json")
            except Exception as e:
                import traceback
                st.error(f"검증 실패: {type(e).__name__}: {e}")
                st.code(traceback.format_exc())


def main():
    _require_auth()

    # 4px 신세계 레드 상단 프레임 (브랜드 일관성)
    st.markdown('<div class="nx-topbar"></div>', unsafe_allow_html=True)

    sb = _supabase()
    if sb is None:
        st.error("⚠️ Supabase 설정이 없습니다.")
        st.stop()

    col_title, col_logout = st.columns([8, 1])
    col_title.title("🛠️ DF COMPASS · Admin")
    if col_logout.button("로그아웃", key="admin_logout"):
        st.session_state["admin_authenticated"] = False
        st.rerun()

    _render_query_logs_health_banner(sb)

    tabs = st.tabs([
        "📥 업로드", "📚 버전", "📡 레이더",
        "🔬 검수 (Phase 3.5)", "📞 핫라인", "🚨 키워드",
        "🔤 vocabulary", "📜 동의",
        "🔍 Eval", "🔐 PII 테스트",
        "🔬 검색 비교",
    ])
    with tabs[0]: _tab_upload(sb)
    with tabs[1]: _tab_versions(sb)
    with tabs[2]: _tab_radar(sb)
    with tabs[3]: _tab_review(sb)
    with tabs[4]: _tab_hotlines(sb)
    with tabs[5]: _tab_keywords(sb)
    with tabs[6]: _tab_vocabulary(sb)
    with tabs[7]: _tab_consents(sb)
    with tabs[8]: _tab_eval(sb)
    with tabs[9]: _tab_pii(sb)
    with tabs[10]: _tab_search_compare(sb)


if __name__ == "__main__":
    main()
