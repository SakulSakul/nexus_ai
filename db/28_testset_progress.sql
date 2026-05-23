-- ============================================================
--  DF COMPASS · PR-Stage-B-Worker: testset_runs progress 추가
--    2026-05-23. Auto-Testset 의 background thread 실행 + DB progress 추적.
-- ============================================================

alter table testset_runs
  add column if not exists progress_current int not null default 0,
  add column if not exists progress_total int not null default 0,
  add column if not exists status text not null default 'pending',
  add column if not exists error_message text;

create index if not exists idx_testset_runs_status on testset_runs(status);
