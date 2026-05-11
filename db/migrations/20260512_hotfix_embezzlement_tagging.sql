-- Hotfix: 횡령/배임 카테고리 — doc 태깅 + universal SOP 확장
-- 실 사용자 query "회사 돈을 훔치면 어떻게 됨?" 답변의 ⚖️/📂 모두 "검색 안됨"
-- → 4-layer fix (이 PR 단일 SQL + 코드 3 파일)

BEGIN;

-- 임직원 징계기준 — 횡령 조항 보유
UPDATE nexus_documents
SET meta = jsonb_set(
  COALESCE(meta, '{}'::jsonb),
  '{incident_nodes}',
  (COALESCE(meta->'incident_nodes', '[]'::jsonb) ||
   '["횡령", "배임", "금전사고", "절도", "비위행위"]'::jsonb)
)
WHERE title ILIKE '%임직원%징계%'
  AND status = 'active' AND superseded_by IS NULL;

-- 윤리강령 / 행동기준 / 윤리경영 / 복무 (있는 경우)
UPDATE nexus_documents
SET meta = jsonb_set(
  COALESCE(meta, '{}'::jsonb),
  '{incident_nodes}',
  (COALESCE(meta->'incident_nodes', '[]'::jsonb) ||
   '["횡령", "배임", "금전사고", "비위행위", "윤리위반"]'::jsonb)
)
WHERE (title ILIKE '%윤리강령%' OR title ILIKE '%행동기준%'
       OR title ILIKE '%윤리경영%' OR title ILIKE '%임직원%복무%')
  AND status = 'active' AND superseded_by IS NULL;

-- universal SOPs — 횡령도 사건사고 보고 대상
UPDATE nexus_documents
SET meta = jsonb_set(
  COALESCE(meta, '{}'::jsonb),
  '{incident_nodes}',
  '["사건사고보고", "인사사고", "고객상해", "성희롱", "괴롭힘", "정보유출",
    "근로자안전", "직원상해", "매장사고", "응급대응", "윤리보고",
    "횡령", "배임", "금전사고", "비위행위", "윤리위반"]'::jsonb
)
WHERE title IN ('(공통) 일반 사건사고 보고지침', '(공통) 중대 사건사고 보고지침')
  AND status = 'active' AND superseded_by IS NULL;

-- 중복 제거 (jsonb dedup)
UPDATE nexus_documents
SET meta = jsonb_set(
  meta,
  '{incident_nodes}',
  (SELECT to_jsonb(array_agg(DISTINCT value))
   FROM jsonb_array_elements_text(meta->'incident_nodes') value)
)
WHERE meta ? 'incident_nodes'
  AND jsonb_array_length(meta->'incident_nodes') > 0;

-- 검증
SELECT title, meta->'incident_nodes' AS incident_nodes
FROM nexus_documents
WHERE meta->'incident_nodes' ? '횡령'
  AND status = 'active' AND superseded_by IS NULL
ORDER BY title;

COMMIT;

NOTIFY pgrst, 'reload schema';
