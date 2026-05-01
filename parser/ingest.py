"""문서 적재 파이프라인.

- DOCX 파서로 청크 생성 → Gemini 임베딩 → Supabase insert
- 신고절차 문서는 차단 (NEXUS 적재 제외, 인사 챗봇 전용)
- 신규 버전 적재 시 같은 title 의 active 문서를 archived 로 자동 전환
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from .docx_parser import (
    Chunk, parse_docx, suggest_categories, looks_like_hr_procedure,
)
from core.embedder import embed_many


@dataclass
class IngestResult:
    document_id: str | None
    chunks_inserted: int
    skipped_hr_procedure: bool
    archived_previous: bool


def ingest_docx(
    supabase: Any,
    *,
    file_bytes: bytes,
    title: str,
    doc_kind: str,                        # 'rule'|'case'|'penalty'
    version: str = "v1",
    effective_date: date | None = None,
    uploaded_by: str | None = None,
    confirmed_categories: list[str] | None = None,
    department: str | None = None,
    source_filename: str | None = None,
) -> IngestResult:
    chunks: list[Chunk] = parse_docx(file_bytes)
    sample = "\n".join(c.text for c in chunks[:6])
    if looks_like_hr_procedure(title, sample):
        return IngestResult(None, 0, True, False)

    # 카테고리 자동 추천 (관리자 확인 후 confirmed_categories 로 override 가능)
    auto_cats = suggest_categories(sample) if confirmed_categories is None else confirmed_categories

    # 관리부서: 빈 문자열·공백만 입력은 NULL 로 정규화. 챗봇 답변 빌드
    # 단계에서 NULL 이면 일반 안내문구로 fallback 한다.
    department_norm = (department or "").strip() or None

    # 동일 title 의 active 문서를 archived 로 전환
    archived_previous = False
    try:
        prev = (
            supabase.table("nexus_documents")
                    .select("id")
                    .eq("title", title)
                    .eq("status", "active")
                    .execute()
                    .data or []
        )
        if prev:
            ids = [r["id"] for r in prev]
            supabase.table("nexus_documents").update(
                {"status": "archived"}
            ).in_("id", ids).execute()
            archived_previous = True
    except Exception:
        pass

    doc_row = supabase.table("nexus_documents").insert({
        "title": title,
        "doc_kind": doc_kind,
        "source_filename": source_filename,
        "version": version,
        "effective_date": effective_date.isoformat() if effective_date else None,
        "status": "active",
        "uploaded_by": uploaded_by,
        "owning_department": department_norm,
        "meta": {"auto_categories": auto_cats},
    }).execute().data[0]

    document_id = doc_row["id"]

    # 원본 DOCX 를 Supabase Storage("nexus-docs-original" 버킷) 에 보관.
    # 이관 시 재파싱·재임베딩이 필요한데 원본 없이는 불가능하므로 베타 단계에서
    # 미리 보관. 버킷이 미생성이거나 권한이 없으면 silently skip — 적재 자체는
    # 계속 성공시킴(스키마는 source_storage_path nullable).
    from core.config import settings as _s
    try:
        bucket = "nexus-docs-original"
        safe_name = (source_filename or f"{title}.docx").replace("/", "_")
        storage_path = f"{document_id}/{safe_name}"
        supabase.storage.from_(bucket).upload(
            path=storage_path,
            file=file_bytes,
            file_options={"content-type":
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document"},
        )
        supabase.table("nexus_documents").update(
            {"source_storage_path": storage_path}
        ).eq("id", document_id).execute()
    except Exception:
        pass

    # 임베딩 (RETRIEVAL_DOCUMENT)
    embeddings = embed_many([c.text for c in chunks])
    embed_model_version = _s().embed_model

    rows = []
    for c, emb in zip(chunks, embeddings):
        # 청크별 카테고리: 추천 카테고리에 청크 텍스트 기반 추가 후보 합집합
        cats = sorted(set(auto_cats) | set(suggest_categories(c.text)))
        rows.append({
            "document_id":         document_id,
            "chunk_idx":           c.chunk_idx,
            "article_no":          c.article_no,
            "case_no":             c.case_no,
            "categories":          cats,
            "text":                c.text,
            "embedding":           emb,
            "embed_model_version": embed_model_version,
        })

    if rows:
        # Supabase python sdk 는 한번에 큰 배열 적재 가능, 안전하게 배치 분할.
        BATCH = 50
        for i in range(0, len(rows), BATCH):
            supabase.table("nexus_chunks").insert(rows[i:i+BATCH]).execute()

    return IngestResult(document_id, len(rows), False, archived_previous)
