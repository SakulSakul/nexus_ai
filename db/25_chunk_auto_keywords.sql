-- ============================================================
--  DF COMPASS · PR-Stage-A-1-Chunk: chunk 단위 auto_keywords
--    2026-05-21. doc-level meta 의 본질적 한계 (memory) 의 fix.
--    Stage A-2-Shadow-V3 의 chunk-level 활용을 위한 데이터 인프라.
-- ============================================================

alter table nexus_chunks
  add column if not exists auto_keywords jsonb default '[]'::jsonb;

comment on column nexus_chunks.auto_keywords is
  'PR-Stage-A-1-Chunk: Claude Opus 4.7 추출 chunk 단위 keyword 5~10개.
   부모 doc.auto_keywords (chapter 제목) 와 차별되는 chunk 본문의 specific 내용.
   Stage A-2-Shadow-V3 의 retrieval 매칭에 활용.';
