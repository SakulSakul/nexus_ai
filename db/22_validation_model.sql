-- ============================================================
--  DF COMPASS · Validation Mode 모델 식별 컬럼 추가
--    nexus_validation_runs 에 model_id / provider 추가
--    PR-Validation-To-Admin: 사이드바 → admin.py 탭 이전 + 모델 selectbox
--    Supabase 측 적용 완료 (2026-05-20).
-- ============================================================

alter table nexus_validation_runs add column if not exists model_id text;
alter table nexus_validation_runs add column if not exists provider text;

create index if not exists idx_validation_runs_model on nexus_validation_runs (model_id);
