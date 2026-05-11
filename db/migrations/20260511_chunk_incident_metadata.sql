-- ============================================================
--  DF COMPASS · Chunk-level incident metadata + force-include 대상
--
--  목적: AEO 출입통제 의 응급 대응 관련 청크(Chunk 7, 8) 가
--  vector / keyword 검색에서 안 잡혀도 retrieval 단계에서 강제로
--  포함되도록 chunk-level metadata 부여.
--
--  스키마 변경: nexus_chunks 에 chunk_incident_nodes jsonb 컬럼 추가
--  (DEFAULT '[]'::jsonb). 기존 데이터 영향 없음.
-- ============================================================

-- chunk-level incident_nodes 컬럼 추가
ALTER TABLE nexus_chunks
ADD COLUMN IF NOT EXISTS chunk_incident_nodes jsonb DEFAULT '[]'::jsonb;

-- AEO 출입통제 응급 대응 관련 청크 태깅
-- Chunk 7: 위험 등급 분류표 (인명사고(고객) 1등급 포함)
UPDATE nexus_chunks
SET chunk_incident_nodes = '["고객상해", "응급대응", "인사사고"]'::jsonb
WHERE id = '7e85fe80-0bc7-473a-a8f9-18231f26df94';

-- Chunk 8: 위기상황 대응표 (병원 후송, 응급조치)
UPDATE nexus_chunks
SET chunk_incident_nodes = '["고객상해", "응급대응", "인사사고"]'::jsonb
WHERE id = 'd7b45c21-6917-487a-a19a-7f0f874b2e87';

-- GIN 인덱스 — incident_nodes JSON 검색용
CREATE INDEX IF NOT EXISTS idx_nexus_chunks_chunk_incident_nodes
ON nexus_chunks USING GIN (chunk_incident_nodes);

-- 검증
SELECT id, chunk_idx, chunk_incident_nodes, substring(text, 1, 200)
FROM nexus_chunks
WHERE chunk_incident_nodes != '[]'::jsonb
ORDER BY chunk_idx;

-- PostgREST 스키마 캐시 reload
NOTIFY pgrst, 'reload schema';
