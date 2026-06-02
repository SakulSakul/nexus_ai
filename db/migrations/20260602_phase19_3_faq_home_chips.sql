-- PR-Phase-19.3: FAQ Cache 홈 칩(home chip) 큐레이션 컬럼.
-- "캐시됨"과 "홈 노출" 분리: 승인·비critical FAQ 중 show_on_home=true 만 칩 노출.
-- 휴가신청 등 범위밖/오해소지 FAQ 는 캐시엔 두되 칩에서 제외.
-- 선례: db/migrations/20260527_phase18_faq_cache.sql
BEGIN;

ALTER TABLE nexus_faq_cache
  ADD COLUMN IF NOT EXISTS show_on_home BOOLEAN NOT NULL DEFAULT false,
  ADD COLUMN IF NOT EXISTS home_label   TEXT,
  ADD COLUMN IF NOT EXISTS home_order   INTEGER NOT NULL DEFAULT 0;

CREATE INDEX IF NOT EXISTS idx_faq_home_chips
  ON nexus_faq_cache(show_on_home, approved, is_critical, home_order);

NOTIFY pgrst, 'reload schema';

COMMIT;
