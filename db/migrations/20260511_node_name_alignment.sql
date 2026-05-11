-- ============================================================
--  DF COMPASS · Document incident_nodes alignment with classifier
--
--  배경:
--  - PR #72 에서 AEO 출입통제 meta.incident_nodes 에 '응급대응' 부여
--  - 본 PR (boost tuning) 의 새 트리거 ("다쳤어요"/"넘어졌어") 는
--    '응급조치' 노드를 emit → '응급대응' 과 명칭 mismatch → boost 안 됨
--  - 본 마이그레이션은 classifier 가 실제로 emit 하는 노드명
--    ('응급조치', '시설안전', '안전사고') 을 핵심 문서의
--    meta.incident_nodes 에 추가해 매칭 성공률 회복
--
--  RPC 시그니처 / 컬럼 변경 없음. jsonb 키 append 만.
-- ============================================================

-- AEO 출입통제: '응급조치' 단독 부여 (차별화 키)
UPDATE nexus_documents
SET meta = jsonb_set(
  meta,
  '{incident_nodes}',
  (meta->'incident_nodes') || jsonb_build_array('응급조치', '시설안전', '안전사고')
)
WHERE title ILIKE '%AEO 출입통제%' AND status = 'active';

-- 매장 안전보건관리 지침: '시설안전', '안전사고' 추가
UPDATE nexus_documents
SET meta = jsonb_set(
  meta,
  '{incident_nodes}',
  (meta->'incident_nodes') || jsonb_build_array('시설안전', '안전사고')
)
WHERE title ILIKE '%매장 안전보건관리 지침%' AND status = 'active';

-- 검증
SELECT title, meta->'incident_nodes' AS incident_nodes
FROM nexus_documents
WHERE status = 'active' AND meta ? 'incident_nodes'
ORDER BY title;
