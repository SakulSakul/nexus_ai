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
# 못 하기 때문에 lookbehind/lookahead 사용.
# RRN/카드/계좌 마스킹 이후에 적용해 큰 구조의 부분 매치를 방지.
# 명백한 비-PII 컨텍스트(원/만/회/명/건/일/년/개/차/호/쪽/페이지) 는 negative
# lookahead 로 제외 — 답변 가독성 보호. 그 외는 보수적으로 마스킹 (PII 우선).
_RE_EMP_ID_6 = re.compile(
    r"(?<!\d)\d{6}(?!\d|\s*(?:원|만|회|명|건|일|년|개|차|호|쪽|페이지|등|초|분|시|월))"
)

# ── 신용카드 — 4-4-4-4 그룹 (공백·하이픈 허용, 16자리) ────────
_RE_CARD = re.compile(r"\b(?:\d{4}[\s-]?){3}\d{4}\b")

# ── 계좌번호 — 숫자 그룹 dash/space 묶음 (총 10자리 이상) ────
# 예: 110-123-456789, 1002 345 6789012
_RE_BANK = re.compile(r"\b\d{2,6}[\s-]\d{2,6}[\s-]\d{2,8}\b")

# ── 한국 자동차 번호판 — 12가1234 / 12가 1234 / 123가 4567 ──
_RE_PLATE = re.compile(r"\b\d{2,3}\s*[가-힣]\s*\d{4}\b")

# ── 한국어 인명 + 직책/호칭 (정밀화 — PR-Q5) ──────────────────
# 이전 패턴 ([가-힣]{2,4} + 직책) 은 false-positive 다발 발생:
#  · "안전관리 책임" 의 "안전관리"(4자) + "책임" → mask
#  · "윤리경영 팀장" 의 "윤리경영"(4자) + "팀장" → mask
#  · "법무 담당" 의 "법무"(2자) + "담당" → mask
# 일반 명사구를 사람으로 오인 → retrieval 정확도 훼손.
#
# 정밀화 정책:
#  1) 한글 성씨 화이트리스트 (단음절 ~60종 + 복성 7종) 로 시작 토큰 좁힘
#  2) 성씨 직전이 한글이면 매치 X (단어 경계 — 부서/주제 명사 중간 매치 차단).
#     예: "안전관리" 의 "전"이 성씨 후보지만 직전 "안" 이 한글 → 차단.
#  3) 이름 길이 0~2 자 (한국 이름은 통상 1~2 자, 0 자는 "성씨 단독 + 직책")
#  4) _HONORIFICS 에서 일반 명사화된 어휘 ("책임", "수석") 제거.
#     "매니저" 추가 (성씨 동반 시만 매치되므로 안전).
# 정책 한계: "윤리경영 팀장" 같이 성씨 시작 + 부서명 토큰 케이스는 여전히
# false positive 가능 (윤+리경+팀장). 사용자 검증·admin PII 테스트 탭으로
# 모니터링. 한국어 NER 도입 시 root fix.
#
# 한국 단음절 성씨 (인구 ~99% 커버, top ~60).
_KO_SURNAMES_SINGLE = (
    "김|이|박|최|정|강|조|윤|장|임|한|오|서|신|권|황|안|송|류|전|홍|"
    "고|문|양|손|배|백|허|유|남|심|노|하|곽|성|차|주|우|구|나|민|진|"
    "지|엄|채|원|천|방|공|현|함|변|염|여|추|도|소|석|선|설|마|길|연|위"
)
# 복성 (희소하지만 실재).
_KO_SURNAMES_DOUBLE = "남궁|선우|황보|독고|서문|사공|제갈"

_HONORIFICS = (
    "님|씨|군|양|"
    "과장|차장|부장|팀장|담당|실장|본부장|상무|전무|부사장|사장|회장|"
    "대표이사|대표|이사|"
    "Chief\\s*Partner|치프\\s*파트너|CP|파트너|"
    "대리|사원|주임|선임|매니저|"
    "원장|소장|센터장|국장|"
    "의원|장관|차관|시장|구청장|군수"
)
# 단어 경계 (?<![가-힣]) 로 부서/주제 명사 중간의 성씨 후보 매칭 차단.
# 복성을 단음절보다 먼저 시도해서 "남궁" 의 "남"만 단독 매치되는 사고 방지.
_RE_NAME_HONOR = re.compile(
    rf"(?<![가-힣])(?:{_KO_SURNAMES_DOUBLE}|{_KO_SURNAMES_SINGLE})"
    rf"[가-힣]{{0,2}}\s*({_HONORIFICS})",
    re.IGNORECASE,
)

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

# ── 부서 오탐 allowlist (V1) ──────────────────────────────────────
# _RE_DEPT 가 '○○실'·'○○국' 같은 1글자 접미사로 일반명사를 부서명으로
# 오인 → [익명] 과매칭하는 결함(예: "회의실"→"[익명]") 보정.
# 패턴 정밀화로는 일반명사(회의실)와 진짜 부서(비서실)를 못 가르므로
# (둘 다 "○○실"), 명시적 일반명사 allowlist 로만 안전하게 예외 처리.
# ⚠️ 안전 규칙: allowlist 에는 일반명사만. 진짜 부서·조직명은 절대 금지
# (넣으면 해당 부서 PII 가 누출됨). 미등록 일반명사는 계속 과마스킹되나
# 이는 '검색 품질 손해'일 뿐 'PII 누출'이 아니므로 안전 방향의 불완전.
_DEPT_ALLOWLIST = frozenset({
    # 시설·공간 (○○실)
    "회의실", "교육실", "자료실", "상황실", "대기실", "휴게실",
    "화장실", "사무실", "탕비실", "흡연실", "당직실", "분실",
    "전산실", "창고실", "안내실", "상담실", "면접실", "강의실",
    # 시설·기관 (○○국)
    "방송국", "우체국", "출입국",
})

def _dept_sub(m):
    """_RE_DEPT 매치 콜백: 매치 전체가 allowlist 일반명사와 '완전 일치'
    할 때만 원문 보존(마스킹 스킵). 그 외 부서 후보는 ANON 마스킹.
    부분 포함이 아닌 완전 일치만 허용 → '회의실장' 등은 보존되지 않음."""
    token = m.group(0)
    if token in _DEPT_ALLOWLIST:
        return token
    return ANON

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
    # PR-Q5: 그룹 1 = honorific (성씨 후보군은 non-capturing). 직책 보존 +
    # 성씨/이름 토큰만 [익명] 으로 치환. 공백 보존을 위해 sub callback 사용.
    out = _RE_NAME_HONOR.sub(lambda m: f"{ANON} {m.group(1)}", out)
    out = _RE_DEPT.sub(_dept_sub, out)
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
