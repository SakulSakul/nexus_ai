-- PR-Phase-18.5.2: OOS Fast Skip 라우팅 메시지 — hotline_config 단일 row 추가.
-- 스키마 변경 0건 (hotline_config 는 key/value text 테이블, hotline_config_public
-- view 가 신규 키도 자동 노출). 코드 fallback (_DEFAULT_OOS_MESSAGE) 와 동일 텍스트.
--
-- ON CONFLICT DO NOTHING (사쿨님 확정):
--   재실행 시 admin 이 운영 중 변경한 텍스트를 덮어쓰지 않음 (운영 보호).
--   기본값 강제 복원이 필요하면 admin 에서 직접 UPDATE 하거나 row 삭제 후 재실행.
--
-- Rollback 옵션:
--   1차 (권장): Streamlit secrets 의 ENABLE_OOS_ROUTING="false" → 즉시 우회.
--   2차: DELETE FROM hotline_config WHERE key='oos_routing_text';
--        → 코드 fallback (_DEFAULT_OOS_MESSAGE) 로 자동 회귀.

BEGIN;

INSERT INTO hotline_config (key, value, description)
VALUES (
  'oos_routing_text',
  E'요청하신 내용은 사규 챗봇의 범위를 벗어납니다. 담당 창구로 안내드립니다.\n\n'
    '· IT 지원 (VPN / 네트워크 / PC / 시스템 오류)  → AX시스템팀\n'
    '· 인사 행정 (휴가 / 인사평가 / 연봉 / 인사기록)  → 인사교육팀\n'
    '· 일반 행정 (회의실 / 카드 / 출장 / 비품)      → 총무팀\n'
    '· 타사 사규                                    → '
    '본 챗봇은 신세계디에프 사규 전용입니다.\n\n'
    '※ 긴급 사안(폭행 · 성희롱 · 중대재해 · 정보유출 · 강력범죄)은 즉시 핫라인 또는\n'
    '   SHRS 로 신고해 주세요 — 본 안내가 잘못 나왔다고 판단되면 채팅창에 그 사안의\n'
    '   ''신고/보고/피해'' 등 명시적 용어를 포함해 다시 질문해 주세요.',
  'OOS (사규 범위 밖) query 의 라우팅 안내 메시지 — Phase-18.5.2'
)
ON CONFLICT (key) DO NOTHING;

NOTIFY pgrst, 'reload schema';

COMMIT;
