-- ============================================================
--  NEXUS AI · 베타 품질 보강 (PII / critical / audit / 검수 / 트리거)
--  - 모든 변경은 멱등 (IF NOT EXISTS / ON CONFLICT DO NOTHING)
--  - 기존 운영 데이터 보존
-- ============================================================

-- ── 1. critical_keywords 시드 확장 ──────────────────────────
-- 기존 짧은 키워드(사망/부상/추락 등) 의 false-positive 는 admin → 키워드
-- 탭에서 운영자가 비활성화 결정. 본 시드는 추가만 (ON CONFLICT DO NOTHING).
-- 'compliance'(부정·뇌물·담합·정보유출) 도 신고·조사 라우팅(=CSR/핫라인) 이
-- harassment 와 동일하므로 kind='harassment' 로 통합 등록.
insert into critical_keywords (kind, keyword) values
  -- safety: 안전·응급
  ('safety','중대재해'),('safety','산업재해'),('safety','사망사고'),
  ('safety','추락사고'),('safety','감전'),('safety','폭발'),
  ('safety','가스 누출'),('safety','119'),('safety','응급실'),
  ('safety','의식을 잃'),('safety','심정지'),('safety','골절'),
  ('safety','출혈'),
  -- harassment: 괴롭힘·성희롱
  ('harassment','직장 내 괴롭힘'),('harassment','폭언'),('harassment','폭행'),
  ('harassment','모욕'),('harassment','강제추행'),('harassment','미투'),
  ('harassment','불법촬영'),('harassment','협박'),('harassment','강요'),
  -- harassment(compliance): 부정·뇌물·담합 — 신고·조사 라우팅 동일
  ('harassment','뇌물'),('harassment','횡령'),('harassment','배임'),
  ('harassment','리베이트'),('harassment','담합'),('harassment','부정청탁'),
  ('harassment','내부자거래'),('harassment','비자금'),('harassment','부정 회계'),
  -- harassment(security): 정보보안 사고 — 신고·조사 라우팅 동일
  ('harassment','개인정보 유출'),('harassment','데이터 유출'),
  ('harassment','영업비밀 유출'),('harassment','자료 무단 반출'),
  ('harassment','해킹'),('harassment','악성코드'),
  -- harassment(traffic·법규): 음주운전·뺑소니 — 신고·조사 라우팅
  ('harassment','음주운전'),('harassment','뺑소니')
on conflict (kind, keyword) do nothing;

-- ── 2. nexus_documents.updated_at 트리거 ─────────────────────
-- admin 이 부서·카테고리 등 메타 변경 시 변경 시각 자동 기록.
alter table if exists nexus_documents
  add column if not exists updated_at timestamptz not null default now();

create or replace function nexus_documents_updated_at_trigger()
returns trigger as $$
begin
  new.updated_at := now();
  return new;
end $$ language plpgsql;

drop trigger if exists trg_nexus_documents_updated_at on nexus_documents;
create trigger trg_nexus_documents_updated_at
  before update on nexus_documents
  for each row execute function nexus_documents_updated_at_trigger();

-- ── 3. beta_consents.participant_emp_no — 별도 컬럼 ──────────
-- 기존: participant 단일 컬럼에 'name / emp_no' 혼합 저장 → 이름에 '/'
-- 들어가면 파싱 깨짐. 사번을 별도 컬럼으로 분리.
alter table if exists beta_consents
  add column if not exists participant_emp_no text;

-- ── 4. review_samples.forbidden_keywords ────────────────────
-- 답변에 "포함되면 안 되는 키워드" — false-positive 검증용.
-- 예: 인사 행정 질문에 답변이 "CSR팀" 라우팅하면 fail.
alter table if exists review_samples
  add column if not exists forbidden_keywords text[] not null default '{}';

-- ── 5. csr_contact_text 시드 (idempotent 보강) ───────────────
insert into hotline_config (key, value, description) values
  ('csr_contact_text',
   '신고·조사 사항은 CSR팀 또는 신세계면세점 핫라인으로 접수해 주시기 바랍니다.',
   '신고·조사(괴롭힘·성희롱·뇌물 등) 라우팅 문구')
on conflict (key) do nothing;

-- ── 6. PostgREST 스키마 캐시 즉시 리로드 ────────────────────
notify pgrst, 'reload schema';
