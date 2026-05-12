-- Phase 7 X+: LLM-driven RAG 자동화 + cache
-- 두 테이블 (classification cache, golden cache) — 동일 query 재호출 비용 zero.

BEGIN;

CREATE TABLE IF NOT EXISTS nexus_classification_cache (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  query_normalized TEXT NOT NULL UNIQUE,
  incident_nodes JSONB NOT NULL,
  model_id TEXT NOT NULL,
  hit_count INTEGER DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  last_used_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_cls_query
  ON nexus_classification_cache(query_normalized);

CREATE TABLE IF NOT EXISTS nexus_golden_cache (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  incident_signature TEXT NOT NULL UNIQUE,
  expected_clauses JSONB NOT NULL,
  required_docs JSONB,
  model_id TEXT NOT NULL,
  hit_count INTEGER DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  last_used_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_golden_sig
  ON nexus_golden_cache(incident_signature);

ALTER TABLE nexus_classification_cache DISABLE ROW LEVEL SECURITY;
ALTER TABLE nexus_golden_cache DISABLE ROW LEVEL SECURITY;

NOTIFY pgrst, 'reload schema';

COMMIT;
