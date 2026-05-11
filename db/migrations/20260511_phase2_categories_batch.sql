-- Phase 2 batch: 5 incident 카테고리 baseline 확장
-- 신규 incident_nodes 어휘: 성희롱, 괴롭힘, 정보유출
-- 기존 customer_injury 태깅 무변경 (universal SOP 2 docs, 안전 4 docs 등은 별도)

BEGIN;

-- ============ HR/윤리 카테고리 (Phase 2.1, 2.2) ============

-- (공통) 임직원 징계기준 — 모든 인사 incident 에 universal
UPDATE nexus_documents
SET meta = jsonb_set(
  COALESCE(meta, '{}'::jsonb),
  '{incident_nodes}',
  '["사건사고보고", "인사사고", "윤리보고", "성희롱", "괴롭힘", "정보유출", "근로자안전"]'::jsonb
)
WHERE title = '(공통) 임직원 징계기준' AND status = 'active' AND superseded_by IS NULL;

-- (인사) 성희롱 예방 지침
UPDATE nexus_documents
SET meta = jsonb_set(
  COALESCE(meta, '{}'::jsonb), '{incident_nodes}',
  '["성희롱", "윤리보고", "사건사고보고", "인사사고"]'::jsonb
)
WHERE title = '(인사) 성희롱 예방 지침' AND status = 'active' AND superseded_by IS NULL;

-- (인사) 직장 내 괴롭힘 예방·대응지침
UPDATE nexus_documents
SET meta = jsonb_set(
  COALESCE(meta, '{}'::jsonb), '{incident_nodes}',
  '["괴롭힘", "윤리보고", "사건사고보고", "인사사고"]'::jsonb
)
WHERE title = '(인사) 직장 내 괴롭힘 예방·대응지침' AND status = 'active' AND superseded_by IS NULL;

-- (공통) 신세계그룹 CREDO 강화
UPDATE nexus_documents
SET meta = jsonb_set(
  COALESCE(meta, '{}'::jsonb), '{incident_nodes}',
  '["윤리보고", "사건사고보고", "성희롱", "괴롭힘"]'::jsonb
)
WHERE title = '(공통) 신세계그룹 CREDO' AND status = 'active' AND superseded_by IS NULL;

-- (인사) 건전한 조직문화 조성을 위한 자율준수 지침
UPDATE nexus_documents
SET meta = jsonb_set(
  COALESCE(meta, '{}'::jsonb), '{incident_nodes}',
  '["윤리보고", "괴롭힘", "인사사고"]'::jsonb
)
WHERE title = '(인사) 건전한 조직문화 조성을 위한 자율준수 지침' AND status = 'active' AND superseded_by IS NULL;


-- ============ 정보유출 카테고리 (Phase 2.3) ============

UPDATE nexus_documents
SET meta = jsonb_set(
  COALESCE(meta, '{}'::jsonb), '{incident_nodes}',
  '["정보유출", "사건사고보고"]'::jsonb
)
WHERE title = '(정보보안) 정보보호 정책서' AND status = 'active' AND superseded_by IS NULL;

UPDATE nexus_documents
SET meta = jsonb_set(
  COALESCE(meta, '{}'::jsonb), '{incident_nodes}',
  '["정보유출", "사건사고보고"]'::jsonb
)
WHERE title = '(정보보안) 정보보호 업무지침' AND status = 'active' AND superseded_by IS NULL;

UPDATE nexus_documents
SET meta = jsonb_set(
  COALESCE(meta, '{}'::jsonb), '{incident_nodes}',
  '["정보유출", "사건사고보고"]'::jsonb
)
WHERE title = '(정보보안) 개인정보보호 지침' AND status = 'active' AND superseded_by IS NULL;

UPDATE nexus_documents
SET meta = jsonb_set(
  COALESCE(meta, '{}'::jsonb), '{incident_nodes}',
  '["정보유출"]'::jsonb
)
WHERE title = '(정보보안) 운영보안 업무지침' AND status = 'active' AND superseded_by IS NULL;

UPDATE nexus_documents
SET meta = jsonb_set(
  COALESCE(meta, '{}'::jsonb), '{incident_nodes}',
  '["정보유출"]'::jsonb
)
WHERE title = '(정보보안) 생활보안 업무지침' AND status = 'active' AND superseded_by IS NULL;


-- ============ 근로자안전 카테고리 (Phase 2.4) ============
-- (안전) 안전보건관리규정 — 기존 ["인사사고","근로자안전","안전점검"] 유지 (이미 OK)

UPDATE nexus_documents
SET meta = jsonb_set(
  COALESCE(meta, '{}'::jsonb), '{incident_nodes}',
  '["근로자안전", "인사사고", "사건사고보고", "응급대응"]'::jsonb
)
WHERE title = '(안전) 중대재해 대응 지침' AND status = 'active' AND superseded_by IS NULL;

UPDATE nexus_documents
SET meta = jsonb_set(
  COALESCE(meta, '{}'::jsonb), '{incident_nodes}',
  '["근로자안전", "안전점검"]'::jsonb
)
WHERE title = '(안전) 위험성평가 지침' AND status = 'active' AND superseded_by IS NULL;

UPDATE nexus_documents
SET meta = jsonb_set(
  COALESCE(meta, '{}'::jsonb), '{incident_nodes}',
  '["근로자안전", "인사사고", "안전점검"]'::jsonb
)
WHERE title = '(안전) 물류 안전보건관리 지침' AND status = 'active' AND superseded_by IS NULL;


-- ============ 매장사고 비고객 카테고리 (Phase 2.5) ============

UPDATE nexus_documents
SET meta = jsonb_set(
  COALESCE(meta, '{}'::jsonb), '{incident_nodes}',
  '["응급대응", "매장사고", "사건사고보고"]'::jsonb
)
WHERE title = '(안전) 비상시대비대응 지침' AND status = 'active' AND superseded_by IS NULL;

UPDATE nexus_documents
SET meta = jsonb_set(
  COALESCE(meta, '{}'::jsonb), '{incident_nodes}',
  '["응급대응", "매장사고", "사건사고보고"]'::jsonb
)
WHERE title = '(안전) 실종아동 등 조기발견 지침' AND status = 'active' AND superseded_by IS NULL;

UPDATE nexus_documents
SET meta = jsonb_set(
  COALESCE(meta, '{}'::jsonb), '{incident_nodes}',
  '["고객상해", "매장사고", "안전점검"]'::jsonb
)
WHERE title = '(안전) 어린이 안전관리 지침' AND status = 'active' AND superseded_by IS NULL;

UPDATE nexus_documents
SET meta = jsonb_set(
  COALESCE(meta, '{}'::jsonb), '{incident_nodes}',
  '["사건사고보고", "안전점검"]'::jsonb
)
WHERE title = '(안전) 사건, 부적합 시정조치 지침' AND status = 'active' AND superseded_by IS NULL;


-- ============ 검증 쿼리 (output 확인용) ============

SELECT
  doc_kind,
  title,
  meta->'incident_nodes' as incident_nodes
FROM nexus_documents
WHERE meta->'incident_nodes' IS NOT NULL
  AND status = 'active'
  AND superseded_by IS NULL
ORDER BY doc_kind, title;

COMMIT;

-- PostgREST 스키마 캐시 reload
NOTIFY pgrst, 'reload schema';
