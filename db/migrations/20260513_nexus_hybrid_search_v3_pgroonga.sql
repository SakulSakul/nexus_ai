-- ============================================================
--  DF COMPASS · nexus_hybrid_search_v3_pgroonga
--
--  배경: v2 의 to_tsquery('simple', …) 한국어 형태소 분석 불가 →
--        pgroonga + TokenMecab 인덱스로 한국어 keyword 매칭 정확도 ↑.
--
--  특징:
--  - 기존 v2 와 공존. NEXUS_HYBRID_SEARCH_VARIANT 환경변수로 토글.
--  - 시그니처 v2 와 동일. query_text 는 pgroonga &@~ 형식
--    ("토큰 OR 토큰 OR 토큰") 으로 들어와야 함.
--  - Python 측 nexus_build_pgroonga_query() 가 빌드.
-- ============================================================
create or replace function nexus_hybrid_search_v3_pgroonga(
  query_embedding vector(768),
  query_text      text,
  match_count     int default 5,
  rrf_k           int default 60,
  pool_size       int default 30
)
returns table (
  id          uuid,
  document_id uuid,
  text        text,
  article_no  text,
  categories  nexus_category[],
  doc_title   text,
  doc_kind    nexus_doc_kind,
  rrf_score   double precision
)
language sql stable as $$
  with vector_hits as (
    select
      c.id,
      row_number() over (order by c.embedding <=> query_embedding) as rnk
    from nexus_chunks c
    join nexus_documents d on d.id = c.document_id
    where d.status = 'active'
      and d.superseded_by is null
    order by c.embedding <=> query_embedding
    limit pool_size
  ),
  keyword_hits as (
    select
      c.id,
      row_number() over (
        order by pgroonga_score(c.tableoid, c.ctid) desc
      ) as rnk
    from nexus_chunks c
    join nexus_documents d on d.id = c.document_id
    where d.status = 'active'
      and d.superseded_by is null
      and nullif(trim(query_text), '') is not null
      and c.text &@~ query_text
    order by pgroonga_score(c.tableoid, c.ctid) desc
    limit pool_size
  ),
  fused as (
    select
      coalesce(v.id, k.id) as id,
      (
        coalesce(1.0 / (rrf_k + v.rnk), 0)
        + coalesce(1.0 / (rrf_k + k.rnk), 0)
      )::double precision as rrf_score
    from vector_hits v
    full outer join keyword_hits k on k.id = v.id
  )
  select
    c.id,
    c.document_id,
    c.text,
    c.article_no,
    c.categories,
    d.title       as doc_title,
    d.doc_kind,
    f.rrf_score
  from fused f
  join nexus_chunks c    on c.id = f.id
  join nexus_documents d on d.id = c.document_id
  order by f.rrf_score desc
  limit match_count;
$$;
notify pgrst, 'reload schema';
