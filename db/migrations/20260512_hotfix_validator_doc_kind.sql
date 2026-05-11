-- Hotfix: 임직원 징계기준 doc_kind 'penalty' 정정 (synthesis_validator 의
-- ⚖️ 섹션 빌드 인식용 + chatbot._balance_by_doc_kind 의 penalty=2 슬롯 진입).
--
-- 배경: 4-layer hotfix (PR #102/103) 후에도 ⚖️ 징계 기준 섹션 비어있음.
-- _balance_by_doc_kind 가 penalty=2 슬롯에 doc_kind='penalty' 청크만 받아서
-- 임직원 징계기준 doc 이 'rule' 또는 NULL 이면 ⚖️ 채울 청크 없음.
-- 본 마이그레이션이 doc_kind 정정으로 보장.

BEGIN;

-- Pre-flight: 현재 doc_kind 확인.
SELECT 'preview: 임직원 징계기준 doc_kind 현황' AS check_kind,
       title, doc_kind
FROM nexus_documents
WHERE title ILIKE '%임직원%징계%'
  AND status = 'active' AND superseded_by IS NULL;

-- UPDATE: doc_kind 가 'penalty' 가 아니면 정정.
UPDATE nexus_documents
SET doc_kind = 'penalty'
WHERE title ILIKE '%임직원%징계%'
  AND status = 'active' AND superseded_by IS NULL
  AND (doc_kind IS NULL OR doc_kind != 'penalty');

-- 최종 검증
SELECT title, doc_kind
FROM nexus_documents
WHERE title ILIKE '%임직원%징계%'
  AND status = 'active' AND superseded_by IS NULL;

COMMIT;

NOTIFY pgrst, 'reload schema';
