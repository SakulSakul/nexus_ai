-- OOS 라우팅 안내: 일반 행정 항목 '회의실 / 카드 / 출장 / 비품' → '회의실 / 명함 / 비품' 변경
-- (arrow 정렬 공백 동반 조정).
-- 스키마 변경 0건 (hotline_config 의 oos_routing_text 단일 row 텍스트 UPDATE).
--
-- 배경: 20260530_phase18_5_2_oos_routing.sql 은 ON CONFLICT DO NOTHING 이라
--   이미 존재하는 live row 를 덮어쓰지 않는다. 따라서 기존 DB 의 안내 문구를
--   바꾸려면 이 UPDATE 마이그레이션이 필요하다. 코드 fallback
--   (_DEFAULT_OOS_MESSAGE, core/oos_router.py) 와 동일 텍스트로 정렬.

BEGIN;

UPDATE hotline_config
SET value = REPLACE(
      value,
      '· 일반 행정 (회의실 / 카드 / 출장 / 비품)      → 총무팀',
      '· 일반 행정 (회의실 / 명함 / 비품)            → 총무팀'
    )
WHERE key = 'oos_routing_text';

NOTIFY pgrst, 'reload schema';

COMMIT;
