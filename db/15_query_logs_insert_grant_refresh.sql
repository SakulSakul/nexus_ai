-- ============================================================
--  DF COMPASS · query_logs INSERT GRANT 재적용 (PR-Beta-Hotfix-1)
--
--  배경:
--    db/13 적용 후 query_logs INSERT 가 silent fail 되는 사고 (266 row,
--    last_ts 2026-05-09 12:14 이후 적재 0). 컬럼 화이트리스트 자체는
--    chatbot.py INSERT 12 컬럼 모두 포함 (subset). 가장 유력한 가설은
--    PostgREST 스키마 캐시 미반영 또는 db/13 SQL 부분 실행.
--
--  본 마이그:
--    1) revoke + grant insert (cols) 재적용 — 멱등 (db/13 와 동일 cols).
--    2) sequence usage 재확인 — id 자동 채번 권한.
--    3) notify pgrst, 'reload schema' — PostgREST 스키마 캐시 강제 reload.
--
--  본 파일은 db/13 의 INSERT GRANT 부분만 다시 박는 것이며 정책 본문
--  (drop/create policy) 은 변경하지 않는다. 재실행 안전.
--
--  실행 후 검증 (사쿨 라이브):
--    1. 챗봇 질의 1회 → query_logs 에 row 적재 확인
--       SELECT id, ts, query_masked FROM query_logs ORDER BY ts DESC LIMIT 5;
--    2. anon 의 INSERT 컬럼 GRANT 확인:
--       SELECT grantee, column_name, privilege_type
--         FROM information_schema.column_privileges
--        WHERE table_name = 'query_logs'
--          AND grantee IN ('anon', 'authenticated')
--          AND privilege_type = 'INSERT'
--        ORDER BY grantee, column_name;
--       기대 결과: 14개 행 × 2 grantee = 28 row.
--    3. admin 페이지 헬스 배너 사라짐 (last_ts 갱신 + 최근 row 존재).
-- ============================================================

-- 1) 컬럼 단위 INSERT GRANT 재적용 (db/13 line 73-78 과 동일 cols).
revoke insert on query_logs from anon, authenticated;
grant insert (
  category, query_masked, is_critical, critical_kind,
  hit_chunk_ids, hit_categories, env, embed_model_version,
  chat_provider, chat_model_version, elapsed_ms, used_fallback,
  is_reroll, dept_hash
) on query_logs to anon, authenticated;

-- 2) 시퀀스 사용 권한 — INSERT 시 id 발급에 필요. db/13 line 27 과 동일.
grant usage, select on sequence query_logs_id_seq to anon, authenticated;

-- 3) PostgREST 스키마 캐시 강제 reload — db/13 적용 후 캐시 미반영
--    가능성을 차단. notify 만으로 충분 (PostgREST 가 LISTEN 중).
notify pgrst, 'reload schema';

-- ============================================================
--  알려진 한계:
--   - 본 파일은 RLS 정책 자체는 건드리지 않음. db/13 정책 (insert_anon /
--     update_feedback_anon / update_reroll_anon / select_service_only) 이
--     이미 정상 적용되어 있다고 가정. 정책 dump 결과 누락 시 db/13 재실행.
--   - 본 파일 적용 후에도 INSERT 가 실패한다면 chatbot.py 의 강화된
--     [QUERY_LOGS INSERT FAIL] stderr 로그를 Streamlit Cloud Logs 탭에서
--     확인. exception type + PostgREST 상세 + payload 컬럼 list 가
--     기록되어 진짜 원인을 즉시 파악 가능.
-- ============================================================
