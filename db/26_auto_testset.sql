-- ============================================================
--  DF COMPASS · PR-Stage-B-Auto-Testset: 505 query 자가 진단
--    2026-05-22. 사쿨 vision (Self-Healing) 의 첫 단계.
--    docs.auto_query_examples 활용 + shadow V3 매칭 분석.
-- ============================================================

create table if not exists testset_runs (
  id uuid primary key default gen_random_uuid(),
  started_at timestamptz not null default now(),
  completed_at timestamptz,
  total_queries int not null default 0,
  recall_at_1 numeric,
  recall_at_3 numeric,
  recall_at_5 numeric,
  recall_overall numeric,
  notes text
);

create table if not exists testset_results (
  id uuid primary key default gen_random_uuid(),
  run_id uuid not null references testset_runs(id) on delete cascade,
  query_text text not null,
  expected_doc_id text not null,
  expected_doc_title text,
  matched_candidates jsonb,
  expected_rank int,
  total_candidates int not null default 0,
  created_at timestamptz default now()
);

create index if not exists idx_testset_results_run on testset_results(run_id);
create index if not exists idx_testset_runs_started on testset_runs(started_at desc);
