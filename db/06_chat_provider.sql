-- ============================================================
--  NEXUS AI · 멀티 챗봇 provider 식별 컬럼
--  - Gemini / Claude 중 어떤 provider 가 답변했는지, 어떤 model 버전인지
--    매 호출 단위로 기록하여 베타 단계 답변 품질·비용 비교 데이터 확보.
--  - chat_provider 가 NULL 인 과거 로그는 베타 hook 도입 이전 데이터.
-- ============================================================

alter table if exists query_logs
  add column if not exists chat_provider       text,    -- 'gemini' | 'claude'
  add column if not exists chat_model_version  text;    -- e.g. 'gemini-2.5-pro', 'claude-opus-4-7'

create index if not exists idx_query_logs_chat_provider
  on query_logs (chat_provider, ts desc) where chat_provider is not null;
