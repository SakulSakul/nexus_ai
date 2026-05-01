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
