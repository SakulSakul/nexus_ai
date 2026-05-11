-- ============================================================
--  DF COMPASS · nexus_hybrid_search_v2 → v3 로직 (동일 이름 REPLACE)
--
--  배경:
--  - v2 의 keyword_hits 는 plainto_tsquery('simple', query_text) 를
--    썼는데, 한국어 자연어 질문은 조사가 토큰에 붙어 매칭률이 낮음.
--  - Python 측 nexus_build_keyword_tsquery 가 조사 제거 후
--    "고객:* | 매장:* | 처리:*" 형태의 정식 tsquery 문자열을 만들어
--    넘긴다. RPC 는 이를 to_tsquery('simple', …) 로 받아야 한다.
--
--  변경:
--  - plainto_tsquery → to_tsquery 로 교체
--  - query_text NULL/공백/잘못된 구문 가드: NULLIF(TRIM(...), '') IS NOT NULL
--  - to_tsquery 가 잘못된 표현으로 raise 하지 않도록 키워드 측만 가드.
--    (vector 측은 query_text 무관)
--
--  시그니처 무변경 — Python 호출 코드는 그대로.
--  기존 v2 함수와 동일 이름으로 CREATE OR REPLACE.
-- ============================================================

create or replace function nexus_hybrid_search_v2(
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
        order by ts_rank(c.text_tsv, to_tsquery('simple', query_text)) desc
      ) as rnk
    from nexus_chunks c
    join nexus_documents d on d.id = c.document_id
    where d.status = 'active'
      and d.superseded_by is null
      -- 빈/공백 query_text 가드 — to_tsquery 는 빈 입력에 syntax error 를 던진다.
      and nullif(trim(query_text), '') is not null
      and c.text_tsv @@ to_tsquery('simple', query_text)
    order by ts_rank(c.text_tsv, to_tsquery('simple', query_text)) desc
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

-- PostgREST 스키마 캐시 reload.
notify pgrst, 'reload schema';
