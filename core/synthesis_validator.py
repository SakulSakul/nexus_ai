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

    lines = ["▼ 사건 분류", f"- 대분류: {major}"]
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
            lines.append(f"- 중분류: {minor} ({definition})")
        else:
            lines.append(f"- 중분류: {minor}")
    lines.append("출처: (공통) 일반 사건사고 보고지침 3.1조")
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
    lines = ["▼ 일반 vs 중대 사건사고 판단",
             "다음 중 하나라도 해당하면 중대 사건사고로 분류:"]
    for c in matched:
        lines.append(f"- {c}")
    lines.append("위 조건 미해당 시 → 일반 사건사고로 처리")
    lines.append("출처: (공통) 중대 사건사고 보고지침 3.1조")
    return "\n".join(lines)


# ──────────────────────────────────────────────────────────
# Section 3 — 일반 사건사고 절차 추출
# ──────────────────────────────────────────────────────────
_GENERAL_PROCEDURE_PATTERNS: tuple = (
    (r"4\.1\.2[^\n]*최초\s*인지자[^\n]*즉시\s*보고[^\n]*",
     "최초 인지자 즉시 보고 (4.1.2조)"),
    (r"4\.1\.3[^\n]*24시간[^\n]*유선[^\n]*SRMS[^\n]*",
     "24시간 이내 유선(구두) + SRMS 모두 이용하여 보고 (4.1.3조)"),
    (r"4\.1\.4[^\n]*24시간[^\n]*정식\s*서면[^\n]*",
     "24시간 이내 정식 서면 보고 (4.1.4조)"),
    (r"4\.2\.1[^\n]*점장[^\n]*",
     "최초 인지자 → 점장(점포) / 해당팀장(본사) 즉시 보고 (4.2.1조)"),
    (r"4\.2\.2[^\n]*CSR팀[^\n]*",
     "점장/팀장 → 본사 지원부서 팀장(CSR팀·인사팀·총무팀·경영관리팀) 병렬 + 담당임원 (4.2.2조)"),
    (r"4\.2\.3[^\n]*대표이사[^\n]*",
     "담당임원 보고 후 24시간 이내 대표이사까지 정식 서면 (4.2.3조)"),
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
    lines = ["▼ 일반 사건사고 보고 절차"]
    for m in matched:
        lines.append(f"- {m}")
    lines.append("출처: (공통) 일반 사건사고 보고지침")
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
    lines = ["▼ 중대 사건사고 보고 절차"]
    for m in matched:
        lines.append(f"- {m}")
    lines.append("출처: (공통) 중대 사건사고 보고지침 4.2조")
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

    # Repair 3 (PR #87, string-based): 사규 기준 섹션 denial → 구조화 SOP 교체.
    # regex 대신 marker scan — 유니코드 변형(⚖️ VS16) / line ending / NBSP 등에 robust.
    # ⚖️ / 📂 / [참조 절대 미수정 (boundary marker 직전까지만 교체).
    if has_universal_sop:
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
                if not _section_has_denial(section_text):
                    print(
                        f"[synthesis:validator:R3_SKIP] 사규 기준 섹션에 denial 없음 "
                        f"(content_len={len(section_text)}). LLM 이 이미 좋은 답변 생성.",
                        file=sys.stderr, flush=True,
                    )
                else:
                    before = repaired[:start_idx]
                    after = repaired[end_idx:].lstrip("\n")
                    repaired = before + structured + "\n\n" + after
                    repairs.append(
                        f"DENIAL_SECTION_REPLACED: "
                        f"section_len={end_idx - start_idx} → "
                        f"structured_len={len(structured)}"
                    )
                    print(
                        f"[synthesis:validator] DENIAL_SECTION_REPLACED "
                        f"(string-based) — section={end_idx - start_idx}chars "
                        f"→ structured={len(structured)}chars",
                        file=sys.stderr, flush=True,
                    )

    # Repair 4: 본문 denial 표현 → soft replacement (한 번만)
    if has_universal_sop:
        for denial in _BODY_DENIAL_PATTERNS:
            if denial in repaired:
                soft = "사건사고 보고지침에 따라 다음 절차로 처리해야 합니다"
                repaired = repaired.replace(denial, soft, 1)
                repairs.append(f"BODY_DENIAL softened: '{denial[:30]}'")
                print(
                    "[synthesis:validator] body denial softened",
                    file=sys.stderr, flush=True,
                )
                break

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
