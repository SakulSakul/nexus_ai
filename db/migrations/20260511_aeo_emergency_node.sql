-- ============================================================
--  DF COMPASS · AEO 출입통제 '응급대응' 노드 부여 (idempotent)
--
--  목적: classifier 가 종결형 트리거("다쳤어요"/"넘어졌어"/"미끄러져"/
--  "전도"/"낙상") 에서 '응급대응' 노드를 emit 했을 때 AEO 출입통제만
--  matched → boost → top-5 surface 안정화.
--
--  PR #72 에서 이미 '응급대응' 을 부여했을 수 있으나, NOT @> 가드로
--  중복 부여 차단 — 재실행 안전.
-- ============================================================

UPDATE nexus_documents
SET meta = jsonb_set(
  meta,
  '{incident_nodes}',
  COALESCE(meta->'incident_nodes', '[]'::jsonb) || '["응급대응"]'::jsonb
)
WHERE title ILIKE '%AEO 출입통제%'
  AND status = 'active'
  AND NOT (meta->'incident_nodes' @> '["응급대응"]'::jsonb);

-- 검증
SELECT title, meta->'incident_nodes' AS incident_nodes
FROM nexus_documents
WHERE status = 'active' AND meta ? 'incident_nodes'
ORDER BY title;
