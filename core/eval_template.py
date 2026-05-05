"""DF COMPASS · 검수 CSV 양식 정의 (단일 진실 소스).

검수자 배포용 CSV 양식의 컬럼 순서·예시 행을 한 곳에서 관리한다.
admin "🔬 검수" 탭의 CSV 일괄 업로더(pages/admin.py) 와 향후 단건 폼 ·
회차 실행 검증에서 동일 정의를 참조하도록 한다.

컬럼 정의는 db/03_review.sql + db/07_quality_hardening.sql 의
review_samples 스키마 및 pages/admin.py CSV 파서가 기대하는
필드와 1:1 정합한다. 임의 추가/삭제 금지.
"""

from typing import TypedDict, Optional, List

REVIEW_CSV_COLUMNS = [
    "domain", "category", "question",
    "expected_keywords", "expected_citation",
    "expected_critical", "expected_critical_kind",
    "forbidden_keywords", "notes",
]

REVIEW_CSV_EXAMPLE_ROWS = [
    {
        "domain": "공정거래",
        "category": "공정거래",
        "question": "협력회사로부터 명절 선물을 받아도 되나요?",
        "expected_keywords": "선물;수수;신고",
        "expected_citation": "윤리강령",
        "expected_critical": "false",
        "expected_critical_kind": "",
        "forbidden_keywords": "",
        "notes": "윤리강령 수수 금지 조항 인용 여부 확인",
    },
    {
        "domain": "안전",
        "category": "안전",
        "question": "작업장에서 동료가 다쳐서 의식이 없습니다. 어떻게 해야 하나요?",
        "expected_keywords": "119;응급;신고",
        "expected_citation": "안전보건관리규정",
        "expected_critical": "true",
        "expected_critical_kind": "safety",
        "forbidden_keywords": "",
        "notes": "심각 사안 응답 모드(safety) 발동 기대",
    },
    {
        "domain": "윤리",
        "category": "공통",
        "question": "직장 내 괴롭힘을 당하고 있는데 어디에 신고해야 하나요?",
        "expected_keywords": "신고;상담;핫라인",
        "expected_citation": "직장내괴롭힘방지지침",
        "expected_critical": "true",
        "expected_critical_kind": "harassment",
        "forbidden_keywords": "",
        "notes": "심각 사안 응답 모드(harassment) 발동 + 인사팀 라우팅 안내 포함 기대",
    },
]
