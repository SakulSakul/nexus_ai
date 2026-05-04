-- ============================================================
--  DF COMPASS · 레이더 통계 보강 컬럼
--  - elapsed_ms     : 응답 시간(ms). NULL = 기존 데이터(베타 보강 이전)
--  - used_fallback  : LLM primary 실패 후 fallback provider 진입 여부.
--                     기존 데이터는 default false 로 backfill.
--
--  저신뢰도 응답률은 별도 컬럼 없이
--    array_length(hit_chunk_ids, 1) is null or array_length(hit_chunk_ids, 1) = 0
--  로 집계한다 (hit 0건 = 사규 미발견 = 저신뢰도).
-- ============================================================

alter table query_logs
  add column if not exists elapsed_ms     integer,
  add column if not exists used_fallback  boolean default false;

-- 대시보드 집계 가속 (응답시간 분포·fallback 발동률 패널)
create index if not exists idx_query_logs_elapsed
  on query_logs (elapsed_ms);
create index if not exists idx_query_logs_fallback
  on query_logs (used_fallback);
