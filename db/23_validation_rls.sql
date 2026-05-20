-- ============================================================
--  DF COMPASS · Validation Mode RLS 영구 기록
--    nexus_validation_runs / nexus_validation_results 의 anon
--    INSERT/SELECT/UPDATE 허용 정책 (admin 전용 도구)
--    Supabase 측 적용 완료 (2026-05-20). 재배포 환경 대응용.
-- ============================================================

-- runs 테이블
alter table nexus_validation_runs enable row level security;

drop policy if exists "anon_all_validation_runs" on nexus_validation_runs;
create policy "anon_all_validation_runs"
on nexus_validation_runs for all
to anon, authenticated
using (true)
with check (true);

-- results 테이블
alter table nexus_validation_results enable row level security;

drop policy if exists "anon_all_validation_results" on nexus_validation_results;
create policy "anon_all_validation_results"
on nexus_validation_results for all
to anon, authenticated
using (true)
with check (true);
