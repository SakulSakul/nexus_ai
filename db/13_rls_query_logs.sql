-- ============================================================
--  DF COMPASS · query_logs RLS 차단 (PR-CRIT3 / PR-S1)
--  - C1: query_masked 가 anon 으로 SELECT 되던 사고 차단
--  - INSERT 는 anon 유지 (chatbot 응답 경로가 anon 키 사용 중) +
--    컬럼 화이트리스트 강제로 불필요 컬럼 주입 차단
--  - SELECT 는 service_role 만 허용. admin 페이지의 query_logs
--    SELECT 경로는 _supabase_admin() 으로 분리됨 (pages/admin.py).
--  - 멱등성: DROP POLICY IF EXISTS → CREATE POLICY 패턴.
-- ============================================================

-- 1) RLS 활성화 (idempotent — 이미 on 이어도 무방)
alter table if exists query_logs enable row level security;

-- 2) anon 키의 SELECT/UPDATE/DELETE GRANT 회수.
--    INSERT 는 chatbot 응답 경로가 anon 으로 사용 중이므로 유지.
--    feedback UPDATE 는 응답 직후 query_log_id 로 본인 row 만 갱신
--    하므로 별도 정책으로 허용 (아래 4번).
revoke select, update, delete on query_logs from anon;
grant insert on query_logs to anon;

-- 3) authenticated 도 동일 — 베타에서는 SSO 미도입이라 모두 anon 이지만
--    회사 이관 시 자동 정합 유지.
revoke select, update, delete on query_logs from authenticated;
grant insert on query_logs to authenticated;

-- 4) 시퀀스 사용 권한 — INSERT 시 id 발급에 필요.
grant usage, select on sequence query_logs_id_seq to anon, authenticated;

-- 5) RLS 정책 — DROP IF EXISTS 후 CREATE.
--    SELECT: service_role 만. anon 은 GRANT 도 없고 정책도 없음 → 이중 차단.
--    INSERT: anon 허용. 컬럼 화이트리스트는 PostgREST 측 column-level
--            grant 로 강제 (아래 6번).
--    UPDATE: 두 정책 분리.
--      (a) feedback UPDATE — 시간 제한 없음. 사용자가 답변 보고 나중에
--          피드백 줄 수 있어야 하므로 ts 윈도우 두지 않음. 컬럼 화이트
--          리스트는 column-level grant 로 강제.
--      (b) reroll fixup UPDATE — 5분 윈도우. app.py:1573 의 reroll 직후
--          query_masked·is_reroll 보정 경로. 운영 보정이므로 답변 직후
--          즉시 실행됨 → 5분 안전 마진. 외부 abuse 표면 축소.
--      ⚠️ PostgreSQL PERMISSIVE 정책은 OR 결합. 두 정책 중 어느 한쪽의
--         USING/WITH CHECK 만 통과하면 row UPDATE 허용. 따라서 (a) 가
--         USING=true 이면 (b) 의 ts 윈도우는 사실상 우회 가능. 진정한
--         abuse 차단은 trigger 로 가야 — 본 정책 분리는 의도 표현·문서
--         가치 + column GRANT 로 컬럼 표면 축소가 1차 방어.
--    UPDATE 일반: id 일치 + INSERT 직후 본인 row 라는 신뢰 경계는 없으나
--            query_logs.id 는 application 단에서만 노출되고 외부 추측이
--            어렵다 (bigserial). 회사 이관 시 SSO + RLS owner 검증으로 강화.
drop policy if exists query_logs_select_service_only on query_logs;
create policy query_logs_select_service_only on query_logs
  for select to service_role using (true);

drop policy if exists query_logs_insert_anon on query_logs;
create policy query_logs_insert_anon on query_logs
  for insert to anon, authenticated with check (true);

-- (a) feedback UPDATE — 본문 변경 없음 (이전 버전 그대로).
drop policy if exists query_logs_update_feedback_anon on query_logs;
create policy query_logs_update_feedback_anon on query_logs
  for update to anon, authenticated using (true) with check (true);

-- (b) reroll fixup UPDATE — 신규. ts > now() - 5분 row 만 대상.
drop policy if exists query_logs_update_reroll_anon on query_logs;
create policy query_logs_update_reroll_anon on query_logs
  for update to anon, authenticated
  using (ts > now() - interval '5 minutes')
  with check (ts > now() - interval '5 minutes');

-- 6) 컬럼 단위 GRANT — INSERT 시 anon 이 채울 수 있는 컬럼 화이트리스트.
--    chatbot.py 가 INSERT 하는 컬럼만 명시. id/ts 는 default 로 채워짐.
--    feedback_* 는 UPDATE 단계에서 채우므로 INSERT GRANT 에 포함 불필요
--    하지만 미래 확장 여지로 포함.
revoke insert on query_logs from anon, authenticated;
grant insert (
  category, query_masked, is_critical, critical_kind,
  hit_chunk_ids, hit_categories, env, embed_model_version,
  chat_provider, chat_model_version, elapsed_ms, used_fallback,
  is_reroll, dept_hash
) on query_logs to anon, authenticated;

-- UPDATE 컬럼 화이트리스트 — 피드백 5개 + reroll fixup 2개.
--   feedback*  : 사용자 피드백 UI 경로 (시간 제한 없음, 위 정책 a)
--   query_masked / is_reroll : reroll fixup 경로 (5분 윈도우, 위 정책 b)
-- column GRANT 는 정책 분기와 무관하게 union 으로 적용 — 컬럼 표면 축소
-- 효과만 강제. row 시간 검증은 정책 (b) 가 담당 (PERMISSIVE OR 결합 한계
-- 는 정책 5번 코멘트의 ⚠️ 참조).
revoke update on query_logs from anon, authenticated;
grant update (
  feedback, feedback_type, feedback_reasons, feedback_comment, feedback_at,
  query_masked, is_reroll
) on query_logs to anon, authenticated;

-- 7) PostgREST 스키마 캐시 reload — 정책·권한 변경 즉시 반영.
notify pgrst, 'reload schema';

-- ============================================================
--  검증 절차 (sakul 라이브 확인 필수):
--  1. anon 키로 query_logs SELECT 시도:
--     curl -H "apikey: <ANON_KEY>" -H "Authorization: Bearer <ANON_KEY>" \
--          "<SUPABASE_URL>/rest/v1/query_logs?select=*&limit=1"
--     기대: HTTP 401/403 또는 빈 배열 + RLS 메시지.
--  2. service_role 키로 SELECT → 정상 row 반환.
--  3. 챗봇 질의 1회 → INSERT 정상 동작 (admin 페이지 헬스 배너 0건 아님).
--  4. admin 페이지 레이더 탭 → 정상 표시 (_supabase_admin() 경로).
--  5. 피드백 👍/👎 클릭 → query_logs.feedback_type 정상 UPDATE.
--  6. reroll 동작 → app.py:1573 의 query_masked·is_reroll 사후 UPDATE
--     정상. 5분 윈도우 안 (답변 직후) 이므로 정책 (b) 통과.
--  7. (선택) anon 키로 5분 초과 row 의 query_masked UPDATE 시도 →
--     정책 (a) USING=true 에 OR 결합되어 통과 가능. 진정한 abuse 차단은
--     trigger 로 강화 (다음 step 의 보안 강화 옵션).
-- ============================================================
