"""Streamlit chat UI + session_state."""
import html

import streamlit as st

from src.frontend.citation_card import render_citations
from src.service.models import Answer, AnswerStatus
from src.service.rag import RAGService


_HISTORY_KEY = "df_chat_history"


def render_chat_page(rag: RAGService) -> None:
    _init_state()

    st.title("🧭 DF COMPASS")
    st.caption("사규 검색 보조 도구 · 베타")

    _render_history()

    user_input = st.chat_input("사규에 대해 질문하세요 (예: 거래처 선물을 받아도 되나요?)")
    if user_input:
        _handle_new_query(rag, user_input)


def _init_state() -> None:
    if _HISTORY_KEY not in st.session_state:
        st.session_state[_HISTORY_KEY] = []


def _append_history(query: str, answer: Answer) -> None:
    st.session_state[_HISTORY_KEY].append({
        "query": query,
        "answer": answer,
    })


def _render_history() -> None:
    for entry in st.session_state[_HISTORY_KEY]:
        with st.chat_message("user"):
            st.write(entry["query"])
        with st.chat_message("assistant"):
            _render_answer(entry["answer"])


def _render_answer(answer: Answer) -> None:
    css_class = "df-answer"
    if answer.status == AnswerStatus.INSUFFICIENT:
        css_class += " insufficient"
    elif answer.status == AnswerStatus.ERROR:
        css_class += " error"

    safe_text = html.escape(answer.text)
    st.markdown(
        f'<div class="{css_class}">{safe_text}</div>',
        unsafe_allow_html=True,
    )

    # 디버그 — error 시 실제 stack trace 노출 (베타 단계 한정)
    if answer.status == AnswerStatus.ERROR and answer.error_message:
        with st.expander("🔍 디버그 정보 (개발자용)"):
            st.code(answer.error_message, language="text")

    meta_parts = []
    if answer.elapsed_ms:
        meta_parts.append(f"⏱ {answer.elapsed_ms}ms")
    if answer.chunks_retrieved:
        meta_parts.append(f"🔍 {answer.chunks_retrieved} chunks")
    if answer.status != AnswerStatus.OK:
        meta_parts.append(f"⚠️ {answer.status.value}")
    if meta_parts:
        st.caption(" · ".join(meta_parts))

    if answer.status == AnswerStatus.OK:
        render_citations(answer.citations)


def _handle_new_query(rag: RAGService, query: str) -> None:
    with st.chat_message("user"):
        st.write(query)

    with st.chat_message("assistant"):
        with st.spinner("사규 검색 중..."):
            answer = rag.answer(query)
        _render_answer(answer)

    _append_history(query, answer)
