"""RAGService 단위 테스트. mock LLM/Repo 사용 — 외부 의존 0."""
from unittest.mock import MagicMock

import pytest

from src.service.models import Answer, AnswerStatus, Chunk
from src.service.rag import RAGService, SIMILARITY_THRESHOLD


def _make_chunk(
    id: str = "c1",
    title: str = "(공통) 신세계그룹 CREDO",
    article: str = "제4조",
    text: str = "임직원은 회사 자산을 사적으로 사용해서는 안 된다.",
    score: float = 0.85,
) -> Chunk:
    return Chunk(
        id=id, document_id="d1", document_title=title,
        article_no=article, text=text,
        categories=("공통",), score=score, doc_kind="rule",
    )


def _make_service(
    chunks: list,
    llm_synth_text: str = "답변. [§(공통) 신세계그룹 CREDO 제4조]",
    llm_classify_result: dict | None = None,
) -> RAGService:
    repo = MagicMock()
    repo.search.return_value = chunks
    llm = MagicMock()
    llm.classify.return_value = llm_classify_result or {"categories": ["공통"]}
    llm.synthesize.return_value = llm_synth_text
    return RAGService(repository=repo, llm=llm)


def test_empty_chunks_returns_insufficient():
    svc = _make_service(chunks=[])
    ans = svc.answer("질문")
    assert ans.status == AnswerStatus.INSUFFICIENT


def test_below_threshold_returns_insufficient():
    low_chunk = _make_chunk(score=SIMILARITY_THRESHOLD - 0.05)
    svc = _make_service(chunks=[low_chunk])
    ans = svc.answer("질문")
    assert ans.status == AnswerStatus.INSUFFICIENT


def test_above_threshold_calls_synthesize():
    svc = _make_service(chunks=[_make_chunk(score=0.85)])
    ans = svc.answer("법인카드 개인 사용 가능?")
    assert ans.status == AnswerStatus.OK
    svc.llm.synthesize.assert_called_once()


def test_answer_without_citation_returns_insufficient():
    svc = _make_service(
        chunks=[_make_chunk()],
        llm_synth_text="인용 없는 답변 텍스트.",
    )
    ans = svc.answer("질문")
    assert ans.status == AnswerStatus.INSUFFICIENT


def test_answer_with_invalid_citation_returns_insufficient():
    svc = _make_service(
        chunks=[_make_chunk(title="(공통) 신세계그룹 CREDO", article="제4조")],
        llm_synth_text="답변. [§(없는사규) 제99조]",
    )
    ans = svc.answer("질문")
    assert ans.status == AnswerStatus.INSUFFICIENT


def test_answer_with_valid_citation_returns_ok():
    chunk = _make_chunk(title="(공통) 신세계그룹 CREDO", article="제4조")
    svc = _make_service(
        chunks=[chunk],
        llm_synth_text="답변. [§(공통) 신세계그룹 CREDO 제4조]",
    )
    ans = svc.answer("질문")
    assert ans.status == AnswerStatus.OK
    assert len(ans.citations) == 1


def test_multiple_citations_extracted():
    c1 = _make_chunk(id="c1", title="A", article="제1조")
    c2 = _make_chunk(id="c2", title="B", article="제2조")
    svc = _make_service(
        chunks=[c1, c2],
        llm_synth_text="[§A 제1조] 그리고 [§B 제2조] 참조.",
    )
    ans = svc.answer("질문")
    assert ans.status == AnswerStatus.OK
    assert {c.chunk_id for c in ans.citations} == {"c1", "c2"}


def test_classifier_failure_uses_default_categories():
    svc = _make_service(
        chunks=[_make_chunk()],
        llm_classify_result={},
    )
    ans = svc.answer("질문")
    assert svc.repository.search.called
    assert ans.status == AnswerStatus.OK


def test_empty_query_returns_error():
    svc = _make_service(chunks=[])
    ans = svc.answer("")
    assert ans.status == AnswerStatus.ERROR


def test_repository_failure_returns_error():
    svc = _make_service(chunks=[])
    svc.repository.search.side_effect = RuntimeError("DB 연결 실패")
    ans = svc.answer("질문")
    assert ans.status == AnswerStatus.ERROR
