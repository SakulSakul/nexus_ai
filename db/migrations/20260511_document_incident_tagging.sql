-- ============================================================
--  DF COMPASS · Document-level incident node tagging (Phase 1)
--
--  목적:
--  - AEO 출입통제 vs AEO 업무절차서 같이 제목이 비슷한 문서 혼동 해소
--  - 매장 사고 도메인 핵심 문서를 incident node 로 명시 식별
--  - retrieval rerank 가 nexus_documents.meta.incident_nodes 와
--    nexus_classify_to_incident_nodes(질문) 의 교집합을 보고
--    chunk.rrf_score 에 +0.15 가산
--
--  스키마 변경 없음 — 기존 nexus_documents.meta jsonb 컬럼에 키 추가만.
--  RPC `nexus_hybrid_search_v2` 시그니처 무변경.
--
--  실행: Supabase SQL Editor (사용자 수동).
-- ============================================================

UPDATE nexus_documents
SET meta = COALESCE(meta, '{}'::jsonb) || jsonb_build_object(
  'incident_nodes',
  jsonb_build_array('고객상해', '인사사고', '매장사고', '응급대응')
)
WHERE title ILIKE '%AEO 출입통제%' AND status = 'active';

UPDATE nexus_documents
SET meta = COALESCE(meta, '{}'::jsonb) || jsonb_build_object(
  'incident_nodes',
  jsonb_build_array('보세품통관', '재고관리')
)
WHERE title ILIKE '%AEO 업무절차%' AND status = 'active';

UPDATE nexus_documents
SET meta = COALESCE(meta, '{}'::jsonb) || jsonb_build_object(
  'incident_nodes',
  jsonb_build_array('고객상해', '매장사고', '안전점검', '인사사고')
)
WHERE title ILIKE '%매장 안전보건관리 지침%' AND status = 'active';

UPDATE nexus_documents
SET meta = COALESCE(meta, '{}'::jsonb) || jsonb_build_object(
  'incident_nodes',
  jsonb_build_array('인사사고', '근로자안전', '안전점검')
)
WHERE title ILIKE '%안전보건관리규정%' AND status = 'active';

UPDATE nexus_documents
SET meta = COALESCE(meta, '{}'::jsonb) || jsonb_build_object(
  'incident_nodes',
  jsonb_build_array('사건사고보고', '인사사고', '고객상해')
)
WHERE title ILIKE '%일반 사건사고 보고지침%' AND status = 'active';

UPDATE nexus_documents
SET meta = COALESCE(meta, '{}'::jsonb) || jsonb_build_object(
  'incident_nodes',
  jsonb_build_array('윤리보고', '사건사고보고')
)
WHERE title ILIKE '%CREDO%' AND status = 'active';

-- 검증
SELECT title, meta->'incident_nodes' AS incident_nodes
FROM nexus_documents
WHERE status = 'active' AND meta ? 'incident_nodes'
ORDER BY title;
