-- OOS 라우팅 안내: IT 지원 담당팀 'IT팀' → 'AX시스템팀' 명칭 변경.
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
      '· IT 지원 (VPN / 네트워크 / PC / 시스템 오류)  → IT팀',
      '· IT 지원 (VPN / 네트워크 / PC / 시스템 오류)  → AX시스템팀'
    )
WHERE key = 'oos_routing_text';

NOTIFY pgrst, 'reload schema';

COMMIT;
