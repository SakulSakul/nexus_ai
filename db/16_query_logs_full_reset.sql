-- ============================================================
--  DF COMPASS · query_logs full reset (PR-Beta-Hotfix-2)
--
--  배경:
--    db/13 + db/15 적용 + Streamlit App Reboot 후에도 INSERT 가
--    "permission denied for table query_logs" (42501) 로 실패. GRANT 28
--    row 적용 + RLS 정책 4건 정확함. 표면적 상태는 정상이나 실제 INSERT
--    가 거절. 가장 유력한 가설:
--      · PostgREST schema 캐시가 column-level GRANT 을 picked-up 하지
--        못하고 table-level INSERT 부재로 거절.
--      · 또는 이전 마이그레이션의 잔존 grant/policy 가 충돌.
--
--  본 마이그는 nuclear reset:
--    1) RLS DISABLE → REVOKE ALL → GRANT 새로 부여 → RLS ENABLE → 정책
--       DROP+CREATE 재생성 → NOTIFY pgrst.
--    2) 사이드 효과로 nexus_diagnose_role() 함수 신설 — chatbot.py 가
--       INSERT 실패 시 호출해 현재 role 정보를 stderr 로 dump.
--
--  스키마/데이터 변경 X (DISABLE/ENABLE 만). 멱등성 — 재실행 안전.
--
--  ⚠ 사쿨 라이브 절차:
--    1. Supabase SQL Editor 에서 본 파일 전체 실행 → "Success".
--    2. Streamlit App Reboot.
--    3. 챗봇 query 1회.
--    4. Streamlit Cloud Logs 에서 확인:
--       · 정상: [QUERY_LOGS INSERT OK] id=N cols=12
--       · 실패: [QUERY_LOGS INSERT FAIL] + [QUERY_LOGS ROLE_DIAG] 진단
--    5. SELECT count(*), max(ts) FROM query_logs; 갱신 확인.
-- ============================================================

-- 1) RLS 비활성 — clean slate. 다음 ENABLE 까지 RLS 정책 무관계.
alter table query_logs disable row level security;

-- 2) 모든 권한 회수 — 잔존 grant 충돌 차단.
revoke all on query_logs from anon, authenticated, service_role;

-- 3) 컬럼 단위 INSERT GRANT — chatbot.py INSERT 12 컬럼 + is_reroll +
--    dept_hash = 14 컬럼 (db/13·15 와 동일).
grant insert (
  category, query_masked, is_critical, critical_kind,
  hit_chunk_ids, hit_categories, env, embed_model_version,
  chat_provider, chat_model_version, elapsed_ms, used_fallback,
  is_reroll, dept_hash
) on query_logs to anon, authenticated;

-- 4) 컬럼 단위 UPDATE GRANT — feedback UI + reroll fixup (db/13 와 동일).
grant update (
  feedback, feedback_comment, feedback_type, feedback_reasons, feedback_at,
  query_masked, is_reroll
) on query_logs to anon, authenticated;

-- 5) SELECT 는 service_role 만 (admin 페이지 _supabase_admin 경로).
grant select on query_logs to service_role;

-- 6) 시퀀스 — INSERT 시 id 발급 필수.
grant usage, select on sequence query_logs_id_seq to anon, authenticated;

-- 7) RLS 재활성.
alter table query_logs enable row level security;

-- 8) 정책 재생성 — DROP IF EXISTS + CREATE.
--    · INSERT: anon, authenticated 에 대해 with check true (column GRANT
--      가 1차 게이트, 정책은 row content 검증).
--    · UPDATE feedback: USING true + WITH CHECK true (db/13 와 동일).
--      USING/CHECK 모두 명시 — Postgres 의 USING ↔ WITH CHECK 기본값
--      cross-reference 동작에 의존하지 않고 의도 명확화.
--    · UPDATE reroll: 5분 윈도우 (USING + WITH CHECK 동일 식).
--    · SELECT: service_role 만.
drop policy if exists query_logs_insert_anon on query_logs;
create policy query_logs_insert_anon on query_logs
  for insert to anon, authenticated with check (true);

drop policy if exists query_logs_update_feedback_anon on query_logs;
create policy query_logs_update_feedback_anon on query_logs
  for update to anon, authenticated using (true) with check (true);

drop policy if exists query_logs_update_reroll_anon on query_logs;
create policy query_logs_update_reroll_anon on query_logs
  for update to anon, authenticated
  using (ts > (now() - interval '5 minutes'))
  with check (ts > (now() - interval '5 minutes'));

drop policy if exists query_logs_select_service_only on query_logs;
create policy query_logs_select_service_only on query_logs
  for select to service_role using (true);

-- 9) chatbot.py 가 호출할 role 진단 함수.
--    SECURITY INVOKER (default) — 호출자 role 그대로 노출. anon 이 호출
--    하면 anon 정보가 반환된다.
--    반환 컬럼: current_user, current_role, session_user, current_schema,
--               current_database. JWT claim 은 어떤 supabase 환경에서는
--               접근 안 될 수 있으므로 기본 5개만.
create or replace function nexus_diagnose_role()
returns table (
  curr_user text,
  curr_role text,
  sess_user text,
  curr_schema text,
  curr_database text
) language sql stable as $$
  select
    current_user::text,
    current_role::text,
    session_user::text,
    current_schema::text,
    current_database()::text;
$$;

-- 함수 실행 권한 — anon, authenticated 가 호출할 수 있어야 진단 의미.
revoke all on function nexus_diagnose_role() from public;
grant execute on function nexus_diagnose_role() to anon, authenticated, service_role;

-- 10) PostgREST schema 캐시 reload — 모든 GRANT/POLICY/FUNCTION 변경 반영.
notify pgrst, 'reload schema';

-- ============================================================
--  사후 검증 SQL (사쿨 SQL Editor 에서 실행):
--
--  -- (a) GRANT 적용 상태 — INSERT 14 row × 2 grantee = 28
--  SELECT grantee, column_name, privilege_type
--    FROM information_schema.column_privileges
--   WHERE table_name = 'query_logs'
--     AND grantee IN ('anon', 'authenticated')
--     AND privilege_type = 'INSERT'
--   ORDER BY grantee, column_name;
--
--  -- (b) 정책 4건 확인
--  SELECT polname, polcmd, polroles::regrole[], polqual::text, polwithcheck::text
--    FROM pg_policy
--   WHERE polrelid = 'query_logs'::regclass
--   ORDER BY polname;
--
--  -- (c) RLS 활성 상태
--  SELECT relname, relrowsecurity, relforcerowsecurity
--    FROM pg_class WHERE relname = 'query_logs';
--
--  -- (d) 스키마 (public 기대)
--  SELECT table_schema FROM information_schema.tables
--   WHERE table_name = 'query_logs';
--
--  -- (e) role 진단 함수 호출 테스트 (postgres 권한으로)
--  SELECT * FROM nexus_diagnose_role();
-- ============================================================
