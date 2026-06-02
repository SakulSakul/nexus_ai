"""Verdict Extractor — 성숙한 답변 위에 얹는 구조화 판정 레이어 (Stage 1: Shadow).

안전 원칙:
- 거짓 '금지'(불편/안전) ≫ 거짓 '허용'(위험). 불확실 시 항상 엄격쪽/확인필요.
- 인용문은 LLM 이 짓지 않는다: LLM 은 evidence_index 만 지목, 코드가 chunk 본문에서 verbatim 복사.
- 모든 실패/불확실 → None → 호출측 fallback(헤더 없이 본문만). 답변 무손실.
- nexus_critical_classifier 와 동일 패턴(_gen_claude · JSON only · fail-safe).
"""
from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, asdict

VERDICT_STANCES = ("금지", "신고대상", "조건부", "허용", "확인필요")
_FAILSAFE = "확인필요"

# 규칙 신호 / 행정·메타 문장 마커
_SIG = ("금지", "할 수 없", "하여야", "하여서는", "해서는 안", "안 된다", "아니 된다",
        "원칙으로", "위반", "수수", "신고", "보고", "준수", "징계", "한도", "초과",
        "승인", "발급", "대상", "이내", "이상", "이하")
_ADMIN = ("문의", "양식", "서식", "사본", "최신본", "다운로드", "안내합니다", "참고하시기")
_META = ("문서번호", "관리부서", "개정일자", "개정 1호", "개정일", "제정일")
# 모든 chunk 에 공통 등장 → 변별력 없는 불용어 (질의별 인용 구분을 방해)
_STOP = {"있습니다", "합니다", "됩니다", "경우", "관련", "대한", "대해", "위해", "또는",
         "그리고", "따라", "통해", "에서", "으로", "하는", "하여", "사용", "문서",
         "지침", "규정", "관리", "다음", "같습니다", "내용", "질문", "답변", "원칙",
         "이를", "있으며", "되며", "임직원"}


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


def _sentences_of(chunk: dict) -> list:
    """chunk 본문 → 메타/안내 헤더 스킵 후 문장 리스트."""
    text = _chunk_text(chunk).strip()
    if not text:
        return []
    _body = []
    _skipping = True
    for _ln in text.split("\n"):
        _ls = _ln.strip()
        if _skipping:
            if not _ls:
                continue
            if _ls.startswith("[") or any(_m in _ls for _m in _META):
                continue
            _skipping = False
        _body.append(_ls)
    body = " ".join(_body).strip() or text
    sents = [x.strip() for x in re.split(r"(?<=다\.)\s+|(?<=\.)\s+|\n", body) if x.strip()]
    return sents


def _keywords(text: str, drop: set) -> set:
    """변별 키워드 집합: 혼합 토큰 + 한글 하위토큰, 불용어/문서명 제거."""
    kw = set(re.findall(r"[가-힣A-Za-z0-9]{2,}", text))
    for m in re.findall(r"[가-힣]{2,}", text):  # '10백만' → '백만' 등 한글 런 추출
        kw.add(m)
    return {w for w in kw if w not in drop and w not in _STOP}


def _score_sentence(sent: str, kw: set) -> float:
    """문장 점수 = 변별 키워드 적중 수 (+규칙신호 소폭 가산)."""
    if any(a in sent for a in _ADMIN):
        return -1.0
    hits = sum(1 for w in kw if w in sent)
    sig = 0.5 if any(g in sent for g in _SIG) else 0.0
    return hits + sig


def _pick_quote_global(chunks: list, kw: set, max_len: int = 135) -> tuple:
    """전체 chunk 의 모든 문장 중 답변 키워드와 가장 겹치는 '실제 규칙 문장' 선택.
       반환: (문장, chunk_index) 또는 (None, None)."""
    best_s, best_i, best_score = None, None, 0.0
    for i, c in enumerate(chunks):
        if not isinstance(c, dict):
            continue
        for sent in _sentences_of(c):
            if not (12 <= len(sent) <= max_len):
                continue
            sc = _score_sentence(sent, kw)
            # 더 높은 점수 우선 / 동점이면 더 짧은(집중된) 문장
            if sc > best_score or (sc == best_score and best_s is not None and len(sent) < len(best_s)):
                if sc > 0:
                    best_s, best_i, best_score = sent, i, sc
    return best_s, best_i


def _pick_quote(chunk: dict, max_len: int = 135) -> str:
    """단일 chunk fallback (글로벌 선택 실패 시)."""
    sents = _sentences_of(chunk)
    if not sents:
        return ""
    for _s in sents:
        if len(_s) <= max_len and any(g in _s for g in _SIG) and not any(a in _s for a in _ADMIN):
            return _s
    for _s in sents:
        if 12 <= len(_s) <= max_len and not any(a in _s for a in _ADMIN):
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
        _all = [c for c in chunks if isinstance(c, dict)]
        # 인용 선택 = 문장 단위 (chunk 단위 X — 문서안내 요약 chunk 가 항상 이김).
        #   변별 키워드 = label+badge+답변본문, 단 모든 chunk 공통 문서명 토큰 제거.
        #   (stance/conf 안전 판정은 위에서 이미 확정 — 여기는 인용 문장 선택만)
        _title_toks = _keywords(" ".join(_chunk_title(c) for c in _all), drop=set())
        _kw = _keywords(
            f"{parsed.get('label') or ''} {parsed.get('badge') or ''} {answer[:400]}",
            drop=_title_toks,
        )
        _qs, _cand = _pick_quote_global(_all, _kw)
        if _qs is not None:
            quote = _qs
        elif isinstance(ev, int) and 0 <= ev < len(_all):
            _cand = ev
            quote = _pick_quote(_all[_cand])
        elif _all:
            _cand = 0
            quote = _pick_quote(_all[0])
        if _cand is not None and 0 <= _cand < len(_all):
            doc_title, clause = _chunk_title(_all[_cand]), _chunk_clause(_all[_cand])
        try:
            print(f"[verdict_extractor:quote_pick] chosen={_cand} kw={len(_kw)} "
                  f"q={quote[:48]!r}", file=sys.stderr, flush=True)
        except Exception:
            pass

        v = Verdict(
            stance=stance,
            label=str(parsed.get("label") or stance)[:40],
            badge=str(parsed.get("badge") or "")[:24],
            quote=quote, doc_title=doc_title, clause=clause,
            confidence=conf,
            rationale=str(parsed.get("rationale") or "")[:200],
        )
        print(f"[verdict_extractor] stance={v.stance} conf={v.confidence} "
              f"badge={v.badge!r} ev={ev} pick={_cand} q_len={len(v.quote)}",
              file=sys.stderr, flush=True)
        return v
    except Exception as e:
        print(f"[verdict_extractor] failed (non-blocking): {type(e).__name__}: {e}",
              file=sys.stderr, flush=True)
        return None
