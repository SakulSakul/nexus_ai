"""카테고리 → 담당부서 매핑.

답변 푸터의 신뢰도 chip 에서 "정확한 사항은 OO 확인" 문구의 OO 를
카테고리에 맞춰 동적으로 결정한다. 신세계DF 사규 거버넌스 구조 기준
(필요 시 직접 조정).

순수 UI 매핑 — retrieval / 합성 흐름과 무관.
"""

from __future__ import annotations


# 카테고리 → 담당부서 매핑.
# 신세계DF 사규 거버넌스 구조 기준 (필요 시 사쿨이 직접 조정).
# 도메인 fallback default — owning_department 정보 없을 때만 사용.
# 사규 본문이 진실이므로 일반적 default 만 명시 (사쿨 운영 원칙).
NEXUS_CATEGORY_OWNER_DEPT_DEFAULT = {
    "CSR": "CSR팀",
    "윤리": "CSR팀",
    "공통": "CSR팀",
    "공정거래": "CSR팀",
    "환경": "CSR팀",
    "안전": "총무팀",       # 안전 사규 다수가 총무팀 (사규 본문 기준)
    "총무": "총무팀",
    "영업": "총무팀",
    "인사": "인사교육팀",    # 조직개편 반영 (구 인사팀) — fallback default
    "재무": "경리팀",       # 다수 = 경리팀
    "정보보안": "정보보안담당",
}

# 하위 호환 alias (기존 import 코드 보호)
NEXUS_CATEGORY_OWNER_DEPT = NEXUS_CATEGORY_OWNER_DEPT_DEFAULT

_FALLBACK = "CSR팀"  # 사규 관리 주체


def nexus_get_owner_dept(
    category: str | None,
    doc_owning_dept: str | None = None,
) -> str:
    """담당부서명 반환.

    1순위: 사규 본문의 owning_department (doc_owning_dept)
    2순위: 도메인 fallback default
    3순위: CSR팀 (사규 관리 주체)
    """
    if doc_owning_dept and doc_owning_dept.strip():
        return doc_owning_dept.strip()
    if category:
        return NEXUS_CATEGORY_OWNER_DEPT_DEFAULT.get(category.strip(), _FALLBACK)
    return _FALLBACK
