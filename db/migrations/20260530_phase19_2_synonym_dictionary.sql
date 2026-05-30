-- PR-Phase-19.2.1: 사규 동의어 자동 추출 + 검수 사전.
-- 선례 미러링: nexus_faq_cache (approved 게이트 + DISABLE RLS) + nexus_classification_cache.
-- 응답 경로 무접촉 (PR 19.2.2 에서 retrieval 통합).

BEGIN;

CREATE TABLE IF NOT EXISTS nexus_synonym_dictionary (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  primary_term    TEXT NOT NULL,
  synonym_term    TEXT NOT NULL,
  source_doc_id   UUID REFERENCES nexus_documents(id) ON DELETE SET NULL,
  source_chunk_id UUID REFERENCES nexus_chunks(id)    ON DELETE SET NULL,
  evidence_text   TEXT,
  extraction_method TEXT NOT NULL,             -- 'regex' | 'llm_assisted' | 'manual'
  confidence      DOUBLE PRECISION DEFAULT 0.0, -- 0.0 ~ 1.0
  approved        BOOLEAN NOT NULL DEFAULT false,
  approved_by     TEXT,
  approved_at     TIMESTAMPTZ,
  rejected        BOOLEAN NOT NULL DEFAULT false,
  rejected_at     TIMESTAMPTZ,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE(primary_term, synonym_term)
);

CREATE INDEX IF NOT EXISTS idx_synonym_term_approved
  ON nexus_synonym_dictionary(synonym_term, approved);
CREATE INDEX IF NOT EXISTS idx_synonym_primary
  ON nexus_synonym_dictionary(primary_term);

-- 선례 (nexus_faq_cache / nexus_classification_cache) 와 동일 정책:
-- write 는 admin(service_role), read 는 응답경로(anon) 가 직접 select.
ALTER TABLE nexus_synonym_dictionary DISABLE ROW LEVEL SECURITY;

NOTIFY pgrst, 'reload schema';

COMMIT;
