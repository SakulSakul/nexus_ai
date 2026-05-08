-- ============================================================
--  DF COMPASS · query_logs reroll 메타 — is_reroll 컬럼 + 오염 정정
--
--  배경:
--    PR-1B 의 _REROLL_PREFIX ("[다시 답변 요청] ... 원 질문: ") 는 LLM
--    재호출 시 effective_q 에 prepend 되어 의도된 동작. 그러나
--    core/chatbot 의 ask_stream 이 effective_q 를 mask_pii 후 그대로
--    query_logs.query_masked 에 저장 → 진단·레이더 데이터 오염.
--
--  본 마이그:
--    1) is_reroll boolean 컬럼 추가 (default false / nullable).
--    2) 기존 prefix 박힌 row 일괄 정정 — query_masked 에서 prefix 제거하고
--       is_reroll=true 마킹.
--    3) is_reroll=true 부분 인덱스 (대부분 정상 답변이라 sparse).
--
--  idempotent — 모두 IF NOT EXISTS / 정정 UPDATE 는 prefix 박힌 row 만
--  타겟. 이미 정상인 row 는 무영향.
--
--  app.py 측 추가 변경 (PR-2.5):
--    _run_ask 의 reroll_of 분기에서 ask_stream 반환 후 같은 row 를
--    query_masked (prefix 제거) + is_reroll=true 로 사후 update.
--    core/ 시그니처 무수정.
-- ============================================================

alter table if exists query_logs
  add column if not exists is_reroll boolean default false;

create index if not exists idx_query_logs_is_reroll
  on query_logs (is_reroll) where is_reroll = true;

-- ── 기존 오염 row 일괄 정정 (idempotent) ────────────────────
-- prefix 패턴: "[다시 답변 요청] ... 원 질문: <원 질문 본문>"
-- regex 는 멀티라인 (\s 가 \n 포함) 이며 lazy 매치로 첫 "원 질문: " 직후
-- 본문만 남김. WHERE 절이 prefix 박힌 row 로 한정 → 미오염 row 무영향.
update query_logs
   set query_masked = regexp_replace(
           query_masked,
           '^\[다시 답변 요청\][\s\S]*?원 질문:\s*',
           ''
       ),
       is_reroll = true
 where query_masked like '[다시 답변 요청]%';

-- PostgREST 스키마 캐시 즉시 reload — 신규 컬럼이 supabase-py 에 즉시 보이게.
notify pgrst, 'reload schema';
