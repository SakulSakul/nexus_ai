"""DF COMPASS 피드백/액션/모드 버튼 — app.py 에서 분리(동작 무변경).

다시답변·관련질문·신고안내 액션, 도움됨/아쉬움 피드백, 멀티턴 모드. _FB_REASONS_* 동반.
"""

import streamlit as st
from ui.panels import (
    _render_report_channels_panel, _render_clean_report_panel, _render_hr_inquiry_panel,
)


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
        'color:#9A968D;margin:8px 0 6px 2px;">다음 단계 예측</div>',
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
