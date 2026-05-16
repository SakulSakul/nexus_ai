-- PR-Validation-Results-Persistence
-- Validation 결과 영속화 — session_state 손실 방지 + 회귀 history 누적.

CREATE TABLE IF NOT EXISTS nexus_validation_runs (
    id BIGSERIAL PRIMARY KEY,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    total_queries INT NOT NULL,
    completed_queries INT NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'running',
    note TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_validation_runs_status ON nexus_validation_runs(status);
CREATE INDEX IF NOT EXISTS idx_validation_runs_started ON nexus_validation_runs(started_at DESC);

CREATE TABLE IF NOT EXISTS nexus_validation_results (
    id BIGSERIAL PRIMARY KEY,
    run_id BIGINT NOT NULL REFERENCES nexus_validation_runs(id) ON DELETE CASCADE,
    query_idx INT NOT NULL,
    query_text TEXT NOT NULL,
    answer_text TEXT,
    answer_chars INT,
    elapsed_seconds REAL,
    is_critical BOOLEAN DEFAULT FALSE,
    confidence TEXT,
    matched_doc_count INT,
    cited_docs JSONB,
    button_type TEXT,
    error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_validation_results_run ON nexus_validation_results(run_id);
CREATE INDEX IF NOT EXISTS idx_validation_results_idx ON nexus_validation_results(run_id, query_idx);
