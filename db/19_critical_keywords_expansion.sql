-- PR-Multi-Signal-Button-Branch-Refactor
-- Critical mode keyword 보강 — 검증 결과 누락 case 추가.
--
-- 누락 발견 (5/16 사쿨 검증):
-- - 괴롭힘 (Q6) — "직장 내 괴롭힘" 부분 매칭 보장 안 되어 standalone 추가
-- - 성희롱 (Q9) — 이미 존재 (ON CONFLICT)
-- - 횡령 (Q10) / 뇌물 (Q11) — 이미 존재 (ON CONFLICT)
-- - 개인정보 유출 (Q8) — 이미 존재 (ON CONFLICT)
-- - PC 분실 (Q12)
-- - 협박 (Q43) / 해킹 (Q44) — 이미 존재 (ON CONFLICT)
--
-- 주의: nexus_critical_kind enum 은 ('safety','harassment') 만 허용 →
-- db/07_quality_hardening.sql 의 convention (compliance/data_breach/security
-- 류는 harassment 로 통합 — 신고·조사 라우팅 동일) 그대로 적용.

insert into critical_keywords (kind, keyword) values
    -- Harassment (직장 내 괴롭힘 standalone + 차별)
    ('harassment','괴롭힘'),
    ('harassment','차별 대우'),
    -- Compliance (도용/절도 = harassment 컨벤션, 신고·조사 라우팅 동일)
    ('harassment','도용'),
    ('harassment','절도'),
    -- Data breach (PC 분실 / 자료 유출 — '데이터 유출' 별칭)
    ('harassment','PC 분실'),
    ('harassment','자료 유출'),
    ('harassment','회사 자료 유출'),
    -- Security
    ('harassment','테러'),
    -- Safety
    ('safety','자해')
on conflict (kind, keyword) do nothing;
