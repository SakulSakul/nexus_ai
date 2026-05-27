-- PR-Phase-18.1: FAQ Cache & Fast Path — 큐레이션 가능한 FAQ 답변 캐시.
-- 선례 미러링: db/migrations/20260513_phase7_auto_cache.sql (nexus_classification_cache).
-- TEXT UNIQUE 직접 키 (SHA-256 미도입) + approved 게이트(컴플라이언스 검토) 추가.
-- 18.1 범위: 테이블/모듈/Admin 큐레이션만. Fast Path 응답 경로 주입은 18.2.

BEGIN;

CREATE TABLE IF NOT EXISTS nexus_faq_cache (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  query_normalized TEXT NOT NULL UNIQUE,   -- lookup 키 (공백+lowercase 정규화, 해시 아님)
  query_display   TEXT NOT NULL,           -- 큐레이터가 입력한 원문 (UI 표시용)
  answer_text     TEXT NOT NULL DEFAULT '',
  category        nexus_category,
  is_critical     BOOLEAN NOT NULL DEFAULT false,  -- true 면 Fast Path 서빙 금지(핫라인 우회 차단)
  incident_nodes  JSONB DEFAULT '[]'::jsonb,
  source          TEXT NOT NULL DEFAULT 'manual',  -- 'manual'|'precompute'|'query_logs'(Phase2)
  approved        BOOLEAN NOT NULL DEFAULT false,  -- 컴플라이언스 검토 게이트
  approved_by     TEXT,
  approved_at     TIMESTAMPTZ,
  hit_count       INTEGER DEFAULT 0,
  last_hit_at     TIMESTAMPTZ,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_faq_query
  ON nexus_faq_cache(query_normalized);
CREATE INDEX IF NOT EXISTS idx_faq_active
  ON nexus_faq_cache(approved, is_critical);

-- 선례 동일: write 는 admin(service_role), read 는 응답 경로(anon)가 service 미경유로
-- 직접 select 하므로 RLS off. critical 우회는 is_critical 필터로 애플리케이션에서 차단.
ALTER TABLE nexus_faq_cache DISABLE ROW LEVEL SECURITY;

NOTIFY pgrst, 'reload schema';

COMMIT;
