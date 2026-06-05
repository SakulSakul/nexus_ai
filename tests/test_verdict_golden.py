"""DF COMPASS verdict-extractor 골든 회귀 가드 (키리스·결정적·LLM 불필요).

#336 회귀 — '직장 내 괴롭힘 신고' 질의에 징계 점수표 '…수수 미신고 40' 이 평결카드
인용으로 나갔던 사건 — 이 그린 CI(AST+Import)를 통과해 버린 것을 재발 방지한다.
AST·Import 는 행동맹점이라 못 잡는 영역을 순수함수 불변식으로 핀 고정한다.

핀 대상(#337 수정 메커니즘):
  (A) _term_in     : 부정접두(미/비/불) 뒤 형태 매칭 거부 — '신고'≠'미신고'.
  (B) _pick_quote_global : 주지침(dom_doc) 가산 + badge 정합 게이트 —
      dom_doc 이 잘못 잡혀도 badge 0겹침 문장은 인용 억제(None).
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.synthesis.verdict_extractor import _term_in, _pick_quote_global

_DOM = "(인사) 직장 내 괴롭힘 예방·대응지침"
_CH = [
    {"doc_title": _DOM, "text": "직장 내 괴롭힘을 알게 된 사람은 지체 없이 신고하여야 한다."},
    {"doc_title": "임직원 징계기준", "text": "금품·편의·접대·향응 수수 미신고 시 40점을 부과한다."},
]
_KW = {"괴롭힘", "신고", "직장"}
_BADGE = {"신고"}


def test_term_in_negation():
    """부정접두 뒤 형태는 거부 — '신고'가 '미신고'에 오매칭되지 않아야."""
    assert _term_in("신고", "신고하여야 한다") is True
    assert _term_in("신고", "미신고 시 과태료를 부과한다") is False
    assert _term_in("공정", "공정거래 원칙을 준수한다") is True
    assert _term_in("공정", "불공정거래 행위에 해당한다") is False
    assert _term_in("신고", "지체없이 신고하고 미신고는 처벌한다") is True


def test_harassment_quote_correct():
    """괴롭힘 질의 → 괴롭힘 지침 문장이 선택되고 '미신고 40' 은 배제."""
    q, idx = _pick_quote_global(_CH, _KW, _BADGE, _DOM)
    assert idx == 0, f"괴롭힘 지침 문장이어야 함: idx={idx}"
    assert "미신고" not in (q or ""), f"징계 점수표 미신고 라인 인용 금지: {q!r}"
    assert "신고하여야" in q


def test_wrong_domdoc_still_suppresses_bad_quote():
    """방어심층: dom_doc 이 '잘못' 징계기준으로 잡혀도(=#336 dom 오선택) badge 게이트가
    '미신고 40' 인용을 억제해야 한다(negation 으로 badge 0겹침 → None)."""
    q, _ = _pick_quote_global(_CH, _KW, _BADGE, "임직원 징계기준")
    assert "미신고" not in (q or ""), f"방어심층 실패 — 미신고 라인 인용됨: {q!r}"


def test_dom_doc_subject_over_penalty():
    """#336-2: 주제 규정 + 징계기준(결과) 둘 다 인용 + rerank#1 노이즈(미인용)일 때
    평결 헤드라인 dom 은 결과문서가 아니라 주제 규정이어야 한다."""
    from core.synthesis.verdict_extractor import _select_dom_doc
    noise = "(공정거래) 매장 위치이동 지침"
    subj = "(공정거래) 협력회사 판촉사원 파견 지침"
    pen = "(공통) 임직원 징계기준"
    chunks = [{"doc_title": noise}, {"doc_title": subj}, {"doc_title": pen, "doc_kind": "penalty"}]
    assert _select_dom_doc(chunks, f"{subj} 위배. 위반 시 {pen}. {pen} 적용.") == subj


def test_dom_doc_keeps_rerank1_when_cited():
    """무회귀: rerank#1 이 본문 인용되면 유지(괴롭힘 케이스)."""
    from core.synthesis.verdict_extractor import _select_dom_doc
    har = "(인사) 직장 내 괴롭힘 예방·대응지침"
    pen = "(공통) 임직원 징계기준"
    chunks = [{"doc_title": har}, {"doc_title": pen, "doc_kind": "penalty"}]
    assert _select_dom_doc(chunks, f"{har} 위반 시 {pen}") == har


def test_dom_doc_keeps_penalty_when_only_penalty_cited():
    """과교정 방지: 인용된 게 penalty 뿐(진짜 징계 질의)이면 penalty 유지."""
    from core.synthesis.verdict_extractor import _select_dom_doc
    noise = "(공정거래) 매장 위치이동 지침"
    pen = "(공통) 임직원 징계기준"
    chunks = [{"doc_title": noise}, {"doc_title": pen, "doc_kind": "penalty"}]
    assert _select_dom_doc(chunks, f"위반 시 {pen} 적용. {pen}.") == pen


if __name__ == "__main__":
    fails = []
    for _n, _f in sorted(globals().items()):
        if _n.startswith("test_") and callable(_f):
            try:
                _f(); print(f"[GOLDEN OK] {_n}")
            except AssertionError as _e:
                fails.append(_n); print(f"[GOLDEN FAIL] {_n}: {_e}")
    if fails:
        print(f"\n[X] {len(fails)} 골든 실패 — #336류 회귀 의심"); sys.exit(1)
    print("\n[OK] verdict 골든 전건 통과")
