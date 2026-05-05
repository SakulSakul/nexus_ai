-- ============================================================
--  NEXUS AI · nexus_hybrid_search 확장 (chunk categories 반환)
--
--  배경: query_logs.hit_categories (db/08) 적재를 위해 RPC 가
--  chunk 단위 categories nexus_category[] 를 결과에 포함해야 함.
--  기존 db/04_beta_hooks.sql:62-172 정의를 베이스로 RETURNS TABLE
--  에 categories 컬럼 1개만 추가하고 두 SELECT 절(주 + fallback)에
--  c.categories 만 추가. BM25/vector/RRF/effective_date/fallback
--  로직 일체 무변경.
--
--  RPC 02 → 04 → 09 (create or replace) 패턴.
--  실행 순서: db/08 → 본 파일 → PostgREST 스키마 캐시 reload.
-- ============================================================

create or replace function nexus_hybrid_search(
  query_text         text,
  query_embed        vector(768),
  filter_categories  nexus_category[]  default null,
  filter_doc_kinds   nexus_doc_kind[]  default null,
  top_k              int               default 3,
  fanout             int               default 30,
  rrf_k              int               default 60,
  fallback_to_common boolean           default true,
  as_of_date         date              default current_date
)
returns table (
  chunk_id          uuid,
  document_id       uuid,
  doc_title         text,
  doc_kind          nexus_doc_kind,
  article_no        text,
  case_no           text,
  text              text,
  score             double precision,
  owning_department text,
  categories        nexus_category[]
) language plpgsql stable as $$
declare
  effective_categories nexus_category[];
  has_hits bigint;
begin
  effective_categories := filter_categories;

  return query
  with vec as (
    select c.id, row_number() over (order by c.embedding <=> query_embed) as r
      from nexus_chunks c
      join nexus_documents d on d.id = c.document_id
     where d.status = 'active'
       and (d.effective_date is null or d.effective_date <= as_of_date)
       and (effective_categories is null or c.categories && effective_categories)
       and (filter_doc_kinds is null or d.doc_kind = any(filter_doc_kinds))
     order by c.embedding <=> query_embed
     limit fanout
  ),
  kw as (
    select c.id,
           row_number() over (order by similarity(c.text, query_text) desc) as r
      from nexus_chunks c
      join nexus_documents d on d.id = c.document_id
     where d.status = 'active'
       and (d.effective_date is null or d.effective_date <= as_of_date)
       and (effective_categories is null or c.categories && effective_categories)
       and (filter_doc_kinds is null or d.doc_kind = any(filter_doc_kinds))
       and (c.text % query_text or c.text_tsv @@ plainto_tsquery('simple', query_text))
     order by similarity(c.text, query_text) desc
     limit fanout
  ),
  fused as (
    select coalesce(vec.id, kw.id) as id,
           (coalesce(1.0/(rrf_k + vec.r), 0) + coalesce(1.0/(rrf_k + kw.r), 0))::double precision as s
      from vec full outer join kw on vec.id = kw.id
  )
  select c.id, c.document_id, d.title, d.doc_kind, c.article_no, c.case_no, c.text, f.s,
         d.owning_department, c.categories
    from fused f
    join nexus_chunks c on c.id = f.id
    join nexus_documents d on d.id = c.document_id
   order by f.s desc
   limit top_k;

  get diagnostics has_hits = row_count;

  if (has_hits = 0) and fallback_to_common
     and (filter_categories is not null)
     and not ('공통' = any(filter_categories)) then
    return query
    with vec as (
      select c.id, row_number() over (order by c.embedding <=> query_embed) as r
        from nexus_chunks c
        join nexus_documents d on d.id = c.document_id
       where d.status = 'active'
         and (d.effective_date is null or d.effective_date <= as_of_date)
         and c.categories && array['공통']::nexus_category[]
         and (filter_doc_kinds is null or d.doc_kind = any(filter_doc_kinds))
       order by c.embedding <=> query_embed
       limit fanout
    ),
    kw as (
      select c.id,
             row_number() over (order by similarity(c.text, query_text) desc) as r
        from nexus_chunks c
        join nexus_documents d on d.id = c.document_id
       where d.status = 'active'
         and (d.effective_date is null or d.effective_date <= as_of_date)
         and c.categories && array['공통']::nexus_category[]
         and (filter_doc_kinds is null or d.doc_kind = any(filter_doc_kinds))
         and (c.text % query_text or c.text_tsv @@ plainto_tsquery('simple', query_text))
       order by similarity(c.text, query_text) desc
       limit fanout
    ),
    fused as (
      select coalesce(vec.id, kw.id) as id,
             (coalesce(1.0/(rrf_k + vec.r), 0) + coalesce(1.0/(rrf_k + kw.r), 0))::double precision as s
        from vec full outer join kw on vec.id = kw.id
    )
    select c.id, c.document_id, d.title, d.doc_kind, c.article_no, c.case_no, c.text, f.s,
           d.owning_department, c.categories
      from fused f
      join nexus_chunks c on c.id = f.id
      join nexus_documents d on d.id = c.document_id
     order by f.s desc
     limit top_k;
  end if;
end;
$$;

notify pgrst, 'reload schema';
