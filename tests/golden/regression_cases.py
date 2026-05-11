"""Phase 2 baseline 회귀 테스트 케이스 (5 카테고리 + customer_injury)."""

REGRESSION_CASES: list = [
    # === customer_injury (Phase 1.5 baseline) ===
    {"category": "customer_injury", "query": "고객이 매장에서 넘어졌어"},
    {"category": "customer_injury", "query": "매장에서 고객이 넘어짐"},
    {"category": "customer_injury", "query": "손님이 미끄러져 다쳤어요"},
    {"category": "customer_injury", "query": "매장에서 손님이 다쳤음"},

    # === sexual_harassment ===
    {"category": "sexual_harassment", "query": "직원이 성희롱 당했어요"},
    {"category": "sexual_harassment", "query": "동료가 성희롱 신고했어"},

    # === workplace_harassment ===
    {"category": "workplace_harassment", "query": "팀장이 폭언해요"},
    {"category": "workplace_harassment", "query": "직장 내 괴롭힘 당했어요"},

    # === info_leak ===
    {"category": "info_leak", "query": "고객 개인정보 유출됐어요"},
    {"category": "info_leak", "query": "직원이 자료 외부로 유출했어"},

    # === worker_safety ===
    {"category": "worker_safety", "query": "직원이 작업 중 다쳤어요"},
    {"category": "worker_safety", "query": "사망사고 발생"},

    # === store_incident ===
    {"category": "store_incident", "query": "매장에서 화재 발생"},
    {"category": "store_incident", "query": "어린이가 실종됐어요"},

    # === embezzlement (Hotfix — 실 사용자 query 발견) ===
    {"category": "embezzlement", "query": "회사 돈을 훔치면 어떻게 됨?"},
    {"category": "embezzlement", "query": "직원이 회사 자금 횡령했어요"},
]
