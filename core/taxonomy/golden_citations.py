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

    # === Phase 2.1: 성희롱 ===
    "sexual_harassment": {
        "description": "직장 내 성희롱 (성추행, 성폭력 포함)",
        "matching_incident_nodes": ["성희롱"],
        "required_docs": {
            "(인사) 성희롱 예방 지침": {
                "severity": "REQUIRED",
                "required_clauses": [
                    {"clause": "성희롱 정의", "topic": "성희롱의 정의 및 유형", "severity": "HIGH"},
                    {"clause": "신고 절차", "topic": "피해자 신고 방법 및 접수 부서", "severity": "HIGH"},
                    {"clause": "조사 절차", "topic": "신고 접수 후 조사 진행", "severity": "HIGH"},
                    {"clause": "피해자 보호", "topic": "피해자 비밀 유지 및 보호 조치", "severity": "HIGH"},
                    {"clause": "2차 가해 금지", "topic": "신고자 보호 및 보복 금지", "severity": "MEDIUM"},
                ],
            },
            "(공통) 임직원 징계기준": {
                "severity": "REQUIRED",
                "required_clauses": [
                    {"clause": "성희롱 징계 등급", "topic": "성희롱 행위자 징계 수위 (경고/감봉/정직/해임 등)", "severity": "HIGH"},
                ],
            },
            "(공통) 중대 사건사고 보고지침": {
                "severity": "REQUIRED",
                "required_clauses": [
                    {"clause": "3.1조 인사사고 중대 분류", "topic": "사업장 內 성범죄 = 중대 사건사고", "severity": "HIGH"},
                    {"clause": "4.2조 보고방법", "topic": "1차 즉시 모바일 / 2차 2h 內 서면 / SRMS 12h 內", "severity": "HIGH"},
                ],
            },
            "(공통) 일반 사건사고 보고지침": {
                "severity": "REQUIRED",
                "required_clauses": [
                    {"clause": "4.2.1조", "topic": "CSR팀장 + 점장/팀장 즉시 보고", "severity": "MEDIUM"},
                ],
            },
        },
        "expected_sections": [
            "▼ 성희롱 정의 및 유형",
            "▼ 신고 절차 (피해자 보호 포함)",
            "▼ 조사 절차",
            "▼ 보고 절차 (중대 사건사고)",
            "▼ 징계 기준",
        ],
    },

    # === Phase 2.2: 직장 내 괴롭힘 ===
    "workplace_harassment": {
        "description": "직장 내 괴롭힘 (폭언, 갑질, 따돌림 포함)",
        "matching_incident_nodes": ["괴롭힘"],
        "required_docs": {
            "(인사) 직장 내 괴롭힘 예방·대응지침": {
                "severity": "REQUIRED",
                "required_clauses": [
                    {"clause": "괴롭힘 정의", "topic": "직장 내 괴롭힘의 정의 및 유형", "severity": "HIGH"},
                    {"clause": "신고 절차", "topic": "피해자 신고 방법 및 접수 부서", "severity": "HIGH"},
                    {"clause": "조사 절차", "topic": "신고 접수 후 조사 진행", "severity": "HIGH"},
                    {"clause": "피해자 보호", "topic": "피해자 보호 조치 및 비밀 유지", "severity": "HIGH"},
                ],
            },
            "(인사) 건전한 조직문화 조성을 위한 자율준수 지침": {
                "severity": "OPTIONAL",
                "required_clauses": [
                    {"clause": "조직문화 원칙", "topic": "괴롭힘 예방을 위한 조직문화 원칙", "severity": "LOW"},
                ],
            },
            "(공통) 임직원 징계기준": {
                "severity": "REQUIRED",
                "required_clauses": [
                    {"clause": "괴롭힘 징계 등급", "topic": "괴롭힘 행위자 징계 수위", "severity": "HIGH"},
                ],
            },
            "(공통) 일반 사건사고 보고지침": {
                "severity": "REQUIRED",
                "required_clauses": [
                    {"clause": "4.1.2조", "topic": "최초 인지자 즉시 보고", "severity": "MEDIUM"},
                    {"clause": "4.2.1조", "topic": "CSR팀장 + 점장/팀장 즉시 보고", "severity": "MEDIUM"},
                ],
            },
        },
        "expected_sections": [
            "▼ 괴롭힘 정의 및 유형",
            "▼ 신고 절차",
            "▼ 조사 절차 (피해자 보호 포함)",
            "▼ 보고 절차 (일반 사건사고)",
            "▼ 징계 기준",
        ],
    },

    # === Phase 2.3: 정보유출 ===
    "info_leak": {
        "description": "개인정보/기밀정보 유출",
        "matching_incident_nodes": ["정보유출"],
        "required_docs": {
            "(정보보안) 정보보호 정책서": {
                "severity": "REQUIRED",
                "required_clauses": [
                    {"clause": "정보 분류", "topic": "정보 등급 및 보호 수준", "severity": "HIGH"},
                    {"clause": "유출 사고 대응", "topic": "유출 발생 시 대응 절차", "severity": "HIGH"},
                ],
            },
            "(정보보안) 정보보호 업무지침": {
                "severity": "REQUIRED",
                "required_clauses": [
                    {"clause": "유출 사고 보고", "topic": "유출 사고 발생 시 보고 절차", "severity": "HIGH"},
                    {"clause": "신고 부서", "topic": "보안담당부서 (정보보호 담당)", "severity": "HIGH"},
                ],
            },
            "(정보보안) 개인정보보호 지침": {
                "severity": "REQUIRED",
                "required_clauses": [
                    {"clause": "개인정보 침해 대응", "topic": "개인정보 유출 시 정보주체 통지 의무", "severity": "HIGH"},
                    {"clause": "관계기관 신고", "topic": "개인정보보호위원회/KISA 신고 의무", "severity": "HIGH"},
                ],
            },
            "(공통) 임직원 징계기준": {
                "severity": "REQUIRED",
                "required_clauses": [
                    {"clause": "정보유출 징계", "topic": "정보유출 행위자 징계 수위", "severity": "HIGH"},
                ],
            },
            "(공통) 일반 사건사고 보고지침": {
                "severity": "REQUIRED",
                "required_clauses": [
                    {"clause": "4.1.2조", "topic": "최초 인지자 즉시 보고", "severity": "MEDIUM"},
                    {"clause": "4.2.1조", "topic": "CSR팀장 + 점장/팀장 즉시 보고", "severity": "MEDIUM"},
                ],
            },
        },
        "expected_sections": [
            "▼ 사건 분류 (정보유출 / 개인정보 vs 기밀)",
            "▼ 사내 보고 절차 (보안담당부서)",
            "▼ 정보주체 통지 및 관계기관 신고 (개인정보 시)",
            "▼ 일반 사건사고 보고 절차",
            "▼ 징계 기준",
        ],
    },

    # === Phase 2.4: 근로자안전 (직원 부상/사망) ===
    "worker_safety": {
        "description": "근로자 안전사고 (직원 부상, 산업재해, 중대재해)",
        "matching_incident_nodes": ["근로자안전"],
        "required_docs": {
            "(안전) 안전보건관리규정": {
                "severity": "REQUIRED",
                "required_clauses": [
                    {"clause": "안전보건 관리 체계", "topic": "안전보건 책임자/관리감독자 체계", "severity": "HIGH"},
                    {"clause": "사고 대응", "topic": "사고 발생 시 대응 및 보고 절차", "severity": "HIGH"},
                ],
            },
            "(안전) 중대재해 대응 지침": {
                "severity": "REQUIRED",
                "required_clauses": [
                    {"clause": "중대재해 정의", "topic": "중대재해처벌법상 중대재해 정의 (사망 1인 / 6개월 이상 부상 2인 등)", "severity": "HIGH"},
                    {"clause": "긴급 대응", "topic": "중대재해 발생 시 즉시 대응 절차", "severity": "HIGH"},
                    {"clause": "관계기관 신고", "topic": "고용노동부/경찰 신고 의무", "severity": "HIGH"},
                ],
            },
            "(공통) 중대 사건사고 보고지침": {
                "severity": "REQUIRED",
                "required_clauses": [
                    {"clause": "3.1조 인사사고 중대 분류", "topic": "사망/중상 직원 = 중대 사건사고", "severity": "HIGH"},
                    {"clause": "4.2조 보고방법", "topic": "1차 즉시 모바일 / 2차 2h 內 서면 / SRMS 12h 內", "severity": "HIGH"},
                ],
            },
            "(공통) 일반 사건사고 보고지침": {
                "severity": "REQUIRED",
                "required_clauses": [
                    {"clause": "3.1조", "topic": "사건사고 분류 (인사사고/직원상해)", "severity": "HIGH"},
                    {"clause": "4.1.1조", "topic": "경중 무관 모두 보고", "severity": "MEDIUM"},
                    {"clause": "4.2.1조", "topic": "CSR팀장 + 점장/팀장 즉시 보고", "severity": "MEDIUM"},
                ],
            },
        },
        "expected_sections": [
            "▼ 사건 분류 (인사사고 / 직원상해)",
            "▼ 중대재해 판정 (중대재해처벌법 기준)",
            "▼ 안전보건 대응 (안전보건관리규정)",
            "▼ 보고 절차 (일반/중대 사건사고)",
            "▼ 관계기관 신고 (중대재해 시)",
        ],
    },

    # === Phase 2.5: 매장사고 비고객 (화재/정전/실종 등) ===
    "store_incident": {
        "description": "매장 비고객 사고 (화재, 정전, 실종아동, 시설사고)",
        "matching_incident_nodes": ["매장사고"],
        "required_docs": {
            "(안전) 매장 안전보건관리 지침": {
                "severity": "REQUIRED",
                "required_clauses": [
                    {"clause": "매장 안전 관리", "topic": "매장 안전보건 관리 책임", "severity": "HIGH"},
                    {"clause": "사고 대응", "topic": "매장 내 사고 대응 절차", "severity": "HIGH"},
                ],
            },
            "(안전) 비상시대비대응 지침": {
                "severity": "REQUIRED",
                "required_clauses": [
                    {"clause": "비상 상황 정의", "topic": "비상 상황 유형 (화재/정전/지진 등)", "severity": "HIGH"},
                    {"clause": "비상 대응 절차", "topic": "비상 상황 발생 시 대응 절차", "severity": "HIGH"},
                ],
            },
            "(영업) AEO 출입통제 및 시설관리 절차서": {
                "severity": "REQUIRED",
                "required_clauses": [
                    {"clause": "시설 관리", "topic": "매장 시설 관리 절차", "severity": "MEDIUM"},
                    {"clause": "출입 통제", "topic": "출입 통제 및 보안", "severity": "MEDIUM"},
                ],
            },
            "(공통) 일반 사건사고 보고지침": {
                "severity": "REQUIRED",
                "required_clauses": [
                    {"clause": "3.1조", "topic": "사건사고 분류", "severity": "HIGH"},
                    {"clause": "4.1.2조", "topic": "최초 인지자 즉시 보고", "severity": "HIGH"},
                    {"clause": "4.2.1조", "topic": "CSR팀장 + 점장/팀장 즉시 보고", "severity": "HIGH"},
                ],
            },
            "(공통) 중대 사건사고 보고지침": {
                "severity": "OPTIONAL",
                "required_clauses": [
                    {"clause": "중대 사건사고 판정", "topic": "사안에 따라 중대 사건사고 가능 (대규모 화재 등)", "severity": "MEDIUM"},
                ],
            },
        },
        "expected_sections": [
            "▼ 사건 분류 (매장사고 / 비상 상황)",
            "▼ 즉각 대응 (비상시대비대응 지침)",
            "▼ 매장 안전 조치 (매장 안전보건관리 지침)",
            "▼ 보고 절차 (일반 사건사고)",
            "▼ (해당 시) 중대 사건사고 판정",
        ],
    },

    # === Hotfix: 횡령/배임/금전사고 (실 사용자 query 발견) ===
    "embezzlement": {
        "description": "횡령·배임·금전사고·절도 (회사 자금/자산 비위행위)",
        "matching_incident_nodes": ["횡령", "배임", "금전사고", "절도", "비위행위"],
        "required_docs": {
            "(공통) 임직원 징계기준": {
                "severity": "REQUIRED",
                "required_clauses": [
                    {"clause": "횡령/절도 행위 정의", "topic": "회사 자금/자산 비위행위 정의", "severity": "HIGH"},
                    {"clause": "징계 수위", "topic": "횡령 금액별 징계 (감봉/정직/해임)", "severity": "HIGH"},
                    {"clause": "형사고발 가능성", "topic": "형사 처벌 동시 진행 여부", "severity": "MEDIUM"},
                    {"clause": "인사위원회 회부", "topic": "징계 절차 (인사위원회 심의)", "severity": "MEDIUM"},
                ],
            },
            "(공통) 일반 사건사고 보고지침": {
                "severity": "REQUIRED",
                "required_clauses": [
                    {"clause": "3.1조 인사사고/비위", "topic": "비위행위 사건사고 분류", "severity": "HIGH"},
                    {"clause": "4.1.2조", "topic": "최초 인지자 즉시 보고", "severity": "MEDIUM"},
                    {"clause": "4.2.1조", "topic": "CSR팀장 + 점장/팀장 즉시 보고", "severity": "MEDIUM"},
                ],
            },
            "(공통) 중대 사건사고 보고지침": {
                "severity": "OPTIONAL",
                "required_clauses": [
                    {"clause": "중대 판정", "topic": "고액 횡령 등 중대 사건사고 가능", "severity": "MEDIUM"},
                ],
            },
        },
        "expected_sections": [
            "▼ 사건 분류 (횡령/배임/금전사고)",
            "▼ 징계 수위 (감봉/정직/해임)",
            "▼ 형사고발 가능성",
            "▼ 인사위원회 회부 절차",
            "▼ 보고 절차 (일반 사건사고)",
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
