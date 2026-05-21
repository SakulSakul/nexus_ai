-- ============================================================
--  DF COMPASS · Stage A-1: Auto-Meta DB 컬럼 추가
--    PR-Stage-A-1 (2026-05-20). 자동 메타데이터 시스템의 기반.
--    Supabase 측 적용 완료 후 영구 기록.
-- ============================================================

-- auto_keywords: doc 의 핵심 명사 list. force_include 자동 매칭용 (Stage A-2).
alter table docs add column if not exists auto_keywords jsonb default '[]'::jsonb;

-- auto_summary: doc 한 줄 요약 (관리자 빠른 검토용).
alter table docs add column if not exists auto_summary text;

-- auto_query_examples: doc 로 답변 가능한 예상 query 5개. Stage B (Auto-Testset) 용.
alter table docs add column if not exists auto_query_examples jsonb default '[]'::jsonb;

-- 확인 (idempotent)
comment on column docs.auto_keywords is 'PR-Stage-A-1: Claude Opus 가 추출한 핵심 명사 (force_include 자동 매칭용)';
comment on column docs.auto_summary is 'PR-Stage-A-1: 한 줄 요약';
comment on column docs.auto_query_examples is 'PR-Stage-A-1: 예상 사용자 query 5개 (Auto-Testset 용)';
