"""인용 chunk 카드 렌더링."""
import html

import streamlit as st

from src.service.models import Citation


def render_citations(citations: tuple[Citation, ...]) -> None:
    if not citations:
        return

    st.markdown("---")
    st.markdown("#### 📎 답변 근거 사규")

    for i, cit in enumerate(citations, start=1):
        _render_one(i, cit)


def _render_one(idx: int, cit: Citation) -> None:
    title_safe = html.escape(cit.document_title)
    article_safe = html.escape(cit.article_no) if cit.article_no else ""
    text_safe = html.escape(cit.chunk_text).replace("\n", "<br>")

    article_line = (
        f'<div class="citation-card-article">{article_safe}</div>'
        if article_safe
        else ""
    )

    st.markdown(
        f"""
<div class="citation-card">
  <div class="citation-card-title">[{idx}] {title_safe}</div>
  {article_line}
  <div class="citation-card-body">{text_safe}</div>
</div>
""",
        unsafe_allow_html=True,
    )
