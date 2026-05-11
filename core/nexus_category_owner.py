"""카테고리 → 담당부서 매핑.

답변 푸터의 신뢰도 chip 에서 "정확한 사항은 OO 확인" 문구의 OO 를
카테고리에 맞춰 동적으로 결정한다. 신세계DF 사규 거버넌스 구조 기준
(필요 시 직접 조정).

순수 UI 매핑 — retrieval / 합성 흐름과 무관.
"""

from __future__ import annotations


# 카테고리 → 담당부서 매핑.
# 신세계DF 사규 거버넌스 구조 기준 (필요 시 사쿨이 직접 조정).
NEXUS_CATEGORY_OWNER_DEPT = {
    # 비즈니스 영역
    "CSR": "CSR팀",
    "윤리": "CSR팀",
    "공통": "CSR팀",
    "영업": "총무팀",          # 매장 운영·습득물 등 다수 문서가 총무팀 관할
    "총무": "총무팀",
    "인사": "인사팀",
    "재무": "재무팀",
    # 안전·보안·규제
    "안전": "CSR팀",           # 안전보건은 CSR 관할
    "정보보안": "정보보호 주관부서",
    "공정거래": "CSR팀",
    "환경": "CSR팀",
}

_FALLBACK = "관할 부서"


def nexus_get_owner_dept(category: str | None) -> str:
    """카테고리 문자열 → 담당부서 명. 미매핑·빈 입력 시 일반 문구."""
    if not category:
        return _FALLBACK
    return NEXUS_CATEGORY_OWNER_DEPT.get(category.strip(), _FALLBACK)
