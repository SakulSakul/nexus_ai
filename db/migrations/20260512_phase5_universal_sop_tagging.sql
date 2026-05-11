-- Phase 5: Universal SOP 의 incident_nodes 에 새 카테고리 추가
-- Phase 2.6 회귀 결과 발견 — 신규 카테고리 query 시 universal SOP 미검색
-- → force-include RPC 가 universal SOP 안 가져옴 → 일반/중대 보고 절차 답변 불가
-- 본 마이그레이션: universal SOPs 의 meta.incident_nodes 에 모든 카테고리 nodes 추가
-- (모든 사건사고 보고는 일반/중대 분류 적용 — universal applicability)

BEGIN;

-- (공통) 일반 사건사고 보고지침 — 모든 incident 카테고리 universal
UPDATE nexus_documents
SET meta = jsonb_set(
  COALESCE(meta, '{}'::jsonb),
  '{incident_nodes}',
  '["사건사고보고", "인사사고", "고객상해", "성희롱", "괴롭힘", "정보유출", "근로자안전", "직원상해", "매장사고", "응급대응", "윤리보고"]'::jsonb
)
WHERE title = '(공통) 일반 사건사고 보고지침'
  AND status = 'active' AND superseded_by IS NULL;

-- (공통) 중대 사건사고 보고지침 — 동일
UPDATE nexus_documents
SET meta = jsonb_set(
  COALESCE(meta, '{}'::jsonb),
  '{incident_nodes}',
  '["사건사고보고", "인사사고", "고객상해", "성희롱", "괴롭힘", "정보유출", "근로자안전", "직원상해", "매장사고", "응급대응", "윤리보고"]'::jsonb
)
WHERE title = '(공통) 중대 사건사고 보고지침'
  AND status = 'active' AND superseded_by IS NULL;

-- 검증
SELECT title, meta->'incident_nodes' AS incident_nodes
FROM nexus_documents
WHERE title IN ('(공통) 일반 사건사고 보고지침', '(공통) 중대 사건사고 보고지침')
  AND status = 'active' AND superseded_by IS NULL;

COMMIT;

-- PostgREST 스키마 캐시 reload
NOTIFY pgrst, 'reload schema';
