"""PII 마스킹 — DB/AI 호출 직전 전처리 단계에서 호출한다.

- 이메일·주민번호·휴대폰·일반전화 — 표준 패턴
- 사번·계좌번호·신용카드·차량번호 — 한국 환경 특화
- 한국어 인명 + 직책/호칭 동반 — 보수적 매칭 (false-positive 최소화)
- 부서명 — 일반 패턴 (00팀 / 00실 / 00본부 / 00사업부 / 00센터)
- extra_terms — 호출자가 추가 마스킹할 단어 (회사 부서 사전 등)

⚠ 본 모듈은 정규식 기반의 "1차 보호막" 임. 한국어 NER 모델 도입 전까지는
직책 없이 등장하는 인명, 비표준 사번 등은 누수될 수 있음. 정식 운영 이관
시점에는 NER(klue-ner 등) 또는 LLM-based PII guard 로 보강 예정. 본 모듈
한계는 베타 동의서 §1 에서 사용자에게 고지함.
"""

from __future__ import annotations

import re
from typing import Iterable

ANON = "[익명]"

# ── 표준 패턴 ─────────────────────────────────────────────────
_RE_EMAIL    = re.compile(r"[\w\.\-+]+@[\w\.\-]+\.[A-Za-z]{2,}")
_RE_RRN      = re.compile(r"\b\d{6}-\d{7}\b")
_RE_PHONE    = re.compile(r"\b01[016-9]-?\d{3,4}-?\d{4}\b")
_RE_PHONE2   = re.compile(r"\b0\d{1,2}-\d{3,4}-\d{4}\b")

# ── 사번 — '사번/사원번호/직원번호/사원ID/emp_no' 키워드 동반 ──
_RE_EMP_ID = re.compile(
    r"(?P<key>(?:사번|사원\s*번호|직원\s*번호|사원\s*ID|emp[_\s-]?no|employee[_\s-]?id))"
    r"\s*[:：=]?\s*(?P<val>[A-Za-z0-9-]{4,12})",
    re.IGNORECASE,
)

# ── 사번 — 6자리 숫자 standalone (회사 사번 표준 형식) ──
# 신세계면세점 사번은 6자리(예: 182491). 키워드 동반 없이 본문에 등장하는
# 케이스 ('내 사번은 182491', '182491 직원이' 등) 도 마스킹.
# (?<!\d)/(?!\d) 로 인접 숫자 배제 — Python \b 가 한글-숫자 경계를 인식
# 못 하기 때문에 lookbehind/lookahead 사용. 한글/공백 인접은 허용.
# RRN/카드/계좌 마스킹 이후에 적용해 큰 구조의 부분 매치를 방지.
# false-positive: 200000원 같은 6자리 금액·기타 6자리 통계 → 보수적으로 마스킹
# 허용 (PII 보호 측면에서 false-negative 보다 낫다).
_RE_EMP_ID_6 = re.compile(r"(?<!\d)\d{6}(?!\d)")

# ── 신용카드 — 4-4-4-4 그룹 (공백·하이픈 허용, 16자리) ────────
_RE_CARD = re.compile(r"\b(?:\d{4}[\s-]?){3}\d{4}\b")

# ── 계좌번호 — 숫자 그룹 dash/space 묶음 (총 10자리 이상) ────
# 예: 110-123-456789, 1002 345 6789012
_RE_BANK = re.compile(r"\b\d{2,6}[\s-]\d{2,6}[\s-]\d{2,8}\b")

# ── 한국 자동차 번호판 — 12가1234 / 12가 1234 / 123가 4567 ──
_RE_PLATE = re.compile(r"\b\d{2,3}\s*[가-힣]\s*\d{4}\b")

# ── 한국어 인명 + 직책/호칭 (확장) ─────────────────────────────
# 한국어 인명은 false-positive 위험이 매우 커서, 직책·호칭이 동반될 때만 매치.
# 회사 표준 직책: 대표이사·부사장·전무·상무·이사·담당·팀장·CP(=Chief Partner)·파트너
# 약어(CP)·풀네임(Chief Partner / 치프 파트너) 4종 모두 매칭. 영문은 IGNORECASE.
_HONORIFICS = (
    "님|씨|군|양|"
    "과장|차장|부장|팀장|담당|실장|본부장|상무|전무|부사장|사장|회장|"
    "대표이사|대표|이사|"
    "Chief\\s*Partner|치프\\s*파트너|CP|파트너|"
    "대리|사원|주임|선임|책임|수석|"
    "원장|소장|센터장|국장|"
    "의원|장관|차관|시장|구청장|군수"
)
_RE_NAME_HONOR = re.compile(rf"([가-힣]{{2,4}})\s*({_HONORIFICS})", re.IGNORECASE)

# ── 직급(pay band) — 회사 표준 4가지 표기 ────────────────────
# 한국어: 밴드1, 밴드4-2, 밴드 5
# 영어:   band1, band 4-2
# 약어:   b1, B5  (false-positive 가능: 'B1 vitamin', 'B1층' 등 — PII 우선)
_RE_BAND_KO   = re.compile(r"밴드\s*\d{1,2}(?:-\d{1,2})?")
# \b 가 영문-한글 경계를 인식 못 하므로(예: 'b1이래') lookbehind/lookahead 로
# 알파뉴메릭만 배제. 한글·공백·구두점 인접은 허용.
_RE_BAND_EN = re.compile(
    r"(?<![A-Za-z0-9])band\s*\d{1,2}(?:-\d{1,2})?(?![A-Za-z0-9])",
    re.IGNORECASE,
)
_RE_BAND_ABBR = re.compile(
    r"(?<![A-Za-z0-9])b\s*\d{1,2}(?:-\d{1,2})?(?![A-Za-z0-9])",
    re.IGNORECASE,
)

# ── 부서명 후보 — 일반 패턴 ────────────────────────────────────
_RE_DEPT = re.compile(
    r"[가-힣A-Za-z0-9]{2,15}(팀|실|본부|사업부|센터|그룹|국)"
)

# ── 영문 이름 — 매우 보수적: 'Mr./Ms./Dr.' 등 호칭 동반 시만 ──
# 자유 매칭(예: New York 까지 매치) 은 false-positive 폭증이라 컨텍스트 필수.
_RE_EN_NAME = re.compile(
    r"\b(?:Mr|Mrs|Ms|Dr|Prof)\.?\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?\b"
)


def mask_pii(text: str, extra_terms: Iterable[str] = ()) -> str:
    if not text:
        return text
    out = text
    out = _RE_EMAIL.sub(ANON, out)
    out = _RE_RRN.sub(ANON, out)
    out = _RE_PHONE.sub(ANON, out)
    out = _RE_PHONE2.sub(ANON, out)
    out = _RE_CARD.sub(ANON, out)
    out = _RE_BANK.sub(ANON, out)
    out = _RE_PLATE.sub(ANON, out)
    # 사번: 키워드 보존 + 값 마스킹 ('사번: [익명]')
    out = _RE_EMP_ID.sub(lambda m: f"{m.group('key')}: {ANON}", out)
    # 사번 standalone (6자리) — RRN/카드/계좌 마스킹 이후 적용
    out = _RE_EMP_ID_6.sub(ANON, out)
    out = _RE_NAME_HONOR.sub(lambda m: f"{ANON} {m.group(2)}", out)
    out = _RE_DEPT.sub(ANON, out)
    out = _RE_EN_NAME.sub(ANON, out)
    # 직급(밴드) — 한국어/영어/약어 3종 모두 마스킹
    out = _RE_BAND_KO.sub(ANON, out)
    out = _RE_BAND_EN.sub(ANON, out)
    out = _RE_BAND_ABBR.sub(ANON, out)

    for term in extra_terms:
        term = (term or "").strip()
        if len(term) >= 2:
            out = re.sub(re.escape(term), ANON, out)
    return out
