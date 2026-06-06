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


def test_dom_doc_sop_not_hijack_when_subject_cited():
    """#336-3: universal-SOP(사건사고 보고지침)도 주제 규정이 인용되면 평결 헤드라인을
    가로채면 안 된다(penalty 와 동일 클래스 — 강제 주입 보일러플레이트)."""
    from core.synthesis.verdict_extractor import _select_dom_doc
    noise = "(공정거래) 매장 위치이동 지침"
    subj = "(공정거래) 협력회사 판촉사원 파견 지침"
    sop = "(공통) 중대 사건사고 보고지침"
    chunks = [{"doc_title": noise}, {"doc_title": subj}, {"doc_title": sop, "is_universal_sop": True}]
    assert _select_dom_doc(chunks, f"{subj} 위배. {sop} 보고. {sop}.") == subj


def test_dom_doc_keeps_sop_when_only_sop_cited():
    """과교정 방지: 보고/신고가 주제라 SOP만 인용되면 SOP 유지(보고질의 회귀 차단)."""
    from core.synthesis.verdict_extractor import _select_dom_doc
    noise = "(공정거래) 매장 위치이동 지침"
    sop = "(공통) 중대 사건사고 보고지침"
    chunks = [{"doc_title": noise}, {"doc_title": sop, "is_universal_sop": True}]
    assert _select_dom_doc(chunks, f"{sop} 절차. {sop}.") == sop


def test_displayed_confidence_graceful_high_to_medium():
    """#336-4: graceful 답변(직접 매칭 미발견)은 표시 신뢰도 '높음'으로 안 됨 → medium 강등."""
    from ui.render import _displayed_confidence
    body = "[💡 안내] 본 query 에 직접 매칭되는 사규가 검색되지 않았습니다.\n인사 행정 사항은 인사교육팀에 문의."
    assert _displayed_confidence("high", body) == "medium"


def test_displayed_confidence_normal_high_unchanged():
    """무회귀: graceful 마커 없는 정상 high 답변은 그대로 high 유지."""
    from ui.render import _displayed_confidence
    body = "직장 내 괴롭힘은 지체없이 신고하여야 한다."
    assert _displayed_confidence("high", body) == "high"


def test_displayed_confidence_low_unchanged():
    """무회귀: low/medium 은 cap 무관 (이미 신중 톤) — 강등 안 함."""
    from ui.render import _displayed_confidence
    body = "본 query 에 직접 매칭되는 사규가 검색되지 않았습니다. 인사교육팀 문의."
    assert _displayed_confidence("low", body) == "low"
    assert _displayed_confidence("medium", body) == "medium"


def test_displayed_confidence_empty_text_unchanged():
    """방어: answer_text 없으면 변경 X (streaming 초기 등 보호)."""
    from ui.render import _displayed_confidence
    assert _displayed_confidence("high", "") == "high"
    assert _displayed_confidence("high", None) == "high"


def test_verdict_trustworthy_graceful_is_false():
    """#336-5: graceful('직접 매칭 미발견') 답변은 평결카드 stance 비신뢰 → False."""
    from ui.render import _verdict_trustworthy
    body = "[💡 안내] 본 query 에 직접 매칭되는 사규가 검색되지 않았습니다.\n인사교육팀 문의."
    assert _verdict_trustworthy(body) is False


def test_verdict_trustworthy_normal_is_true():
    """무회귀: graceful 마커 없는 정상 답변은 신뢰 가능 → True (평결카드 렌더)."""
    from ui.render import _verdict_trustworthy
    body = "직장 내 괴롭힘은 지체없이 신고하여야 한다. 위반 시 임직원 징계기준 적용."
    assert _verdict_trustworthy(body) is True


def test_verdict_trustworthy_empty_is_true():
    """None-safe: answer_text None/'' 은 True (호출자 별도 가드 책임 — TypeError 방지)."""
    from ui.render import _verdict_trustworthy
    assert _verdict_trustworthy(None) is True
    assert _verdict_trustworthy("") is True


def test_displayed_confidence_graceful_new_wording():
    from ui.render import _displayed_confidence
    body = "[💡 안내] 질문하신 내용에 직접 해당하는 사규를 찾지 못했습니다. 정보보안담당 문의."
    assert _displayed_confidence("high", body) == "medium"


def test_verdict_trustworthy_new_wording_is_false():
    from ui.render import _verdict_trustworthy
    body = "[💡 안내] 질문하신 내용에 직접 해당하는 사규를 찾지 못했습니다. 정보보안담당 문의."
    assert _verdict_trustworthy(body) is False


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
