-- ============================================================
--  NEXUS AI · hotline_config_public view 점검 + 동기화
--  - app.py:load_hotlines 가 anon 키로 'hotline_config_public' view 를
--    SELECT 함. view 정의가 누락됐거나 컬럼이 부족하면 사용자 화면에
--    핫라인 문구가 빈 값으로 fallback.
--  - 본 스크립트는 view 존재 / 컬럼 / 신규 키 노출 여부를 점검하고,
--    필요 시 view 를 표준 정의로 재생성.
-- ============================================================

-- ── 1. view 존재 + 컬럼 확인 ─────────────────────────────────
select column_name, data_type
  from information_schema.columns
 where table_name = 'hotline_config_public'
 order by ordinal_position;
-- 기대: key (text), value (text)

-- ── 2. view 가 노출하는 row 수 / 키 목록 ────────────────────
select count(*) as total_keys,
       string_agg(key, ', ' order by key) as keys
  from hotline_config_public;
-- 기대: csr_contact_text, ethics_hotline_url, external_hotline,
--       hr_chatbot_url, hr_contact_text, internal_report_url

-- ── 3. view 누락/구버전이면 표준 정의로 재생성 ──────────────
-- 안전한 표준 정의 — key/value 만 노출, description/updated_at 등 메타
-- 데이터는 anon 에 누설 안 되게 차단. 신규 키도 자동 포함되도록 select *.
create or replace view hotline_config_public as
  select key, value
    from hotline_config;

-- view 자체 RLS 가 source 테이블 RLS 를 상속하므로, anon SELECT 허용을
-- view 에 명시적으로 grant (Supabase 기본은 anon 에 SELECT 허용).
grant select on hotline_config_public to anon, authenticated;

notify pgrst, 'reload schema';

-- ── 4. 재확인 ───────────────────────────────────────────────
select key, value
  from hotline_config_public
 order by key;
