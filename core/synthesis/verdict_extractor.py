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


def _pick_quote(chunk: dict, max_len: int = 140) -> str:
    text = _chunk_text(chunk).strip()
    if not text:
        return ""
    for sep in (". ", ".\n", "다.", "\n"):
        idx = text.find(sep)
        if 0 < idx <= max_len:
            return text[: idx + len(sep)].strip()
    return text[:max_len].strip()


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
