"""Streamlit entry — DF COMPASS v2."""
import streamlit as st

from src.ai.cache import LRUCache
from src.ai.gemini import GeminiClient
from src.config.settings import get_settings
from src.data.repository import DocumentRepository
from src.frontend.chat import render_chat_page
from src.frontend.styles import inject_global_css
from src.service.rag import RAGService


st.set_page_config(
    page_title="DF COMPASS",
    page_icon="🧭",
    layout="centered",
    initial_sidebar_state="collapsed",
)


@st.cache_resource(show_spinner=False)
def _get_rag_service() -> RAGService:
    settings = get_settings()
    llm_cache = LRUCache(capacity=256)
    llm = GeminiClient(settings=settings, cache=llm_cache)
    repository = DocumentRepository(settings=settings, llm=llm)
    return RAGService(repository=repository, llm=llm)


def main() -> None:
    inject_global_css()
    try:
        rag = _get_rag_service()
    except RuntimeError as e:
        st.error(f"초기화 오류: {e}")
        st.info("관리자에게 문의: SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY / GOOGLE_API_KEY 설정 확인 필요")
        return

    render_chat_page(rag)


if __name__ == "__main__":
    main()
