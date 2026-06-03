"""DF COMPASS 신고/문의 안내 패널 — app.py 에서 분리(동작 무변경).

신고방법(SRMS)·클린신고(SHRS)·인사교육팀 문의 3종. hotlines dict 만 입력, st 출력.
"""

import streamlit as st


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
