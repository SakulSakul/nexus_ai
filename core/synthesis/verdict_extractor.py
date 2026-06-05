"""Verdict Extractor — 성숙한 답변 위에 얹는 구조화 판정 레이어 (Stage 1: Shadow).

안전 원칙:
- 거짓 '금지'(불편/안전) ≫ 거짓 '허용'(위험). 불확실 시 항상 엄격쪽/확인필요.
- 인용문은 LLM 이 짓지 않는다: LLM 은 evidence_index 만 지목, 코드가 chunk 본문에서 verbatim 복사.
- 모든 실패/불확실 → None → 호출측 fallback(헤더 없이 본문만). 답변 무손실.
- nexus_critical_classifier 와 동일 패턴(_gen_claude · JSON only · fail-safe).

인용(quote) 선택 — 사규봇 보수 정책:
- A) 주 지침(최빈 doc) 문장 우선 → 엉뚱한 다른 지침 인용 차단.
- B) badge(판정 핵심어) 정합 우선 + 게이트 → badge 와 전혀 안 겹치면 인용 생략.
     겉도는 인용보다 무인용이 안전(카드는 pill+본문 유지).
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


_NEG = ("미", "비", "불")  # 부정 접두 — '신고'≠'미/비신고', '공정'≠'불공정' 의미반전 차단


def _term_in(w: str, s: str) -> bool:
    """w 가 s 에 등장하되 부정접두(미/비/불) 바로 뒤 형태는 제외(반의어 오매칭 차단)."""
    i = s.find(w)
    while i != -1:
        if i == 0 or s[i - 1] not in _NEG:
            return True
        i = s.find(w, i + 1)
    return False


def _score_sentence(sent: str, kw: set) -> float:
    """문장 점수 = 변별 키워드 적중 수 (+규칙신호 소폭 가산)."""
    if any(a in sent for a in _ADMIN):
        return -1.0
    hits = sum(1 for w in kw if _term_in(w, sent))
    sig = 0.5 if any(g in sent for g in _SIG) else 0.0
    return hits + sig


def _pick_quote_global(chunks: list, kw: set, badge_kw: set, dom_doc: str,
                       max_len: int = 135) -> tuple:
    """전체 chunk 의 모든 문장 중 verdict 와 가장 정합하는 '실제 규칙 문장' 선택.
       반환: (문장, chunk_index) 또는 (None, None) — 사규봇 보수적 정책:

       A) 주 지침(dom_doc) 문장 가산 → 엉뚱한 다른 지침 인용 차단.
       B) badge(판정 핵심어) 정합 우선 + 게이트 → badge 와 전혀 안 겹치는
          문장만 남으면 인용 생략(None). 겉도는 인용보다 무인용이 안전.
       (stance/conf 안전 판정은 호출측에서 이미 확정 — 여기는 인용 선택만)

       record: (score, badge_hits, same_doc, length, idx, sent)
    """
    scored, longish = [], []
    for i, c in enumerate(chunks):
        if not isinstance(c, dict):
            continue
        same = 1 if (dom_doc and _chunk_title(c) == dom_doc) else 0
        for sent in _sentences_of(c):
            L = len(sent)
            if L < 12 or any(a in sent for a in _ADMIN):
                continue
            kwh = sum(1 for w in kw if _term_in(w, sent))
            bh = sum(1 for w in badge_kw if _term_in(w, sent))
            sig = 0.5 if any(g in sent for g in _SIG) else 0.0
            sc = kwh + sig + 2.0 * bh + (3.0 if same else 0.0)
            if sc <= 0:
                continue
            (scored if L <= max_len else longish).append((sc, bh, same, L, i, sent))

    _gate = bool(badge_kw)
    # 정렬: (badge 정합 우선) → 점수 → 짧은 문장 → 먼저 나온 것
    # 정렬: (1) 주지침 우선(하드) → (2) badge 정합 → (3) 점수 → (4) 짧은 문장
    _key = lambda x: (-x[2], -(1 if (_gate and x[1] > 0) else 0), -x[0], x[3])
    try:
        _t = sorted(scored, key=_key)[:5]
        print("[verdict_extractor:quote_cands] " + " || ".join(
            f"#{ci} s={s:.1f} b={bh} d={sd} L={ln} {st[:30]!r}"
            for (s, bh, sd, ln, ci, st) in _t), file=sys.stderr, flush=True)
        _l = sorted(longish, key=_key)[:3]
        if _l:
            print("[verdict_extractor:quote_long] " + " || ".join(
                f"#{ci} s={s:.1f} b={bh} L={ln} {st[:40]!r}"
                for (s, bh, sd, ln, ci, st) in _l), file=sys.stderr, flush=True)
    except Exception:
        pass

    if not scored:
        return None, None
    best = sorted(scored, key=_key)[0]
    # B) 보수적 게이트: badge 가 있는데 최선 후보가 badge 핵심어와 0개 겹침 → 인용 생략
    if _gate and best[1] == 0:
        try:
            print("[verdict_extractor:quote_gate] suppressed (no badge-term match)",
                  file=sys.stderr, flush=True)
        except Exception:
            pass
        return None, None
    return best[5], best[4]


def _pick_quote(chunk: dict, max_len: int = 135) -> str:
    """단일 chunk fallback (보존 — 현재 경로 미사용)."""
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


def _is_penalty(c: dict) -> bool:
    """결과(징계) 문서 식별 — doc_kind=='penalty' 또는 제목에 '징계기준'.
    평결 헤드라인 dom_doc 후보에서 결과문서를 배제하기 위한 술어."""
    return (c.get("doc_kind") or "").strip().lower() == "penalty" or "징계기준" in _chunk_title(c)


_SOP_TITLES = {"(공통) 일반 사건사고 보고지침", "(공통) 중대 사건사고 보고지침"}


def _is_nonsubject(c: dict) -> bool:
    """평결 헤드라인 dom 후보에서 제외할 '비-주제' 문서.
    penalty(징계기준) 또는 universal-SOP(사건사고 보고지침) — 여기저기 강제 주입/인용
    되지만 질의의 주제가 아닌 경우. 단 주제 문서가 인용 안 됐으면(=보고/징계 자체가
    주제) _select_dom_doc 의 2-tier 폴백이 이들을 유지한다(과교정 방지)."""
    return _is_penalty(c) or bool(c.get("is_universal_sop")) or _chunk_title(c) in _SOP_TITLES


def _select_dom_doc(all_chunks: list, answer: str) -> str:
    """평결 주지침(dom_doc) 선택.

    rerank#1 을 기본 유지하되, rerank#1 이 본문에 _인용조차 안 됐을_ 때만(=순수 검색
    노이즈) 본문 최빈 doc 으로 교체한다. 단 본문최빈이 penalty(징계기준=결과 문서)면
    비-penalty 인용 문서를 우선한다 — 결과문서가 평결 헤드라인을 가로채는 #336 계열
    회귀 차단. 인용된 게 penalty 뿐이면(=진짜 징계 질의) penalty 를 유지(과교정 방지).
    """
    _all = [c for c in all_chunks if isinstance(c, dict)]
    _dom = _chunk_title(_all[0]) if _all else ""

    def _cited(_t: str) -> int:
        if not _t:
            return 0
        _tb = _t.split(") ", 1)[1] if _t.startswith("(") and ") " in _t else _t
        return answer.count(_t) + (answer.count(_tb) if _tb != _t else 0)

    _r1 = _dom
    _r1_cited = _cited(_r1) > 0
    if not _r1_cited:
        _seen = set()
        _best_np = ("", 0)
        _best_p = ("", 0)
        for _c in _all:
            _t = _chunk_title(_c)
            if not _t or _t in _seen:
                continue
            _seen.add(_t)
            _n = _cited(_t)
            if _n <= 0:
                continue
            if _is_nonsubject(_c):
                if _n > _best_p[1]:
                    _best_p = (_t, _n)
            elif _n > _best_np[1]:
                _best_np = (_t, _n)
        if _best_np[1] > 0:
            _dom = _best_np[0]
        elif _best_p[1] > 0:
            _dom = _best_p[0]
    try:
        print(f"[verdict_extractor:dom_doc] r1={_r1!r} r1_cited={_r1_cited} "
              f"-> dom={_dom!r}", file=__import__("sys").stderr, flush=True)
    except Exception:
        pass
    return _dom


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
        # 인용 선택 = 문장 단위 + 사규봇 보수 정책(A 주지침 우선 / B badge 정합 게이트).
        #   변별 키워드 = label+badge+답변본문(공통 문서명 토큰 제거).
        #   badge_kw = 판정 핵심어만 — 정합 우선·게이트 기준.
        #   (stance/conf 안전 판정은 위에서 이미 확정 — 여기는 인용 선택만)
        _title_toks = _keywords(" ".join(_chunk_title(c) for c in _all), drop=set())
        _kw = _keywords(
            f"{parsed.get('label') or ''} {parsed.get('badge') or ''} {answer[:400]}",
            drop=_title_toks,
        )
        _badge_kw = _keywords(str(parsed.get("badge") or ""), drop=_title_toks)
        # 주 지침(dom_doc) 선택은 _select_dom_doc 로 위임(추출+penalty-skip, 테스트 가능).
        _dom_doc = _select_dom_doc(_all, answer)
        _qs, _cand = _pick_quote_global(_all, _kw, _badge_kw, _dom_doc)
        # 보수적: 정합 인용이 없으면(_qs None) 억지 fallback 금지 → 인용 생략(카드는 pill+본문).
        if _qs is not None:
            quote = _qs
        if _cand is not None and 0 <= _cand < len(_all):
            doc_title, clause = _chunk_title(_all[_cand]), _chunk_clause(_all[_cand])
        try:
            print(f"[verdict_extractor:quote_pick] chosen={_cand} kw={len(_kw)} "
                  f"badge_kw={len(_badge_kw)} q={quote[:48]!r}", file=sys.stderr, flush=True)
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
