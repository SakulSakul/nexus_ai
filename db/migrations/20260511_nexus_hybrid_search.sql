-- ============================================================
--  DF COMPASS · Tier 2 — 신규 하이브리드 검색 (RRF) RPC
--
--  배경:
--  - 본 레포에는 이미 nexus_hybrid_search(text, vector, …) RPC 가
--    존재한다 (db/02 → db/04 → db/09 누적 정의). 본 마이그레이션은
--    그 함수를 일체 수정하지 않고, Tier 1 (query rewriting) 결과를
--    받기 위한 단순화 시그니처의 신규 함수를 v2 로 추가한다.
--  - 함수명 충돌 회피 + 롤백 안전망 위해 nexus_hybrid_search_v2 로 명명.
--    USE_HYBRID_SEARCH=False 로 토글 시 코드 경로가 즉시 기존 RPC 로
--    돌아가도록 보장.
--
--  스펙 (DF COMPASS Tier 2):
--  - vector_hits: status='active' AND superseded_by IS NULL,
--                 ORDER BY embedding <=> query_embedding LIMIT pool_size
--  - keyword_hits: 동일 필터 + text_tsv @@ plainto_tsquery('simple', query_text)
--                  ORDER BY ts_rank DESC LIMIT pool_size
--  - FULL OUTER JOIN, rrf_score = sum(1.0 / (rrf_k + rank))
--  - 최종 LIMIT match_count
--
--  실행 순서:
--    1) 본 파일 SQL Editor 실행
--    2) NOTIFY pgrst, 'reload schema'
--    3) 코드 (core/retriever.py) 의 USE_HYBRID_SEARCH=True 로 활성화
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
        order by ts_rank(c.text_tsv, plainto_tsquery('simple', query_text)) desc
      ) as rnk
    from nexus_chunks c
    join nexus_documents d on d.id = c.document_id
    where d.status = 'active'
      and d.superseded_by is null
      and c.text_tsv @@ plainto_tsquery('simple', query_text)
    order by ts_rank(c.text_tsv, plainto_tsquery('simple', query_text)) desc
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

-- PostgREST 스키마 캐시 reload — 신규 RPC 즉시 노출.
notify pgrst, 'reload schema';
