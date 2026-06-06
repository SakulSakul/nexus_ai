"""DF COMPASS 답변 부가 렌더 헬퍼 — app.py 에서 분리(동작 무변경).

신뢰도/메타/카테고리/추천/역질문/마무리/근거 칩. _KIND_BADGE_TEXT 동반.
"""

import streamlit as st


# PR-fix-confidence-display(#336-4): 디스플레이용 신뢰도 강등 마커.
#   답변 본문이 "직접 매칭되는 사규 미발견"(prompts.py rule-4 template)을 명시하면
#   배지는 '높음(high)' 으로 표시하지 않는다. 내부 confidence(_maybe_prefix_system_prompt,
#   classify_button HR-branch 입력)는 **절대 건드리지 않는다** — 표시값만 보정.
_DISPLAY_CONF_DOWNCAP_MARKERS: tuple[str, ...] = (
    "본 query 에 직접 매칭되는 사규가 검색되지 않았습니다",  # 옛 (history replay)
    "질문하신 내용에 직접 해당하는 사규를 찾지 못했습니다",  # 신규
)


def _verdict_trustworthy(answer_text: str | None) -> bool:
    """평결카드(stance pill) 렌더 가능 여부 — graceful('직접 매칭 미발견') 답변은 False.

    answer_text 가 None/빈문자열이면 True (보수적 — 호출자가 별도 가드를 책임).
    False 일 때 호출 측은 _verdict_dict 를 None 으로 유지해 단일 변수 흐름이
    live/history/replay 3 경로 모두 중립 브랜드 헤더 fallback 으로 보내게 한다.
    _DISPLAY_CONF_DOWNCAP_MARKERS 와 같은 신호를 공유(prompts.py rule-4 template).
    """
    if not answer_text:
        return True
    return not any(m in answer_text for m in _DISPLAY_CONF_DOWNCAP_MARKERS)


def _displayed_confidence(confidence: str, answer_text: str | None) -> str:
    """디스플레이용 신뢰도. graceful(직접 매칭 미발견) 답변은 high → medium 강등.

    cap 대상은 high 만 — low/medium 은 그대로(이미 신중 톤). answer_text 없으면 변경 X.
    내부 confidence 값은 호출자가 변경하지 않음 — display path 한 곳에서만 보정.
    """
    if confidence != "high" or not answer_text:
        return confidence
    if any(m in answer_text for m in _DISPLAY_CONF_DOWNCAP_MARKERS):
        return "medium"
    return confidence


_KIND_BADGE_TEXT = {
    "rule":    "사규",
    "case":    "사례",
    "penalty": "징계기준",
}


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
    # PR-fix-confidence-display(#336-4): graceful 답변 = high 표시 금지.
    confidence = _displayed_confidence(confidence, answer_text)
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
        f"padding:8px 0 6px;border-top:1px solid var(--c-border);margin-top:6px;"
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
