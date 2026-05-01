-- ============================================================
--  NEXUS AI · 2차 audit 보강
--  - review_results.forbidden_hit_score 컬럼 (per-sample 추적)
--  - nexus_documents.superseded_by 외래키를 ON DELETE SET NULL 로 변경
--    (v1 삭제 시 v2.superseded_by 가 NULL 로 자동 정리, 외래키 위반 차단)
-- ============================================================

-- ── 1. review_results.forbidden_hit_score ───────────────────
-- run_review 가 sums 에만 누적하던 forbidden_hit 점수를 row 단위로 영속화.
-- 회차 종료 후 어떤 샘플이 금지 키워드 위반했는지 admin 이 즉시 식별 가능.
alter table if exists review_results
  add column if not exists forbidden_hit_score double precision;

-- ── 2. nexus_documents.superseded_by — ON DELETE SET NULL ─
-- 기존: references nexus_documents(id) (no action) — v1 삭제 시 v2 가 v1 을
--       가리키고 있으면 외래키 위반으로 실패.
-- 변경: SET NULL — v1 삭제 시 v2.superseded_by 가 NULL 로 자동 정리.
do $$
begin
  alter table nexus_documents
    drop constraint if exists nexus_documents_superseded_by_fkey;

  alter table nexus_documents
    add constraint nexus_documents_superseded_by_fkey
    foreign key (superseded_by)
    references nexus_documents(id)
    on delete set null;
exception
  when others then
    -- 제약 이름이 다르거나 이미 SET NULL 인 경우 silently skip
    null;
end $$;

notify pgrst, 'reload schema';
