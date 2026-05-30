-- PR-Phase-19.2.2: 기존 Haiku 4.5 추출 결과 일괄 삭제 (재추출 준비).
--
-- 사쿨님 결정: PR #278 의 Haiku 4.5 추출 546건은 Tier 3 비율 (~20%)이 높아
-- Opus 4.7 + 강화 prompt 로 재추출. TRUNCATE 로 깨끗하게 비운 뒤 admin
-- "🚀 사규 분석 시작" 재실행.
--
-- 안전 가드:
--  - RESTART IDENTITY: PK 시퀀스 초기화 (UUID 라 의미상 무관하지만 일관성).
--  - 백업 옵션 주석 처리 (필요 시 admin 이 주석 해제 후 실행).
--  - 응답 경로 무영향: ENABLE_SYNONYM_EXPANSION=false 상태에서 실행해도 안전.

BEGIN;

-- (선택) 기존 데이터 백업 — admin 이 필요 시 주석 해제:
-- DROP TABLE IF EXISTS nexus_synonym_dictionary_backup;
-- CREATE TABLE nexus_synonym_dictionary_backup AS
--   SELECT * FROM nexus_synonym_dictionary;

TRUNCATE TABLE nexus_synonym_dictionary RESTART IDENTITY;

NOTIFY pgrst, 'reload schema';

COMMIT;
