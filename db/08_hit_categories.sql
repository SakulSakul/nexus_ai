-- ============================================================
--  NEXUS AI · query_logs.hit_categories (사규 인용 분포 정확화)
--
--  배경: _tab_radar 의 카테고리 분포가 query_logs.category (사용자
--  selectbox 값) 에 의존했으나, "전체" 선택 시 NULL 한 덩어리로
--  뭉치고 multi-category 사규 인용을 반영하지 못함.
--
--  본 마이그: hit_categories text[] 신설. chatbot.py 가 검색 결과
--  contexts 의 nexus_chunks.categories 를 평탄화(중복 허용) 적재.
--  ⚠️ chatbot.py 가 c.get("categories") 를 읽으려면 db/09 의
--     nexus_hybrid_search RPC 시그니처 확장이 함께 적용되어야 함.
--
--  실행 순서: 본 파일 → db/09 → PostgREST 스키마 캐시 reload.
-- ============================================================

alter table query_logs
  add column if not exists hit_categories text[] not null default '{}';

-- 카테고리별 unnest 집계 가속용 GIN.
-- (admin _tab_radar 가 client-side aggregate 하지만 향후 server-side
--  unnest+group by 로 옮길 때를 위한 선제 인덱스.)
create index if not exists idx_query_logs_hit_categories
  on query_logs using gin (hit_categories);

-- PostgREST 스키마 캐시 즉시 리로드 (신규 컬럼이 supabase-py 에 즉시 보이게)
notify pgrst, 'reload schema';
