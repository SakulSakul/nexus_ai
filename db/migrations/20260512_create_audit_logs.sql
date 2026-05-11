-- Phase 3: Audit log 영구 저장 (dual-LLM provenance)
-- 모든 query 의 Gemini 답변 + Claude 검증 결과 영구 보관 — 사용자 결정.
-- Phase 2.6 회귀 결과 세션 손실 방지 + drift detection / 분석 / 디버깅 토대.

CREATE TABLE IF NOT EXISTS nexus_audit_logs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

  source TEXT NOT NULL,
  query TEXT NOT NULL,
  rewritten_query TEXT,
  incident_nodes JSONB,

  retrieved_chunk_ids JSONB,
  retrieved_chunk_count INTEGER,

  gemini_model_id TEXT,
  gemini_answer TEXT,
  gemini_latency_ms INTEGER,

  claude_model_id TEXT,
  claude_verdict TEXT,
  claude_score NUMERIC,
  claude_report JSONB,
  claude_latency_ms INTEGER,

  total_latency_ms INTEGER,
  notes TEXT
);

CREATE INDEX IF NOT EXISTS idx_audit_created_at
  ON nexus_audit_logs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_verdict
  ON nexus_audit_logs(claude_verdict);
CREATE INDEX IF NOT EXISTS idx_audit_source
  ON nexus_audit_logs(source);
CREATE INDEX IF NOT EXISTS idx_audit_incident_nodes
  ON nexus_audit_logs USING GIN (incident_nodes);

-- RLS 해제 (admin/service_role INSERT 안전성 우선)
ALTER TABLE nexus_audit_logs DISABLE ROW LEVEL SECURITY;

-- PostgREST 스키마 캐시 reload
NOTIFY pgrst, 'reload schema';

-- 검증
SELECT 'nexus_audit_logs created' AS result,
       COUNT(*) AS initial_rows
FROM nexus_audit_logs;
