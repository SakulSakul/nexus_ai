-- ============================================================
--  DF COMPASS · PR-Stage-C-Auto-Fixer: weak query 자동 보강
--    2026-05-22. 사쿨 vision (Self-Healing) 의 완성.
--    Stage B (Auto-Testset) 의 weak query 를 LLM 이 자동 분석 + 보강 제안.
-- ============================================================

create table if not exists auto_fixer_proposals (
  id uuid primary key default gen_random_uuid(),
  run_id uuid references testset_runs(id) on delete set null,
  weak_query text not null,
  expected_doc_id text not null,
  expected_doc_title text,
  target_chunk_id uuid references nexus_chunks(id) on delete set null,
  target_chunk_idx int,
  current_keywords jsonb,
  suggested_keywords jsonb,
  reasoning text,
  confidence text,
  status text default 'pending',
  created_at timestamptz default now(),
  applied_at timestamptz
);

create index if not exists idx_fixer_status on auto_fixer_proposals(status);
create index if not exists idx_fixer_run on auto_fixer_proposals(run_id);
