"""헌법적 제약 system prompt — chunk_id + verbatim_quote 강제."""


CONSTITUTIONAL_SYSTEM_PROMPT = """\
당신은 신세계디에프의 사규 답변 전문가. 컴플라이언스 절대 우선.

🏛️ 헌법적 제약 (반드시 준수):
1. 모든 claim 은 제공된 청크에서만. 외부 지식/추측/발명 금지.
2. 각 claim 에 chunk_id 명시 — 제공된 청크 리스트에 실제 존재하는 ID 만 사용.
3. verbatim_quote 는 청크의 정확한 원문 인용 (10~100자, 요약 X).
4. 청크에 없는 정보는 unsupported_topics 에 명시.
5. 필수 doc 이 청크에 없으면 data_gaps 에 명시.
6. 출력은 strict JSON 만.

섹션 구성 (청크 따라 유연하게):
- "사건 분류" / "보고 절차" / "징계 수위" / "사건 사례" 등

금지 표현: "일반적으로", "대개", 청크 없는 부서/시한/금액 발명
"""


def build_user_prompt(query: str, chunks: list) -> str:
    parts: list = []
    for c in chunks or []:
        if not isinstance(c, dict):
            continue
        cid = c.get("id") or c.get("chunk_id") or ""
        title = c.get("doc_title") or c.get("title") or ""
        clause = c.get("clause") or c.get("section") or c.get("article_no") or ""
        text = c.get("text") or c.get("content") or ""
        parts.append(
            f"[chunk_id: {cid}] | doc: {title} | 조항: {clause}\n{text}\n"
        )
    chunks_block = "\n---\n".join(parts)
    return (
        f"사용자 질문: {query}\n\n"
        f"제공된 청크:\n{chunks_block}\n\n"
        f"strict JSON 출력."
    )
