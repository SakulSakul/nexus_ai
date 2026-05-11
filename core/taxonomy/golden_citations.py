"""Incident type 별 expected 사규 + 조항 mapping (golden truth)."""

from __future__ import annotations

from typing import Any


# Phase 0: customer_injury (인사사고 → 고객상해) 만 정의
# Phase 2 에서 다른 incident 카테고리 확장
INCIDENT_GOLDEN_CITATIONS: dict[str, dict[str, Any]] = {
    "customer_injury": {
        "description": "매장 내 고객 부상 (인사사고 → 고객상해)",
        "matching_incident_nodes": ["고객상해", "인사사고"],
        "required_docs": {
            "(공통) 일반 사건사고 보고지침": {
                "severity": "REQUIRED",
                "required_clauses": [
                    {"clause": "3.1조", "topic": "분류 체계 (13 대분류 / 57 중분류)", "severity": "HIGH"},
                    {"clause": "3.1조 인사사고/고객상해 정의", "topic": "매장 내 부상 (원인 불문)", "severity": "HIGH"},
                    {"clause": "4.1.1조", "topic": "경중 무관 보고 원칙", "severity": "MEDIUM"},
                    {"clause": "4.1.2조", "topic": "최초 인지자 즉시 보고", "severity": "HIGH"},
                    {"clause": "4.1.3조", "topic": "24시간 內 유선(구두) + SRMS", "severity": "HIGH"},
                    {"clause": "4.1.4조", "topic": "24시간 內 정식 서면 보고", "severity": "MEDIUM"},
                    {"clause": "4.2.1조", "topic": "최초 인지자 → 점장(점포)/해당팀장(본사) + CSR팀장 즉시", "severity": "HIGH"},
                    {"clause": "4.2.2조", "topic": "점장/팀장 → CSR·인사·총무·경영관리팀 병렬 + 담당임원 (24h SRMS)", "severity": "HIGH"},
                    {"clause": "4.2.3조", "topic": "담당임원 보고 후 24시간 內 대표이사 정식 서면", "severity": "MEDIUM"},
                ],
            },
            "(공통) 중대 사건사고 보고지침": {
                "severity": "REQUIRED",
                "required_clauses": [
                    {"clause": "3.1조 인사사고 중대 분류", "topic": "사망/중상 (고객·협력사원 사업장 內, 직원 모든 건)", "severity": "HIGH"},
                    {"clause": "3.1조 인사사고 중대 분류", "topic": "경상 동시 5인 이상", "severity": "HIGH"},
                    {"clause": "3.1조 인사사고 중대 분류", "topic": "사업장 內 성범죄 (직원·협력사원 연루)", "severity": "MEDIUM"},
                    {"clause": "3.1조 인사사고 중대 분류", "topic": "강도/유괴/폭행/인질극 등 강력 범죄", "severity": "MEDIUM"},
                    {"clause": "3.1조 인사사고 중대 분류", "topic": "법정 감염병 발생", "severity": "MEDIUM"},
                    {"clause": "4.2조 1차 보고", "topic": "사고 인지 즉시 모바일 사건사고 (유선/문자)", "severity": "HIGH"},
                    {"clause": "4.2조 2차 보고", "topic": "인지 후 2시간 內 서면 (이메일)", "severity": "HIGH"},
                    {"clause": "4.2조 SRMS 등록", "topic": "발생 후 12시간 內 (PC/모바일)", "severity": "HIGH"},
                ],
            },
        },
        "expected_sections": [
            "▼ 사건 분류 (대분류: 인사사고 / 중분류: 고객상해)",
            "▼ 일반 vs 중대 사건사고 판단 (5가지 기준)",
            "▼ 일반 사건사고 보고 절차 (4.1.x + 4.2.x)",
            "▼ 중대 사건사고 보고 절차 (1차 즉시 / 2차 2h / SRMS 12h)",
        ],
    },
}


def lookup_golden(incident_nodes: list | None) -> dict | None:
    """user_incident_nodes 로부터 매칭되는 golden entry 찾기.
    여러 entry 매칭 시 첫 번째 우선 (Phase 0 는 customer_injury 만).
    """
    if not incident_nodes:
        return None
    nodes_set = set(incident_nodes)
    for incident_type, golden in INCIDENT_GOLDEN_CITATIONS.items():
        matching = set(golden.get("matching_incident_nodes", []) or [])
        if nodes_set & matching:
            return {**golden, "incident_type": incident_type}
    return None


def list_supported_incident_types() -> list:
    """Phase 0 에서 검증 가능한 incident type list."""
    return list(INCIDENT_GOLDEN_CITATIONS.keys())
