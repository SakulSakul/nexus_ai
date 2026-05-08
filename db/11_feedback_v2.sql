-- ============================================================
--  DF COMPASS · query_logs 피드백 v2 — type/reasons/at + index
--
--  - 기존 컬럼 무수정 (호환성 유지):
--      feedback         smallint   (-1=👎 / 1=👍 / null=무응답)
--      feedback_comment text
--    → 기존 admin/radar 집계 (pages/admin.py: r.get("feedback") == -1)
--      가 그대로 동작.
--
--  - 신규 nullable 컬럼 3개 + 인덱스 1개. 모두 IF NOT EXISTS (idempotent).
--
--  - 사용자 지시안의 nexus_query_logs 는 본 레포 컨벤션상 query_logs
--    이므로 테이블명을 query_logs 로 정렬 (db/01_schema.sql:147).
--
--  - 흐름:
--      1) 사용자가 답변에 👍/👎 클릭
--         → feedback (기존 ±1) + feedback_type ('positive'/'negative')
--           + feedback_at (timestamptz) 동시 갱신.
--           폼이 펼쳐지지만 클릭 직후 이미 카운트는 잡힘.
--      2) 사유 chip + 자유 의견 입력 후 [제출]
--         → feedback_reasons (jsonb 배열) + feedback_comment (기존 text)
--           추가 갱신. feedback_at 은 클릭 시점 그대로.
--      3) [건너뛰기] 클릭 시 추가 쓰기 없음 (이미 type/at 기록됨).
-- ============================================================

alter table if exists query_logs
  add column if not exists feedback_type      text,                          -- 'positive' | 'negative'
  add column if not exists feedback_reasons   jsonb default '[]'::jsonb,
  add column if not exists feedback_at        timestamptz;

-- feedback_comment 는 db/04_beta_hooks.sql 에서 이미 존재 (text). 재선언 불요.

create index if not exists idx_query_logs_feedback_type
  on query_logs (feedback_type) where feedback_type is not null;

-- PostgREST 스키마 캐시 즉시 reload — 신규 컬럼이 supabase-py 에 즉시 보이게.
notify pgrst, 'reload schema';
