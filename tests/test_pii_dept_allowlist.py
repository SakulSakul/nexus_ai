"""PII _RE_DEPT allowlist 골든 — 일반명사 오탐 통과 + 진짜 부서 PII 보호.
이 두 invariant 가 동시에 성립해야 한다:
  ① 일반명사(회의실 등)는 마스킹되지 않는다 (검색 오염 방지)
  ② 진짜 부서(비서실 등)는 계속 마스킹된다 (PII 누출 방지) ← 안전 핵심
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.pii_filter import mask_pii, ANON

# ① 마스킹되면 안 되는 일반명사 (allowlist)
GENERIC_NOUNS = [
    "회의실", "교육실", "자료실", "상황실", "대기실", "휴게실",
    "화장실", "사무실", "탕비실", "흡연실", "당직실",
    "방송국", "우체국", "출입국",
]
# ② 계속 마스킹돼야 하는 진짜 부서 (정탐 — 누출 금지)
REAL_DEPTS = [
    "비서실", "감사실", "기획실", "홍보실", "법무실", "전략기획실",
    "인사교육팀", "총무팀", "경영관리팀", "경리팀",
    "영업본부", "관리본부", "고객만족센터", "물류센터",
]

def test_generic_nouns_not_masked():
    """일반명사는 mask_pii 후에도 원형 보존 (오탐 0)."""
    failed = []
    for w in GENERIC_NOUNS:
        if mask_pii(w) != w:
            failed.append(w)
    assert not failed, f"오탐(마스킹되면 안 되는데 됨): {failed}"

def test_real_depts_still_masked():
    """진짜 부서는 여전히 마스킹 (PII 보호 — 가장 중요)."""
    leaked = []
    for w in REAL_DEPTS:
        if mask_pii(w) == w:  # 원형 그대로면 마스킹 안 된 것 = 누출
            leaked.append(w)
    assert not leaked, f"PII 누출(마스킹돼야 하는데 안 됨): {leaked}"

def test_realistic_query_not_corrupted():
    """실제 질의 맥락: '회의실 예약' 류가 오염되지 않는지."""
    cases = [
        "회의실 예약 어떻게 해요?",
        "교육실 대관 보안 규정",
        "자료실 출입 통제 절차",
    ]
    for q in cases:
        out = mask_pii(q)
        assert ANON not in out, f"일반명사 질의 오염: {q!r} -> {out!r}"

def test_dept_in_sentence_still_masked():
    """문장 속 진짜 부서도 마스킹 유지."""
    out = mask_pii("비서실에 문의하세요")
    assert ANON in out, f"문장 속 부서 누출: {out!r}"

if __name__ == "__main__":
    test_generic_nouns_not_masked()
    test_real_depts_still_masked()
    test_realistic_query_not_corrupted()
    test_dept_in_sentence_still_masked()
    print("PII allowlist 골든 4/4 PASS")
