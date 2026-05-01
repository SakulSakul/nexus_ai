-- ============================================================
--  NEXUS AI · 베타 단계 hook 컬럼 + 감사 로그 + effective_date 필터
--  - 모든 신규 컬럼은 nullable. 기존 데이터/호출 100% 호환.
--  - 회사 계정 이관 후 SSO/RBAC/재임베딩 도입 시 스키마 변경 없이
--    바로 채워서 운영 가능하도록 미리 박아두는 슬롯들.
-- ============================================================

-- ── nexus_documents: 관리부서 + 원본 DOCX 보관 경로 ─────────
-- owning_department 는 코드(retriever/prompts)가 이미 사용 중이지만
-- 본 레포 db/01_schema.sql 에는 정의가 없어 누락된 마이그레이션을 보강.
alter table if exists nexus_documents
  add column if not exists owning_department   text,
  add column if not exists source_storage_path text;

-- ── nexus_chunks: 임베딩 모델 버전 (재임베딩 추적) ─────────
-- 모델 변경 시 어떤 청크가 구 모델로 박혀있는지 즉시 식별 → 점진 재임베딩.
alter table if exists nexus_chunks
  add column if not exists embed_model_version text;

-- ── query_logs: 베타 식별 + 미래 SSO/RBAC 슬롯 + 피드백 ────
alter table if exists query_logs
  add column if not exists env                  text,         -- 'beta-personal' | 'beta-corp' | 'prod'
  add column if not exists user_id_hash         text,         -- 회사 이관 후 SSO 식별자 해시
  add column if not exists access_level         text,         -- 'employee' | 'manager' | 'admin' (RBAC 도입 시)
  add column if not exists feedback             smallint,     -- -1=👎, 1=👍, null=무응답
  add column if not exists feedback_comment     text,
  add column if not exists embed_model_version  text;

create index if not exists idx_query_logs_env
  on query_logs (env, ts desc);
create index if not exists idx_query_logs_feedback
  on query_logs (feedback) where feedback is not null;

-- ── 관리자 감사 로그 ────────────────────────────────────────
-- 사규 업로드/archive, 핫라인/키워드 변경, 부서 갱신 등 상태 변경은
-- 누가·언제·무엇을 바꿨는지 본 테이블에 함께 기록.
create table if not exists admin_audit_logs (
  id        bigserial primary key,
  ts        timestamptz not null default now(),
  actor     text,
  action    text not null,
  target    text,
  details   jsonb not null default '{}'::jsonb
);
create index if not exists idx_admin_audit_logs_ts
  on admin_audit_logs (ts desc);
create index if not exists idx_admin_audit_logs_action
  on admin_audit_logs (action, ts desc);

-- ── nexus_hybrid_search: effective_date 필터 + owning_department 반환 ──
-- 시행일이 미래인 사규(예: 2026-07-01 시행)가 검색 결과에 노출되지 않도록
-- 차단. 회귀/미래 시뮬레이션이 필요할 때는 as_of_date 인자로 강제 가능.
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
  owning_department text
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
         d.owning_department
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
           d.owning_department
      from fused f
      join nexus_chunks c on c.id = f.id
      join nexus_documents d on d.id = c.document_id
     order by f.s desc
     limit top_k;
  end if;
end;
$$;
