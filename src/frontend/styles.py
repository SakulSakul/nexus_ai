"""Streamlit 공통 CSS."""
import streamlit as st


_CSS = """
<style>
.citation-tag {
    display: inline-block;
    padding: 0.1em 0.5em;
    margin: 0 0.2em;
    background: #f0f7ff;
    color: #0066cc;
    border-left: 3px solid #0066cc;
    border-radius: 3px;
    font-size: 0.88em;
    font-weight: 500;
}
.df-answer {
    padding: 1em 1.2em;
    background: #ffffff;
    border: 1px solid #e5e7eb;
    border-radius: 8px;
    line-height: 1.7;
    color: #1f2937;
    white-space: pre-wrap;
}
.df-answer.insufficient {
    background: #fef2f2;
    border-color: #fca5a5;
    color: #991b1b;
}
.df-answer.error {
    background: #fffbeb;
    border-color: #fcd34d;
    color: #92400e;
}
.citation-card {
    margin: 0.5em 0;
    padding: 0.8em 1em;
    background: #fafafa;
    border: 1px solid #e5e7eb;
    border-left: 4px solid #6366f1;
    border-radius: 6px;
    font-size: 0.92em;
}
.citation-card-title {
    font-weight: 600;
    color: #4338ca;
    margin-bottom: 0.3em;
}
.citation-card-article {
    color: #6b7280;
    font-size: 0.88em;
    margin-bottom: 0.5em;
}
.citation-card-body {
    color: #374151;
    white-space: pre-wrap;
}
</style>
"""


def inject_global_css() -> None:
    st.markdown(_CSS, unsafe_allow_html=True)
