-- PR-DB-Based-Validation-Queries
-- 검증 자동화 query 동적 관리 (PR #159 의 hardcoded 8 query 대체).

CREATE TABLE IF NOT EXISTS nexus_validation_queries (
    id BIGSERIAL PRIMARY KEY,
    query_text TEXT NOT NULL,
    category TEXT,
    expected_button TEXT,    -- 'report' | 'hr_inquiry' | 'hidden' | NULL
    note TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- PR #159 의 hardcoded 8 query seed
INSERT INTO nexus_validation_queries (query_text, category, expected_button, note) VALUES
    ('거래처에서 명절 선물을 받았어요',                       'CSR',          'report',     'PR #159 seed'),
    ('환경 사고 발생 시 어떻게 해야 하나요?',                  '환경',         'hidden',     'PR #159 seed'),
    ('경쟁사 직원과 가격 정보 공유해도 되나요?',                '공정거래',     'report',     'PR #159 seed'),
    ('회사 인장 도용한 사례를 발견했어요',                     '총무',         'report',     'PR #159 seed'),
    ('해외 출장 비용 정산 방법',                              '재무',         'hidden',     'PR #159 seed'),
    ('직장 내 괴롭힘 신고하려고 하는데 가해자가 동기예요',        'Critical',     'report',     'PR #159 seed'),
    ('휴가 미사용 수당 받을 수 있나요?',                       '인사 graceful', 'hr_inquiry', 'PR #159 seed'),
    ('개인정보 유출 사고가 발생했어요',                        '정보보안',     'report',     'PR #159 seed')
ON CONFLICT DO NOTHING;
