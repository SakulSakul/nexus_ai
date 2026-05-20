-- ============================================================
--  DF COMPASS · Phase 3.5 확장: 모델별 자가 테스트 + 진단
--    review_runs / review_results 에 모델 ID · 비용 · 속도 컬럼 추가
--    기존 컬럼 무변경, ADD COLUMN IF NOT EXISTS 로 idempotent
--    Supabase 측 적용 완료 (2026-05-20). 재배포·재현 환경 대응용 기록.
-- ============================================================

-- review_runs: 회차 메타에 모델 정보 추가
alter table review_runs add column if not exists model_id text;
alter table review_runs add column if not exists provider text;
alter table review_runs add column if not exists latency_avg_ms double precision;
alter table review_runs add column if not exists tokens_input_total bigint;
alter table review_runs add column if not exists tokens_output_total bigint;
alter table review_runs add column if not exists tokens_cached_total bigint;
alter table review_runs add column if not exists cost_krw_total double precision;

create index if not exists idx_review_runs_model on review_runs (model_id);

-- review_results: 샘플별 측정값 추가
alter table review_results add column if not exists latency_ms double precision;
alter table review_results add column if not exists tokens_input integer;
alter table review_results add column if not exists tokens_output integer;
alter table review_results add column if not exists tokens_cached integer;
alter table review_results add column if not exists cost_krw double precision;
alter table review_results add column if not exists structure_4section_ok boolean;
alter table review_results add column if not exists model_id text;

create index if not exists idx_review_results_model on review_results (model_id);
