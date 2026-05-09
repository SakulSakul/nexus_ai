-- ============================================================
--  DF COMPASS · query_logs 레거시 RLS 정책 정리 (PR-S1.1)
--
--  배경:
--    db/13 적용 후 query_logs 정책 dump 시 7개 발견 — 의도 4개 +
--    이전 마이그레이션 잔존 3개. 본 마이그는 잔존 3개만 정리.
--
--  정리 대상 (DROP):
--    - anon_insert_query_logs   (db/13 의 query_logs_insert_anon 으로 대체)
--    - anon_select_query_logs   ⚠ GRANT 차단으로 실제 SELECT 노출은 없으나
--                                 정책이 남아있어 의도 표현 불일치
--    - anon_update_query_logs   (db/13 의 query_logs_update_feedback_anon /
--                                 query_logs_update_reroll_anon 으로 분리)
--
--  유지 (의도 정책, 변경 X):
--    - query_logs_select_service_only
--    - query_logs_insert_anon
--    - query_logs_update_feedback_anon
--    - query_logs_update_reroll_anon
--
--  실행 전 사전 dump 권장 (본 파일에 기록 — 사쿨이 SQL Editor 결과
--  비교 후 실행):
--    SELECT polname, polcmd, polqual::text, polwithcheck::text
--    FROM pg_policy
--    WHERE polrelid = 'query_logs'::regclass
--      AND polname LIKE 'anon\_%' ESCAPE '\';
--
--  멱등성: DROP POLICY IF EXISTS — 재실행 안전. 정책이 이미 없어도
--          에러 없이 통과.
-- ============================================================

drop policy if exists anon_insert_query_logs on query_logs;
drop policy if exists anon_select_query_logs on query_logs;
drop policy if exists anon_update_query_logs on query_logs;

-- PostgREST 스키마 캐시 reload — 정책 변경 즉시 반영.
notify pgrst, 'reload schema';

-- ============================================================
--  실행 후 검증 (사쿨 라이브):
--    SELECT polname FROM pg_policy
--    WHERE polrelid = 'query_logs'::regclass
--    ORDER BY polname;
--
--  기대 결과 (4건):
--    query_logs_insert_anon
--    query_logs_select_service_only
--    query_logs_update_feedback_anon
--    query_logs_update_reroll_anon
-- ============================================================
