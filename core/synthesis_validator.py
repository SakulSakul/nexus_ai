"""LLM 답변 사후 검증 + 구조화 사건사고 SOP 강제 주입 (PR #84).

Layer 3 of synthesis hardening. 청크 텍스트 keyword markers 매칭으로
extraction — hallucination zero. 청크에 없는 라인은 답변에 안 들어감.

검증 범위 (force_included_by_intent 청크 있을 때만):
- [참조: 검색 결과 없음] → 실제 doc titles 자동 교체
- [참조] 섹션 누락 시 force-included docs 자동 첨부
- 사규 기준 섹션 denial → 구조화 4단계 SOP 강제 교체
  (분류 / 일반·중대 판정 / 일반 절차 / 중대 절차)
- 본문 denial 표현 soft replacement

⚖️ 징계 기준 / 📂 사건사례 섹션은 절대 미수정 (정규식 lookahead 엄격).
진짜 검색 0건은 보정 안 함.
"""

from __future__ import annotations

import re
import sys
from typing import Optional

# PR-Fix-Domain-Synth: retriever 의 도메인 매핑 import (단방향 dependency,
# retriever 는 synthesis_validator import 안 함 — cycle 없음).
# STRUCTURED_INJECT 가 사건사고 SOP 4단계 구조를 ethics 도메인 질문에
# 무차별 주입하는 회귀 차단.
from core.retriever import INCIDENT_NODE_TO_DOMAIN


# ──────────────────────────────────────────────────────────
# 사건사고 카테고리 — 일반 사건사고 보고지침 3.1조 13개 대분류
# LLM 답변 구조화 시 user_incident_nodes 와 매핑용
# ──────────────────────────────────────────────────────────
_INCIDENT_CATEGORY_MAP: dict = {
    # incident_node → (대분류, 중분류 또는 None)
    "고객상해":   ("인사사고", "고객상해"),
    "직원상해":   ("인사사고", "직원상해"),
    "직원질병":   ("인사사고", "직원질병"),
    "고객질병":   ("인사사고", "고객질병/취식후병증"),
    "취식후병증": ("인사사고", "고객질병/취식후병증"),
    "인사관리":   ("인사사고", "인사관리"),
    "인사사고":   ("인사사고", None),
    "매장사고":   ("안전관리", "시설안전"),
    "시설안전":   ("안전관리", "시설안전"),
    "안전관리":   ("안전관리", None),
    "응급대응":   ("안전관리", None),
    "고객관리":   ("고객관리", None),
    "고객난동":   ("고객관리", "고객난동"),
    "고객분실":   ("고객관리", "고객분실"),
    "고객불만":   ("고객관리", "고객불만"),
    "회사정보":   ("정보보안", "회사정보"),
    "고객정보":   ("정보보안", "고객정보"),
    # === Hotfix 2026-05-12 PR #104: 횡령/배임/금전사고 카테고리 ===
    # nexus_query_rewriter 의 _NEXUS_GENERAL_INCIDENT_TAXONOMY['조직관리'] 와 정렬.
    "횡령":       ("조직관리", "횡령수수"),
    "배임":       ("조직관리", "횡령수수"),
    "금전사고":   ("조직관리", "횡령수수"),
    "절도":       ("조직관리", "직원절취"),
    "비위행위":   ("조직관리", None),
    "윤리위반":   ("근무기강", None),
    "뇌물":       ("조직관리", "횡령수수"),
}


# ──────────────────────────────────────────────────────────
# Forbidden patterns
# ──────────────────────────────────────────────────────────
_FORBIDDEN_NO_REF_PATTERNS: tuple = (
    r"\[참조\s*:\s*검색\s*결과\s*없음\s*\]",
    r"\[참조\s*:\s*관련\s*사규\s*미발견\s*\]",
    r"\[참조\s*:\s*관련\s*사규에서\s*확인되지\s*(?:않음|않습니다|않았습니다)\.?\s*\]",
    r"\[참조\s*:\s*해당\s*사규\s*없음\s*\]",
)

# 📋 사규 기준 섹션 boundary markers — 유니코드 변형 모두 cover.
# regex 의존 → string-based marker scan 으로 교체 (PR #87).
_SECTION_NEXT_BOUNDARIES: tuple = (
    "⚖️", "⚖",                       # 징계 기준 (VS16 유무 양쪽)
    "📂",                            # 사건사례
    "[참조", "[참 조",
    "권장 행동",
    "AI 안내",
)

# Denial keywords (substring 매칭, 유연 — 띄어쓰기/맞춤법 변형 cover).
_REGULATION_DENIAL_KEYWORDS: tuple = (
    "해당 유형 문서가 검색되지 않았습니다",
    "해당 유형 문서가 검색 되지 않았습니다",
    "관련 사규 내용을 확인할 수 없습니다",
    "관련 사규에서 확인되지 않습니다",
    "관련 사규에서 확인되지 않았습니다",
    "관련 사규에서 확인되지 않음",
    "관련 사규 내용을 확인하기 어렵습니다",
)

_BODY_DENIAL_PATTERNS: tuple = (
    "관련 사규에서 확인되지 않습니다",
    "관련 사규에서 확인되지 않았습니다",
    "관련 사규가 확인되지 않았습니다",
    "구체적인 대응 절차는 관련 사규에서 확인되지 않습니다",
    "구체적인 대응 절차는 관련 사규에서 확인되지 않았습니다",
    "해당 유형 문서가 검색되지 않았습니다",
    "확인되지 않습니다",
    "확인하기 어렵습니다",
)


# ──────────────────────────────────────────────────────────
# Domain check (PR-Fix-Domain-Synth)
# ──────────────────────────────────────────────────────────
def _has_incident_domain(user_incident_nodes: Optional[list]) -> bool:
    """user_incident_nodes 중 incident 도메인 노드가 하나라도 있으면 True.

    PR-Fix-Domain-Synth: STRUCTURED_INJECT (Repair 3) 의 발동 조건.
    universal_sop chunks 가 있어도 ethics 단독 도메인이면 사건사고 SOP
    4단계 강제 주입 안 함 → LLM 의 원래 답변 (CREDO/징계기준 인용 포함) 보존.
    """
    if not user_incident_nodes:
        return False
    for _node in user_incident_nodes:
        if INCIDENT_NODE_TO_DOMAIN.get(_node) == "incident":
            return True
    return False


# ──────────────────────────────────────────────────────────
# 청크 필터링
# ──────────────────────────────────────────────────────────
def _universal_sop_chunks(chunks: list) -> dict:
    """force-included universal SOP 청크를 doc_title 별 분리."""
    out: dict = {
        "(공통) 일반 사건사고 보고지침": [],
        "(공통) 중대 사건사고 보고지침": [],
    }
    for c in chunks or []:
        if not c.get("is_universal_sop"):
            continue
        title = c.get("doc_title") or ""
        if title in out:
            out[title].append(c)
    return out


def _force_included_titles(chunks: list) -> list:
    """force-included 모든 doc titles (입력 순 dedup)."""
    titles: list = []
    seen: set = set()
    for c in chunks or []:
        if not c.get("force_included_by_intent"):
            continue
        t = c.get("doc_title") or ""
        if t and t not in seen:
            titles.append(t)
            seen.add(t)
    return titles


# 외부 import 용 — chatbot.py 가 사용 (PR #83 호환).
def extract_force_included_titles(chunks: list) -> list:
    return _force_included_titles(chunks)


# ──────────────────────────────────────────────────────────
# 사규 기준 섹션 string-based marker scan (PR #87)
# ──────────────────────────────────────────────────────────
def _find_regulation_section_bounds(answer: str) -> Optional[tuple]:
    """📋 사규 기준 섹션의 (start_idx, end_idx) 반환.

    end_idx = 다음 boundary marker (⚖️/📂/[참조/권장 행동/AI 안내) 직전 또는 답변 끝.
    섹션 미발견 시 None.
    """
    start_idx = -1
    L = len(answer)
    for i in range(L):
        if answer[i] == "📋" and "사규 기준" in answer[i:i + 30]:
            start_idx = i
            break
    if start_idx == -1:
        return None
    search_start = start_idx + len("📋")
    end_idx = L
    for marker in _SECTION_NEXT_BOUNDARIES:
        idx = answer.find(marker, search_start)
        if idx != -1 and idx < end_idx:
            end_idx = idx
    return (start_idx, end_idx)


def _section_has_denial(section_text: str) -> bool:
    """섹션 본문에 denial keyword 포함 여부."""
    return any(kw in section_text for kw in _REGULATION_DENIAL_KEYWORDS)


# 4단계 완성도 검사 (PR #91) — 답변 사규 기준 섹션이 모든 sub-section 갖췄는지.
# LLM 이 "넘어짐" 등을 자율적으로 가벼운 사고로 해석해 일부 sub-section
# prune 하는 케이스 차단.
_REQUIRED_4SECTION_MARKERS: dict = {
    "classification": (
        "사건 분류",
        "고객상해", "직원상해",
        "인사사고",
    ),
    "severity_criteria": (
        "일반 vs 중대", "중대 사건사고로 분류",
        "사망", "중상", "5인 이상",
    ),
    "general_procedure": (
        "일반 사건사고 보고 절차", "24시간", "SRMS",
        "최초 인지자",
    ),
    "severe_procedure": (
        "중대 사건사고 보고 절차",
        "1차 보고", "2차 보고", "모바일 사건사고",
        "2시간", "12시간",
    ),
}

# Phase 1 (PR #94) — 일반 사건사고 보고 절차 섹션의 필수 조항 마커.
# 모두 본문에 등장해야 complete 로 판정. 하나라도 누락이면 STRUCTURED_INJECT 트리거.
# (현재 라이브 chat 흐름이 일부 조항을 자율 prune 하는 케이스 차단)
# PR-Fix-Section-Detection-Markers: 조항 번호 marker → 절차 본문 keyword.
# PR #133-#134 의 SystemPrompt 가 LLM 에게 조항 번호 인용 금지, PR #137
# 의 structured SOP 본문도 조항 번호 제거 → LLM 답변에 조항 번호 등장
# 안 함 → 기존 마커 (4.1.1 등) 매칭 0 → 매번 incomplete → 매번
# STRUCTURED_INJECT 발동 (PR #133-#137 와 conflict). 절차 본문 의미
# keyword 로 변경하여 LLM 답변 자연 등장 시 매칭 가능.
_GENERAL_PROCEDURE_REQUIRED_MARKERS: tuple = (
    r"경중",                                # 4.1.1 — 경중 무관 모두 보고
    r"즉시\s*보고|즉시\s*인지",              # 4.1.2 — 최초 인지자 즉시 보고
    r"24시간",                              # 4.1.3-4 — 24시간 이내
    r"유선|구두|SRMS",                     # 4.1.3 — 유선/SRMS 보고
    r"리스크관리부서|CSR팀",                # 4.2.1 — 리스크관리부서장(CSR팀장)
    r"본사\s*지원부서|담당임원",             # 4.2.2 — 본사 지원부서 + 담당임원
    r"대표이사",                            # 4.2.3 — 대표이사 정식 서면
)


def _is_section_incomplete(section_text: str) -> tuple:
    """사규 기준 섹션이 4 sub-section 모두 갖췄는지 검사.

    각 sub-section 의 keyword set 중 최소 1개라도 매칭되면 그 sub-section
    있음으로 판정. PR #94 (Phase 1): general_procedure 는 추가로 7개 필수
    조항 마커 (4.1.1~4.2.3) 모두 본문 등장 요구. Returns
    (is_incomplete, missing_sections).
    """
    missing: list = []
    for section_key, keywords in _REQUIRED_4SECTION_MARKERS.items():
        if not any(kw in section_text for kw in keywords):
            missing.append(section_key)
            continue
        # general_procedure 는 keyword 통과해도 절차 본문 markers 검사.
        # PR-Fix-Section-Detection-Threshold: 모든 markers 필수 → 절반
        # (4개) 이상 매칭으로 완화. PR #138 (markers 절차 본문 keyword 변경)
        # 후속 — '직장 내 괴롭힘' 같이 4/7 매칭 case 에서 매번 STRUCTURED_INJECT
        # 발동되는 회귀 fix. LLM 답변 variability 허용.
        if section_key == "general_procedure":
            matched_count = sum(
                1 for m in _GENERAL_PROCEDURE_REQUIRED_MARKERS
                if re.search(m, section_text)
            )
            total = len(_GENERAL_PROCEDURE_REQUIRED_MARKERS)
            min_required = total // 2 + 1  # 7//2+1 = 4 (절반 이상)
            if matched_count < min_required:
                missing_clauses = [
                    m for m in _GENERAL_PROCEDURE_REQUIRED_MARKERS
                    if not re.search(m, section_text)
                ]
                missing.append(
                    f"general_procedure_clauses(matched={matched_count}/{total}, missing={missing_clauses})"
                )
    # PR-Fix-Section-Detection-Full: 4 sub-section 의 절반 이상 매칭 시
    # OK 로 완화. PR #139 (general_procedure markers 절반 매칭) 의 자연
    # 연장 — 4 sub-section 자체 매칭도 같은 절반 정책 적용.
    #
    # 직장 내 괴롭힘 query: LLM 답변에 classification + general_procedure
    # 매칭, severity_criteria + severe_procedure 미매칭 (universal SOP 전용
    # 키워드라 도메인 specific query 답변에 자연 등장 어려움). 기존 strict
    # logic (len(missing) > 0) 매번 발동 → universal SOP 본문 강제 주입 →
    # 도메인 mismatch (사망/중상/5인/1차 보고 등 직장 내 괴롭힘 무관 정보).
    #
    # 변경: 2 sub-section 이상 매칭 (4//2=2) 시 OK. LLM 답변에 절차 본문
    # 일부 있으면 강제 주입 SKIP. 4 sub-section 모두 미매칭 (또는 3 미매칭)
    # 시는 여전히 발동 — 안전망 유지.
    MAX_ALLOWED_MISSING = len(_REQUIRED_4SECTION_MARKERS) // 2  # 4//2 = 2
    return (len(missing) > MAX_ALLOWED_MISSING, missing)


# ──────────────────────────────────────────────────────────
# Section 1 — 분류 추출
# ──────────────────────────────────────────────────────────
def _extract_classification(
    user_incident_nodes: Optional[list],
    general_chunks: list,
) -> Optional[str]:
    if not user_incident_nodes:
        return None

    # 1차: subcategory 있는 노드 우선 (specific match — 예: '고객상해' → 인사사고/고객상해).
    major, minor = None, None
    for node in user_incident_nodes:
        if node in _INCIDENT_CATEGORY_MAP:
            m, sub = _INCIDENT_CATEGORY_MAP[node]
            if sub:
                major = m
                minor = sub
                break

    # 2차: subcategory 없는 노드라도 매핑 있으면 major 만 사용.
    if not major:
        for node in user_incident_nodes:
            if node in _INCIDENT_CATEGORY_MAP:
                m, _sub = _INCIDENT_CATEGORY_MAP[node]
                major = m
                break

    if not major:
        return None

    lines = ["**🗂️ 사건 분류**", "", f"* 대분류: {major}"]
    if minor:
        definition = None
        for chunk in general_chunks:
            text = chunk.get("text") or ""
            m = re.search(
                rf"{re.escape(minor)}\s*[:：]\s*([^\n]+?)(?:\n|$)",
                text,
            )
            if m:
                definition = m.group(1).strip()
                break
        if definition:
            lines.append(f"* 중분류: {minor} ({definition})")
        else:
            lines.append(f"* 중분류: {minor}")
    lines.append("")
    lines.append("📎 ((공통) 일반 사건사고 보고지침)")
    return "\n".join(lines)


# ──────────────────────────────────────────────────────────
# Section 2 — 중대 판정 기준 추출
# ──────────────────────────────────────────────────────────
_SEVERITY_CRITERIA_PATTERNS: tuple = (
    (r"사망[,，]?\s*중상[^•\n]*?(?:고객|협력사원|직원)[^•\n]*",
     "사망 또는 중상 (고객/협력사원: 사업장 內 발생, 직원: 모든 건)"),
    (r"경상[^•\n]*?(?:동시\s*)?5인\s*이상[^•\n]*",
     "경상이라도 동시 5인 이상 상해 발생"),
    (r"성범죄[^•\n]*",
     "직원·협력사원 연루 사업장 內 성범죄"),
    (r"(?:강도|유괴|폭행|인질극)[^•\n]*강력\s*범죄[^•\n]*",
     "강도, 유괴, 폭행, 인질극 등 강력 범죄"),
    (r"법정\s*감염병[^•\n]*",
     "법정 감염병 발생"),
)


def _extract_severity_criteria(severe_chunks: list) -> Optional[str]:
    if not severe_chunks:
        return None
    matched: list = []
    for chunk in severe_chunks:
        text = chunk.get("text") or ""
        for pattern, label in _SEVERITY_CRITERIA_PATTERNS:
            if re.search(pattern, text) and label not in matched:
                matched.append(label)
    if not matched:
        return None
    lines = [
        "**⚖️ 일반 vs 중대 사건사고 판단**",
        "",
        "다음 중 하나라도 해당하면 중대 사건사고로 분류:",
    ]
    for c in matched:
        lines.append(f"* {c}")
    lines.append("")
    lines.append("위 조건 미해당 시 → 일반 사건사고로 처리")
    lines.append("")
    lines.append("📎 ((공통) 중대 사건사고 보고지침)")
    return "\n".join(lines)


# ──────────────────────────────────────────────────────────
# Section 3 — 일반 사건사고 절차 추출
# ──────────────────────────────────────────────────────────
_GENERAL_PROCEDURE_PATTERNS: tuple = (
    (r"4\.1\.1[^\n]*경중[^\n]*",
     "일반 사건사고는 경중 무관 모두 보고"),
    (r"4\.1\.2[^\n]*최초\s*인지자[^\n]*즉시\s*보고[^\n]*",
     "최초 인지자 즉시 보고"),
    (r"4\.1\.3[^\n]*24시간[^\n]*유선[^\n]*SRMS[^\n]*",
     "24시간 이내 유선(구두) + SRMS 모두 이용하여 보고"),
    (r"4\.1\.4[^\n]*24시간[^\n]*정식\s*서면[^\n]*",
     "24시간 이내 정식 서면 보고"),
    (r"4\.2\.1[^\n]*점장[^\n]*",
     "최초 인지자 → 리스크관리부서장(CSR팀장) + 점장(점포)/해당팀장(본사) 즉시 보고"),
    (r"4\.2\.2[^\n]*CSR팀[^\n]*",
     "점장/팀장 → 본사 지원부서 팀장(CSR팀·인사교육팀·총무팀·경영관리팀) 병렬 + 담당임원"),
    (r"4\.2\.3[^\n]*대표이사[^\n]*",
     "담당임원 보고 후 24시간 이내 대표이사까지 정식 서면"),
)


def _extract_general_procedure(general_chunks: list) -> Optional[str]:
    if not general_chunks:
        return None
    matched: list = []
    for chunk in general_chunks:
        text = chunk.get("text") or ""
        for pattern, label in _GENERAL_PROCEDURE_PATTERNS:
            if re.search(pattern, text) and label not in matched:
                matched.append(label)
    if not matched:
        return None
    lines = ["**📋 일반 사건사고 보고 절차**", ""]
    for m in matched:
        lines.append(f"* {m}")
    lines.append("")
    lines.append("📎 ((공통) 일반 사건사고 보고지침)")
    return "\n".join(lines)


# ──────────────────────────────────────────────────────────
# Section 4 — 중대 사건사고 절차 추출
# ──────────────────────────────────────────────────────────
_SEVERE_PROCEDURE_PATTERNS: tuple = (
    (r"1차\s*보고[^\n]*즉시[^\n]*",
     "1차 보고: 사고 인지 즉시, 모바일 사건사고 긴급보고 (유선/문자)"),
    (r"2차\s*보고[^\n]*2시간[^\n]*",
     "2차 보고: 인지 후 2시간 內, 서면(이메일)"),
    (r"SRMS\s*등록[^\n]*12시간[^\n]*",
     "SRMS 등록: 발생 후 12시간 內 (PC/모바일)"),
)


def _extract_severe_procedure(severe_chunks: list) -> Optional[str]:
    if not severe_chunks:
        return None
    matched: list = []
    for chunk in severe_chunks:
        text = chunk.get("text") or ""
        for pattern, label in _SEVERE_PROCEDURE_PATTERNS:
            if re.search(pattern, text) and label not in matched:
                matched.append(label)
    if not matched:
        return None
    lines = ["**🚨 중대 사건사고 보고 절차**", ""]
    for m in matched:
        lines.append(f"* {m}")
    lines.append("")
    lines.append("📎 ((공통) 중대 사건사고 보고지침)")
    return "\n".join(lines)


# ──────────────────────────────────────────────────────────
# 통합 — 4 sections 조합
# ──────────────────────────────────────────────────────────
def _build_structured_regulation_section(
    chunks: list,
    user_incident_nodes: Optional[list] = None,
) -> Optional[str]:
    """Universal SOP 청크에서 4단계 구조 답변 생성.
    하나라도 추출 가능하면 답변 반환, 전부 실패면 None.
    """
    sop_chunks = _universal_sop_chunks(chunks)
    general_chunks = sop_chunks["(공통) 일반 사건사고 보고지침"]
    severe_chunks = sop_chunks["(공통) 중대 사건사고 보고지침"]
    if not (general_chunks or severe_chunks):
        return None

    sections = ["📋 사규 기준 (사건사고 보고 절차)\n"]
    classification = _extract_classification(user_incident_nodes, general_chunks)
    if classification:
        sections.append(classification + "\n")
    severity = _extract_severity_criteria(severe_chunks)
    if severity:
        sections.append(severity + "\n")
    general_proc = _extract_general_procedure(general_chunks)
    if general_proc:
        sections.append(general_proc + "\n")
    severe_proc = _extract_severe_procedure(severe_chunks)
    if severe_proc:
        sections.append(severe_proc + "\n")

    if len(sections) <= 1:
        return None
    return "\n".join(sections)


# ──────────────────────────────────────────────────────────
# Main validator
# ──────────────────────────────────────────────────────────
def validate_and_repair_answer(
    answer: str,
    chunks: list,
    user_incident_nodes: Optional[list] = None,
) -> tuple:
    """LLM 답변 검증 + 자동 보정.

    Returns:
        (repaired_answer, applied_repairs_log)
    """
    if not answer:
        return answer, []

    repairs: list = []
    repaired = answer

    force_titles = _force_included_titles(chunks)
    sop_chunks_map = _universal_sop_chunks(chunks)
    has_universal_sop = any(sop_chunks_map.values())

    # 진입 로그 — 매 호출마다 출력 (silent return 진단용).
    print(
        f"[synthesis:validator:ENTRY] "
        f"answer_len={len(answer)} "
        f"chunks={len(chunks or [])} "
        f"force_titles={len(force_titles)} "
        f"universal_sop_chunks="
        f"{{{', '.join(f'{k!r}: {len(v)}' for k, v in sop_chunks_map.items())}}} "
        f"user_incident_nodes={list(user_incident_nodes or [])}",
        file=sys.stderr, flush=True,
    )

    # 진짜 검색 0건은 보정 안 함.
    if not force_titles and not chunks:
        print(
            "[synthesis:validator:SKIP] no chunks, no force titles",
            file=sys.stderr, flush=True,
        )
        return answer, []

    # Repair 1: FORBIDDEN [참조: 검색 결과 없음] → 실제 doc titles
    if force_titles:
        actual_ref = f"[참조: {', '.join(force_titles)}]"
        for pattern in _FORBIDDEN_NO_REF_PATTERNS:
            if re.search(pattern, repaired):
                repaired = re.sub(pattern, actual_ref, repaired)
                repairs.append("FORBIDDEN_NO_REF replaced")
                print(
                    "[synthesis:validator] FORBIDDEN_NO_REF repaired",
                    file=sys.stderr, flush=True,
                )

    # Repair 2: [참조] 섹션 자체 누락 시 자동 추가
    if force_titles and "[참조:" not in repaired:
        actual_ref = f"[참조: {', '.join(force_titles)}]"
        repaired = repaired.rstrip() + f"\n\n{actual_ref}"
        repairs.append("MISSING_REF auto-injected")
        print(
            "[synthesis:validator] MISSING_REF auto-injected",
            file=sys.stderr, flush=True,
        )

    # Repair 3 (PR #91, v3 — strict 4-section enforcement):
    #   universal SOP 청크 있고 사규 기준 섹션이 미완성이면 → 강제 구조화 주입.
    #   denial pattern 유무와 무관하게 4단계 절대 보장 (LLM 자율 prune 차단).
    #   ⚖️ / 📂 / 권장 행동 / [참조] 영역은 절대 미수정.
    # PR-Fix-Domain-Synth: ethics 단독 도메인은 STRUCTURED_INJECT SKIP — LLM 자유 답변 보존.
    if has_universal_sop and _has_incident_domain(user_incident_nodes):
        structured = _build_structured_regulation_section(
            chunks, user_incident_nodes
        )
        if not structured:
            print(
                "[synthesis:validator:R3_SKIP] structured_section 빌드 실패 "
                "(universal SOP 청크에서 4단계 추출 불가)",
                file=sys.stderr, flush=True,
            )
        else:
            bounds = _find_regulation_section_bounds(repaired)
            if not bounds:
                print(
                    "[synthesis:validator:R3_SKIP] 📋 사규 기준 섹션 미발견 in answer",
                    file=sys.stderr, flush=True,
                )
            else:
                start_idx, end_idx = bounds
                section_text = repaired[start_idx:end_idx]
                has_denial = _section_has_denial(section_text)
                is_incomplete, missing = _is_section_incomplete(section_text)
                should_replace = has_denial or is_incomplete
                if not should_replace:
                    print(
                        f"[synthesis:validator:R3_SKIP] 사규 기준 섹션 완성 "
                        f"(denial=False, 4단계 모두 충족). LLM 답변 보존.",
                        file=sys.stderr, flush=True,
                    )
                else:
                    reason_parts: list = []
                    if has_denial:
                        reason_parts.append("denial")
                    if is_incomplete:
                        reason_parts.append(f"incomplete(missing={missing})")
                    reason = "+".join(reason_parts)
                    before = repaired[:start_idx]
                    after = repaired[end_idx:].lstrip("\n")
                    repaired = before + structured + "\n\n" + after
                    repairs.append(
                        f"STRUCTURED_INJECT: reason={reason} "
                        f"section_len={end_idx - start_idx} → "
                        f"structured_len={len(structured)}"
                    )
                    print(
                        f"[synthesis:validator] STRUCTURED_INJECT "
                        f"reason={reason} — section={end_idx - start_idx}chars "
                        f"→ structured={len(structured)}chars",
                        file=sys.stderr, flush=True,
                    )

    # Repair 4 (PR #88): body denial soft replacement — ⚖️ marker 이전 영역에서만.
    # ⚖️ 징계 기준 / 📂 사건사례 의 정상 "해당 없음" 표시 보호.
    if has_universal_sop:
        weighted_pos = repaired.find("⚖️")
        if weighted_pos == -1:
            weighted_pos = repaired.find("⚖")
        if weighted_pos == -1:
            weighted_pos = len(repaired)
        intro_text = repaired[:weighted_pos]
        rest_text = repaired[weighted_pos:]
        for denial in _BODY_DENIAL_PATTERNS:
            if denial in intro_text:
                soft = "사건사고 보고지침에 따라 다음 절차로 처리해야 합니다"
                new_intro = intro_text.replace(denial, soft, 1)
                repaired = new_intro + rest_text
                repairs.append(
                    f"BODY_DENIAL softened (intro-scoped): '{denial[:30]}'"
                )
                print(
                    f"[synthesis:validator] body denial softened "
                    f"(scope=intro, before ⚖️ at pos={weighted_pos})",
                    file=sys.stderr, flush=True,
                )
                break

    # Repair 5 (PR-Fix-Citation-Grounding): 가짜 조문 번호 인용 검출 + 제거.
    # LLM 이 청크 본문의 항목 번호 (예: '14. 회사 공금 횡령') 또는 sub-section
    # 번호 (예: '3.1 신고/조사') 를 '제38조', '제3.1조' 등 가짜 조문번호로
    # 변환 hallucinate 하는 회귀 차단. 사규 doc 의 청크 article_no 와
    # cross-reference 후 매칭 안 되는 조문번호 → 인용 라벨에서 제거하고
    # doc_title 만 보존. 답변 본문 내용은 청크에서 정확 인용된 상태이므로 유지.
    #
    # 데이터 근거 (2026-05-13 진단 SQL):
    # - 임직원 징계기준 13 청크 article_no 전부 null → '제38조,39,40' hallucination
    # - 일반 사건사고 보고지침 4 청크 article_no 전부 null → '제3.1조,4.1.1조' hallucination
    # - 중대 사건사고 보고지침 1 청크 article_no='제8조' → 그것만 정상
    _doc_articles: dict = {}
    for _c in chunks or []:
        _title = (_c.get("doc_title") or "").strip()
        _art = _c.get("article_no")
        if not _title:
            continue
        _doc_articles.setdefault(_title, set())
        if _art:
            _doc_articles[_title].add(str(_art).strip())

    _CITATION_RE = re.compile(r'📎\s*\(\(([^📎\n]+)\)')
    _hallucinated_refs: list = []

    def _validate_citation(match):
        inner = match.group(1).strip()
        # '제20조' (제 prefix 있음) + '20조' (제 prefix 없음) 두 형식 모두 매칭.
        # LLM 답변 variability 대응. 끝 '조' 는 mandatory 라 일반 숫자 매칭 안 됨.
        article_matches = list(re.finditer(r'제?([\d\.]+)조[^,)\(]*', inner))
        if not article_matches:
            return match.group(0)  # 조문번호 없는 정상 인용
        first_art_start = article_matches[0].start()
        doc_title_candidate = inner[:first_art_start].rstrip().rstrip(",").strip()
        # doc_title 정확 또는 partial match
        matched_title = None
        if doc_title_candidate in _doc_articles:
            matched_title = doc_title_candidate
        else:
            for _dt in _doc_articles:
                if _dt and (_dt in doc_title_candidate or doc_title_candidate in _dt):
                    matched_title = _dt
                    break
        if not matched_title:
            return match.group(0)  # 알 수 없는 doc — 변경 없음
        valid_arts = _doc_articles.get(matched_title, set())
        cited_arts = [m.group(1) for m in article_matches]
        invalid_cited: list = []
        for _cited in cited_arts:
            _cited_norms = {
                _cited,
                f"제{_cited}조",
                _cited.lstrip("제").rstrip("조"),
            }
            _is_valid = False
            for _valid in valid_arts:
                _valid_norms = {
                    _valid,
                    f"제{_valid}조",
                    _valid.lstrip("제").rstrip("조"),
                }
                if _cited_norms & _valid_norms:
                    _is_valid = True
                    break
            if not _is_valid:
                invalid_cited.append(_cited)
        if not invalid_cited:
            return match.group(0)  # 모두 valid — 정상 인용
        _hallucinated_refs.append(
            f"{matched_title} 제{','.join(invalid_cited)}조"
        )
        return f"📎 ({matched_title})"

    _new_repaired = _CITATION_RE.sub(_validate_citation, repaired)
    if _new_repaired != repaired:
        repaired = _new_repaired
        repairs.append(
            f"CITATION_GROUNDING: {len(_hallucinated_refs)} hallucinated article refs removed"
        )
        print(
            f"[synthesis:validator] CITATION_GROUNDING — removed "
            f"{len(_hallucinated_refs)} hallucinated article refs: "
            f"{_hallucinated_refs[:3]}",
            file=sys.stderr, flush=True,
        )

    # 종료 로그 — repair 수 / regex miss 진단.
    if not repairs:
        print(
            "[synthesis:validator:EXIT] no repairs applied "
            "(answer already clean OR regex miss)",
            file=sys.stderr, flush=True,
        )
    else:
        print(
            f"[synthesis:validator:EXIT] {len(repairs)} repair(s): "
            f"{'; '.join(r[:60] for r in repairs[:3])}",
            file=sys.stderr, flush=True,
        )

    return repaired, repairs
