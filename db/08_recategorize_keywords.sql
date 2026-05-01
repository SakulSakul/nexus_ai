-- ============================================================
--  NEXUS AI · critical_keywords 카테고리 보정
--  - 음주운전·뺑소니: safety(응급) → harassment(신고·조사) 이동
--    응급 안전 사고가 아니라 윤리·법규 위반이라 routing 톤 안 맞음.
--    safety routing 은 119 톤이고 harassment(=신고·조사) 는 CSR/핫라인 톤.
-- ============================================================

-- harassment 로 신규 등록 (없으면 추가)
insert into critical_keywords (kind, keyword) values
  ('harassment','음주운전'),
  ('harassment','뺑소니')
on conflict (kind, keyword) do nothing;

-- safety 의 동일 키워드 비활성화 (delete 보다 비활성화로 audit 보존)
update critical_keywords
   set is_active = false,
       updated_at = now()
 where kind = 'safety'
   and keyword in ('음주운전','뺑소니');

notify pgrst, 'reload schema';
