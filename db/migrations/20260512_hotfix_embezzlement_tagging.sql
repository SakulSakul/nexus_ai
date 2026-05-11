-- Hotfix: 횡령/배임 카테고리 — doc 태깅 + universal SOP 확장
-- 실 사용자 query "회사 돈을 훔치면 어떻게 됨?" 답변의 ⚖️/📂 모두 "검색 안됨"
-- → 4-layer fix (PR #102 이 코드 3 파일 머지 + 본 마이그레이션)
--
-- 보강판 (PR #103): pre-flight SELECT preview + rollback 주석.
-- 사용자가 SQL Editor 에서 preview 결과 보고 영향 doc 범위 확인 후 COMMIT.

BEGIN;

-- ============ Pre-flight 확인 (실행 전 SELECT 로 영향 doc 확인) ============
-- 다음 두 SELECT 결과를 보고 의도한 doc 만 매칭됐는지 확인.
-- 매칭 결과가 의외면 해당 UPDATE 빼고 재실행 (커서로 부분 실행 권장).

SELECT 'preview: 임직원 징계기준 매칭' AS check_kind, title
FROM nexus_documents
WHERE title ILIKE '%임직원%징계%'
  AND status = 'active' AND superseded_by IS NULL;

SELECT 'preview: 윤리강령/행동기준 매칭' AS check_kind, title
FROM nexus_documents
WHERE (title ILIKE '%윤리강령%' OR title ILIKE '%행동기준%'
       OR title ILIKE '%윤리경영%' OR title ILIKE '%임직원%복무%')
  AND status = 'active' AND superseded_by IS NULL;

-- ============ UPDATE 1: 임직원 징계기준 ============
UPDATE nexus_documents
SET meta = jsonb_set(
  COALESCE(meta, '{}'::jsonb),
  '{incident_nodes}',
  (COALESCE(meta->'incident_nodes', '[]'::jsonb) ||
   '["횡령", "배임", "금전사고", "절도", "비위행위"]'::jsonb)
)
WHERE title ILIKE '%임직원%징계%'
  AND status = 'active' AND superseded_by IS NULL;

-- ============ UPDATE 2: 윤리강령 / 행동기준 / 윤리경영 / 복무 ============
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

-- ============ UPDATE 3: universal SOPs — 횡령도 사건사고 보고 대상 ============
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

-- ============ 중복 incident_nodes 제거 (jsonb dedup) ============
UPDATE nexus_documents
SET meta = jsonb_set(
  meta,
  '{incident_nodes}',
  (SELECT to_jsonb(array_agg(DISTINCT value))
   FROM jsonb_array_elements_text(meta->'incident_nodes') value)
)
WHERE meta ? 'incident_nodes'
  AND jsonb_array_length(meta->'incident_nodes') > 0;

-- ============ 최종 검증 ============
SELECT title,
       jsonb_array_length(meta->'incident_nodes') AS node_count,
       meta->'incident_nodes' AS incident_nodes
FROM nexus_documents
WHERE meta->'incident_nodes' ? '횡령'
  AND status = 'active' AND superseded_by IS NULL
ORDER BY title;

COMMIT;

NOTIFY pgrst, 'reload schema';

-- ============ Rollback (실수 발견 시 별도 실행) ============
-- BEGIN;
-- UPDATE nexus_documents
-- SET meta = jsonb_set(
--   meta,
--   '{incident_nodes}',
--   (SELECT to_jsonb(array_agg(value))
--    FROM jsonb_array_elements_text(meta->'incident_nodes') value
--    WHERE value NOT IN ('횡령','배임','금전사고','절도','비위행위','윤리위반'))
-- )
-- WHERE meta->'incident_nodes' ?| array['횡령','배임','금전사고','절도','비위행위','윤리위반']
--   AND status = 'active' AND superseded_by IS NULL;
-- COMMIT;
