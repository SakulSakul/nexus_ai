"""Verdict Extractor — 성숙한 답변 위에 얹는 구조화 판정 레이어 (Stage 1: Shadow).

안전 원칙:
- 거짓 '금지'(불편/안전) ≫ 거짓 '허용'(위험). 불확실 시 항상 엄격쪽/확인필요.
- 인용문은 LLM 이 짓지 않는다: LLM 은 evidence_index 만 지목, 코드가 chunk 본문에서 verbatim 복사.
- 모든 실패/불확실 → None → 호출측 fallback(헤더 없이 본문만). 답변 무손실.
- nexus_critical_classifier 와 동일 패턴(_gen_claude · JSON only · fail-safe).
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass, asdict

VERDICT_STANCES = ("금지", "신고대상", "조건부", "허용", "확인필요")
_FAILSAFE = "확인필요"


@dataclass(frozen=True)
class Verdict:
    stance: str
    label: str
    badge: str
    quote: str
    doc_title: str
    clause: str
    confidence: str
    rationale: str

    def to_dict(self) -> dict:
        return asdict(self)


_SYSTEM = """당신은 신세계디에프 컴플라이언스 챗봇의 '판정 추출기'입니다.
이미 생성된 답변과 근거 사규 조각(chunks)을 읽고 사용자 행위에 대한 판정을 구조화합니다.

[stance — 반드시 아래 중 하나]
- "금지": 사규가 명백히 금지. 위반 시 징계.
- "신고대상": 신고/보고/자진신고 의무 발생.
- "조건부": 일정 한도·조건 내 허용, 초과 시 제한.
- "허용": 사규상 문제 없음 (근거가 명확할 때만).
- "확인필요": 근거 불충분/모호. 판단이 안 서면 반드시 이것.

[절대 안전 규칙]
1. 거짓 '허용' 금지. 조금이라도 불확실하면 "확인필요" 또는 더 엄격한 쪽.
2. 근거를 지어내지 말 것. 핵심 근거가 담긴 chunk 의 evidence_index(번호)만 지목.
3. label 은 한국어 짧은 구 (예: "금지 · 신고 대상", "조건부 허용").
4. badge 는 핵심 임계/조건 한 조각 (예: "10만원 초과", "업무 목적만"), 없으면 "".

[출력 — JSON 만, 설명 금지]
{"stance":"...","label":"...","badge":"...","evidence_index":<int|null>,"confidence":"high|medium|low","rationale":"한 문장"}
"""


def _ck(c: dict, keys: tuple) -> str:
    for k in keys:
        v = c.get(k)
        if v:
            return str(v)
    return ""


def _chunk_text(c: dict) -> str:
    return _ck(c, ("text", "content", "chunk_text", "body"))


def _chunk_title(c: dict) -> str:
    return _ck(c, ("doc_title", "title", "document_title", "source"))


def _chunk_clause(c: dict) -> str:
    return _ck(c, ("clause", "article", "조항", "section"))


def _pick_quote(chunk: dict, max_len: int = 170) -> str:
    text = _chunk_text(chunk).strip()
    if not text:
        return ""
    # 1) 선두 [문서 안내]·문서정보 메타 헤더 스킵.
    _meta = ("문서번호", "관리부서", "개정일자", "개정 1호", "개정일")
    _body = []
    _skipping = True
    for _ln in text.split("\n"):
        _ls = _ln.strip()
        if _skipping:
            if not _ls:
                continue
            if _ls.startswith("[") or any(_m in _ls for _m in _meta):
                continue
            _skipping = False
        _body.append(_ls)
    body = " ".join(_body).strip() or text
    # 2) 문장 분할 (한국어 종결 '다.' / 마침표 / 줄바꿈).
    import re as _re
    sents = [x.strip() for x in _re.split(r"(?<=다\.)\s+|(?<=\.)\s+|\n", body) if x.strip()]
    if not sents:
        return body[:max_len].strip()
    # 3) 규칙 신호 문장 우선 인용 — 행정·안내 문장은 회피.
    _sig = ("금지", "할 수 없", "하여야", "하여서는", "해서는 안", "안 된다", "아니 된다",
            "원칙으로", "위반", "수수", "신고", "보고", "준수", "징계")
    _admin = ("문의", "양식", "서식", "사본", "최신본", "다운로드", "안내합니다")
    for _s in sents:
        if len(_s) <= max_len and any(g in _s for g in _sig) and not any(a in _s for a in _admin):
            return _s
    # 4) fallback: 행정 문장 제외 첫 적정 문장 → 그래도 없으면 첫 문장 절단.
    for _s in sents:
        if 10 <= len(_s) <= max_len and not any(a in _s for a in _admin):
            return _s
    return sents[0][:max_len].strip()


def extract_verdict(question: str, answer: str, chunks: list) -> "Verdict | None":
    """답변 + chunks → Verdict. 실패/불확실 시 None(호출측 fallback)."""
    if not answer or not chunks:
        return None
    try:
        top = [c for c in chunks if isinstance(c, dict)][:6]
        if not top:
            return None
        listing = "\n".join(
            f"[{i}] {(_chunk_title(c) or '제목없음')}: {_chunk_text(c)[:300]}"
            for i, c in enumerate(top)
        )
        user = (
            f"[질문]\n{question}\n\n"
            f"[생성된 답변]\n{answer[:2500]}\n\n"
            f"[근거 chunks]\n{listing}\n\n"
            "위를 근거로 판정 JSON 을 출력하세요."
        )
        from core.chatbot import _gen_claude
        text, _, _ = _gen_claude(system=_SYSTEM, user=user, include_thinking=False)

        s, e = text.find("{"), text.rfind("}")
        if s < 0 or e < 0 or e < s:
            return None
        parsed = json.loads(text[s:e + 1])

        stance = parsed.get("stance")
        if stance not in VERDICT_STANCES:
            stance = _FAILSAFE
        conf = parsed.get("confidence")
        if conf not in ("high", "medium", "low"):
            conf = "low"
        if stance == "허용" and conf != "high":
            stance = _FAILSAFE

        quote = doc_title = clause = ""
        ev = parsed.get("evidence_index")
        if isinstance(ev, int) and 0 <= ev < len(top):
            ch = top[ev]
            quote, doc_title, clause = _pick_quote(ch), _chunk_title(ch), _chunk_clause(ch)

        v = Verdict(
            stance=stance,
            label=str(parsed.get("label") or stance)[:40],
            badge=str(parsed.get("badge") or "")[:24],
            quote=quote, doc_title=doc_title, clause=clause,
            confidence=conf,
            rationale=str(parsed.get("rationale") or "")[:200],
        )
        print(f"[verdict_extractor] stance={v.stance} conf={v.confidence} "
              f"badge={v.badge!r} ev={ev} q_len={len(v.quote)}",
              file=sys.stderr, flush=True)
        return v
    except Exception as e:
        print(f"[verdict_extractor] failed (non-blocking): {type(e).__name__}: {e}",
              file=sys.stderr, flush=True)
        return None
