-- ============================================================
--  NEXUS AI · 베타 참가자 동의 기록
--  - 정식 운영 이관 전까지 회사-Google 간 DPA / 처리방침 미수립
--    상태에서 임직원 베타 테스트를 진행하므로, 참가자별 사전 동의를
--    별도 기록한다.
--  - consent_version 을 두어 동의서 문구가 갱신되면 자동 재동의 트리거.
-- ============================================================

create table if not exists beta_consents (
  id              bigserial primary key,
  consented_at    timestamptz not null default now(),
  participant     text        not null,        -- 이름 (+ 사번) 자유 입력
  consent_version text        not null,        -- 'v1' 등. 문구 변경 시 증가
  env             text,                        -- query_logs.env 와 매칭 ('beta-personal' 등)
  user_agent      text,
  details         jsonb       not null default '{}'::jsonb
);

create index if not exists idx_beta_consents_ts
  on beta_consents (consented_at desc);
create index if not exists idx_beta_consents_version
  on beta_consents (consent_version, consented_at desc);

-- ── 베타 RLS 정책 ──────────────────────────────────────────
-- Supabase 신규 테이블은 RLS 가 활성화돼 있어 anon 이 insert 못 한다.
-- 베타 단계에서는 단순화를 위해 RLS off + anon/authenticated 에 insert·
-- select 권한 명시. (사용자가 베타 동의를 anon 클라이언트로 기록하고,
-- admin 화면도 anon 으로 읽기 때문.)
-- 회사 계정 이관 시점에 RLS on + 명시 정책 (예: insert 만 anon 허용,
-- select 는 service_role/admin role 한정) 으로 재구성한다.
alter table beta_consents disable row level security;
grant insert, select on beta_consents to anon, authenticated;
grant usage, select on sequence beta_consents_id_seq to anon, authenticated;
