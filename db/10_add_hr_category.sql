-- ============================================================
--  NEXUS AI · nexus_category enum 에 '인사' 추가
--
--  배경: 사규 카테고리에 '인사' 추가. 단 본 카테고리는 조직문화·예방
--  지침 영역 한정 (적재 대상: 업무인수인계지침 / 사내 동호회 운영지침 /
--  건전한 조직문화 조성 자율준수 지침 / 성희롱 예방지침 / 직장내 괴롭힘
--  예방대응 지침).
--
--  행정 인사(근태/휴가/급여/복리후생) 는 별도 인사봇이 처리하므로 본
--  챗봇 범위 밖. SYSTEM_PROMPT 규칙 #4-1 의 인사 행정 라우팅(인사팀에
--  문의)은 그대로 유지.
--
--  PostgreSQL 12+ 의 `add value if not exists` 사용 — Supabase 호환.
--  enum ADD VALUE 는 commit 직후 즉시 사용 가능 (같은 트랜잭션 내에서는
--  사용 불가하므로 본 SQL 단독 실행).
-- ============================================================

alter type nexus_category add value if not exists '인사' after '총무';

-- PostgREST 스키마 캐시 즉시 리로드 (신규 enum 값이 supabase-py 에 즉시 보이게)
notify pgrst, 'reload schema';
