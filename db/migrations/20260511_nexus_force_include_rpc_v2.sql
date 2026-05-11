-- ============================================================
--  DF COMPASS · Force-include RPC + 진단 RPC (Track C v2)
--
--  목적:
--  - PR #79 의 Python-side table query 가 라이브에서 0 chunks 회귀
--  - SQL-side intersect 로 layer 1 신뢰성 ↑
--  - Layer 2/3 fallback 은 retriever Python 측에서 구현
--
--  SECURITY DEFINER 로 anon/authenticated 가 호출해도 nexus_documents.meta
--  조회 가능 (RLS 우회). 신규 RPC 만 추가, 기존 시그니처 변경 없음.
-- ============================================================

-- ─────────────────────────────────────────────
-- 1) Main RPC: incident node 매칭 docs 의 모든 청크 반환
-- ─────────────────────────────────────────────
CREATE OR REPLACE FUNCTION nexus_force_include_chunks_by_incident_nodes(
  p_nodes text[]
)
RETURNS TABLE (
  id uuid,
  document_id uuid,
  chunk_idx integer,
  article_no text,
  text text,
  doc_title text,
  doc_incident_nodes jsonb,
  matched_node_count integer
)
LANGUAGE SQL
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
  SELECT
    c.id,
    c.document_id,
    c.chunk_idx,
    c.article_no::text,
    c.text,
    d.title AS doc_title,
    (d.meta->'incident_nodes') AS doc_incident_nodes,
    (
      SELECT count(*)::integer
      FROM jsonb_array_elements_text(d.meta->'incident_nodes') AS node
      WHERE node = ANY(p_nodes)
    ) AS matched_node_count
  FROM nexus_chunks c
  JOIN nexus_documents d ON c.document_id = d.id
  WHERE d.status = 'active'
    AND d.meta ? 'incident_nodes'
    AND (d.meta->'incident_nodes')::jsonb ?| p_nodes;
$$;

GRANT EXECUTE ON FUNCTION nexus_force_include_chunks_by_incident_nodes(text[])
  TO service_role, authenticated, anon;


-- ─────────────────────────────────────────────
-- 2) Diagnostic RPC: doc 별 매칭 정보 (청크 X, doc 만)
-- ─────────────────────────────────────────────
CREATE OR REPLACE FUNCTION nexus_diagnose_incident_node_matching(
  p_nodes text[]
)
RETURNS TABLE (
  doc_id uuid,
  doc_title text,
  doc_status text,
  doc_incident_nodes jsonb,
  matched_nodes text[],
  total_chunks integer
)
LANGUAGE SQL
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
  SELECT
    d.id AS doc_id,
    d.title AS doc_title,
    d.status::text AS doc_status,
    d.meta->'incident_nodes' AS doc_incident_nodes,
    ARRAY(
      SELECT node
      FROM jsonb_array_elements_text(d.meta->'incident_nodes') AS node
      WHERE node = ANY(p_nodes)
    ) AS matched_nodes,
    (SELECT count(*)::integer FROM nexus_chunks WHERE document_id = d.id) AS total_chunks
  FROM nexus_documents d
  WHERE d.status = 'active'
    AND d.meta ? 'incident_nodes';
$$;

GRANT EXECUTE ON FUNCTION nexus_diagnose_incident_node_matching(text[])
  TO service_role, authenticated, anon;

-- PostgREST 스키마 캐시 reload
NOTIFY pgrst, 'reload schema';


-- ─────────────────────────────────────────────
-- 3) 검증 쿼리 (참조용 — 실행 후 결과 확인)
-- ─────────────────────────────────────────────

-- 3-1. RPC 동작 확인 — 청크 총 수
SELECT count(*) AS total_force_chunks
FROM nexus_force_include_chunks_by_incident_nodes(
  ARRAY['고객상해', '응급대응', '인사사고', '직원상해', '고객관리', '시설안전', '안전관리']
);

-- 3-2. 문서별 청크 수 분포
SELECT doc_title, count(*) AS chunk_count
FROM nexus_force_include_chunks_by_incident_nodes(
  ARRAY['고객상해', '응급대응', '인사사고', '직원상해', '고객관리', '시설안전', '안전관리']
)
GROUP BY doc_title
ORDER BY chunk_count DESC;

-- 3-3. 매칭 진단 — 어떤 doc 가 어떤 노드로 매칭되는지
SELECT doc_title, doc_status, matched_nodes, total_chunks
FROM nexus_diagnose_incident_node_matching(
  ARRAY['고객상해', '응급대응', '인사사고', '직원상해', '고객관리', '시설안전', '안전관리']
)
WHERE array_length(matched_nodes, 1) > 0
ORDER BY array_length(matched_nodes, 1) DESC;

-- 3-4. 매칭 안 되는 active doc (참고용 — 정상)
SELECT doc_title, doc_incident_nodes
FROM nexus_diagnose_incident_node_matching(
  ARRAY['고객상해', '응급대응', '인사사고', '직원상해', '고객관리', '시설안전', '안전관리']
)
WHERE array_length(matched_nodes, 1) IS NULL
   OR array_length(matched_nodes, 1) = 0;
