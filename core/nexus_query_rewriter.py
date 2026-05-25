"""Tier 1 — Gemini 기반 쿼리 재작성 (사규 용어 확장) + 한국어 tsquery 빌더.

사용자 자연어 질문이 사규 본문의 한자어·법률 용어와 어휘적으로 불일치할 때
검색 recall 이 떨어지는 문제를 보정한다. 검색 직전에 호출되어 원문 의도를
유지한 채 동의어·상위 개념을 1~3개 덧붙인 키워드 나열형 문자열을 만든다.

설계 원칙:
- Gemini 호출은 core/chatbot.py:_gen_gemini 와 동일 패턴 (google-genai
  Client + types.GenerateContentConfig + res.candidates[0].content.parts).
- 가벼운 non-thinking 모델 (gemini-2.0-flash) · max_output_tokens 128.
  2.5-flash 는 thinking 토큰이 출력 예산을 잠식해 응답이 잘림 — 단순
  키워드 확장에는 thinking 불필요하므로 2.0-flash 로 고정.
- 실패는 절대 raise 하지 않는다. 호출자는 항상 결과 텍스트를 받는다.
- 동일 질문 반복(eval/디버그)에 대비해 lru_cache 적용.
"""

from __future__ import annotations

import functools
import re
import sys
import time

from .config import get_secret, settings


_REWRITE_MODEL = get_secret("NEXUS_QUERY_REWRITE_MODEL", "gemini-2.5-flash-lite")
_MAX_OUTPUT_TOKENS = 128
_REWRITE_TEMPERATURE = 0.0
_MAX_LEN = 60


# 답변용 _gen_gemini 와 동일 구조: system / user 채널 분리.
# 지시문 + few-shot 은 system_instruction 으로, 실제 질문만 contents 로.
_SYSTEM_TEXT = """당신은 사규 검색을 돕는 쿼리 재작성 보조입니다.
사용자의 자연어 질문을 사규 문서에서 사용될 법한 정식 용어·동의어로 확장하세요.

원칙:
- 원문 의도 유지
- 사규에서 쓰이는 한자어·법률 용어 우선 포함
- 동의어·상위 개념 1~3개 추가
- 출력은 검색용 키워드 나열형 단일 문장, 60자 이내
- 답변·설명·문장부호 없이 키워드만

예시:
질문: 고객이 매장에 두고 간 물건은 어떻게 처리하나요?
답: 고객 습득물 유실물 분실물 매장 처리 보관 인계 절차

질문: 거래처가 명절에 선물을 보내왔는데 어떻게 하나요?
답: 이해관계자 금품 수수 명절 선물 클린뱅크 윤리 신고

질문: 사내 자료를 외부 메일로 보낼 때 주의할 점이 있나요?
답: 회사 정보 자료 외부 반출 메일 송신 정보보안 통제 절차

질문: 해외 출장 비용 정산 방법
답: 해외출장비 국내출장비 시내교통비 관리 지침 정산 일당 숙박료

질문: 법인카드를 개인 식사에 사용해도 되나요?
답: 법인카드 관리 지침 부정 사용 정상 사용 정산

질문: 산업재해 발생 시 보고 절차
답: 중대재해 대응 지침 산업재해 안전사고 보고 절차

질문: 경쟁사 직원과 가격 정보 공유해도 되나요?
답: 경쟁사 가격 정보 부당공동행위 담합 공정거래 자율준수 행동강령

질문: 환경 사고 발생 시 어떻게 해야 하나요?
답: 환경 사건 환경경영 매뉴얼 환경 리스크 환경운영 대응

질문: 회사 인장 도용한 사례를 발견했어요
답: 인감 관리 지침 위조 부정사용 사건사고 보고

질문: 외부 강사료를 받았어요
답: 클린뱅크 운영 지침 강사료 수수 CREDO 윤리 신고

질문: 자진 신고하려면 어디로 가야 하나요?
답: 클린뱅크 운영 지침 자진신고 클린신고 SHRS CSR경영란 윤리경영 윤리실천등록

질문: 지인과 거래해도 되나요?
답: 지인 거래 이해상충 신고 CREDO 제3조 이중취업"""

_USER_TEMPLATE = """질문: {user_question}
답:"""


# ── 메타 (admin 디버그 패널 표시용) ─────────────────────────
REWRITE_MODEL_INFO: dict = {
    "model": _REWRITE_MODEL,
    "max_output_tokens": _MAX_OUTPUT_TOKENS,
    "temperature": _REWRITE_TEMPERATURE,
}


def _call_gemini_for_rewrite(user_question: str) -> str:
    """core/chatbot.py:_gen_gemini 패턴을 그대로 따라간다.

    - google-genai Client + GenerateContentConfig
    - response 추출: res.candidates[0].content.parts 전체 text 이어붙임,
      fallback 으로 res.text. 어떤 경우에도 slicing 으로 1글자/1단어 자르지 않음.
    - 503 UNAVAILABLE / 빈 응답 시 1회 retry (1초 sleep). 그래도 실패면
      빈 문자열 반환 (postprocess 가 원문 폴백 처리).
    """
    try:
        from google import genai
        from google.genai import types
    except Exception:
        return ""

    s = settings()
    if not s.gemini_api_key:
        return ""

    user_text = _USER_TEMPLATE.format(user_question=user_question)

    last_text = ""
    # 3 attempts with exponential backoff (1s, 2s, 4s)
    for attempt in (1, 2, 3):
        try:
            cli = genai.Client(api_key=s.gemini_api_key)
            cfg = types.GenerateContentConfig(
                system_instruction=_SYSTEM_TEXT,
                temperature=_REWRITE_TEMPERATURE,
                max_output_tokens=_MAX_OUTPUT_TOKENS,
                top_p=0.1,  # 답변용과 동일 — 결정성 향상
            )
            res = cli.models.generate_content(
                model=_REWRITE_MODEL,
                contents=user_text,
                config=cfg,
            )
        except Exception as e:
            err_str = str(e)
            is_503 = "503" in err_str or "UNAVAILABLE" in err_str.upper()
            is_retryable = is_503 or "429" in err_str or "TIMEOUT" in err_str.upper()
            if is_retryable and attempt < 3:
                wait_s = 2 ** (attempt - 1)  # 1s, 2s, 4s
                print(
                    f"[nexus_query_rewriter] {err_str[:80]} on attempt {attempt}, "
                    f"retrying after {wait_s}s",
                    file=sys.stderr, flush=True,
                )
                time.sleep(wait_s)
                continue
            print(
                f"[nexus_query_rewriter] gemini call failed (attempt {attempt}): "
                f"{type(e).__name__}: {e}",
                file=sys.stderr, flush=True,
            )
            return ""

        # finish_reason 진단 로그 — SAFETY / MAX_TOKENS / RECITATION / OTHER 추적.
        finish_reason = None
        try:
            finish_reason = getattr(res.candidates[0], "finish_reason", None)
        except Exception:
            pass
        if finish_reason is not None and str(finish_reason).upper() not in (
            "STOP", "FINISHREASON.STOP", "1"
        ):
            print(
                f"[nexus_query_rewriter] non-STOP finish_reason={finish_reason}",
                file=sys.stderr, flush=True,
            )

        # 응답 추출 — _gen_gemini 와 동일. 슬라이싱·split 으로 1글자/1단어 자르지 않는다.
        text_parts: list[str] = []
        try:
            for part in res.candidates[0].content.parts:
                if getattr(part, "thought", False):
                    continue
                text_parts.append(getattr(part, "text", "") or "")
        except Exception:
            text_parts = [getattr(res, "text", "") or ""]

        text = "".join(text_parts).strip()
        if not text:
            text = (getattr(res, "text", "") or "").strip()

        if not text and attempt < 3:
            # 빈 응답 → exponential backoff retry
            wait_s = 2 ** (attempt - 1)  # 1s, 2s
            print(
                f"[nexus_query_rewriter] empty response on attempt {attempt}, "
                f"retrying after {wait_s}s",
                file=sys.stderr, flush=True,
            )
            time.sleep(wait_s)
            last_text = ""
            continue

        return text

    return last_text


def _postprocess_rewritten(raw: str, fallback: str) -> str:
    """Gemini 원문 응답 -> 검색용 키워드 문자열로 정규화.
    실패 시 원문 user_question(fallback) 반환.
    """
    if not raw:
        return fallback
    try:
        text = raw.strip()
        # 접두 라벨 제거 (모델이 가끔 붙임)
        for prefix in ("답:", "답 :", "답변:", "Answer:", "A:"):
            if text.startswith(prefix):
                text = text[len(prefix):].strip()
                break
        # 첫 줄만 사용 (모델이 가끔 여러 줄을 출력)
        text = text.splitlines()[0] if text else ""
        # 양쪽 따옴표 제거
        text = text.strip().strip('"').strip("'").strip("「").strip("」").strip()
        # 글자 단위 60자 컷 (바이트 아님)
        if len(text) > _MAX_LEN:
            text = text[:_MAX_LEN]
        # 빈 문자열이면 원문 폴백
        if not text or len(text) < 2:
            return fallback
        return text
    except Exception:
        return fallback


@functools.lru_cache(maxsize=512)
def rewrite_query_for_retrieval(user_question: str, return_debug: bool = False):
    """사규 검색용 키워드 확장 문자열 반환.

    실패 시 원문 user_question 을 그대로 반환 (절대 raise 하지 않음).
    return_debug=True 면 (cleaned, raw_response) 튜플 반환 — admin 디버그
    패널 전용. 라이브 검색 경로(core/retriever.py)는 절대 본 인자를 넘기지 말 것.
    """
    if not user_question or not user_question.strip():
        result = user_question or ""
        return (result, "") if return_debug else result
    try:
        raw = _call_gemini_for_rewrite(user_question)
    except Exception:
        raw = ""
    cleaned = _postprocess_rewritten(raw, fallback=user_question)
    return (cleaned, raw) if return_debug else cleaned


# ── 한국어 prefix tsquery 빌더 ─────────────────────────────
# 배경: plainto_tsquery('simple', '고객이 매장에 처리하나요') 는 한국어 조사가
# 토큰에 붙은 채 들어가서 매칭률이 처참하다. 조사를 떼고 to_tsquery 용 prefix
# 형태 ("고객:* | 매장:* | 처리:*") 로 빌드하면 정확도 급상승.
_KOREAN_PARTICLES = (
    "으로부터", "에서부터", "에게서", "한테서", "이라고", "라고",
    "에서", "에게", "한테", "으로", "까지", "부터", "마다",
    "이라", "처럼", "보다", "조차", "마저",
    "이", "가", "을", "를", "은", "는", "도", "만",
    "와", "과", "의", "에", "로", "랑",
)


# 자연어 토큰 → 사규 용어. 점진적으로 추가 가능한 단순 dict.
# Gemini rewriter 가 흔들려도 작동하는 정적 안전망. compliance 도메인
# 어휘가 좁아 dict 만으로도 핵심 패턴 커버 가능.
_NEXUS_NL_TO_REGULATORY = {
    # 매장 습득물 / 유실물 도메인
    "두고": ("습득물", "유실물", "분실물", "인계", "보관"),
    "잊고": ("습득물", "유실물", "분실물"),
    "분실": ("습득물", "유실물"),
    "잃어": ("습득물", "유실물"),
    "잃어버": ("습득물", "유실물"),
    "놓고": ("습득물", "유실물"),
    # 금품 수수 / 윤리 도메인
    "선물": ("금품", "이해관계자", "클린뱅크"),
    "명절": ("금품", "이해관계자"),
    "거래처": ("이해관계자", "협력업체"),
    "접대": ("금품", "이해관계자"),
    "촌지": ("금품", "이해관계자"),
    # 정보보안 도메인
    "외부": ("반출", "송신", "정보보안"),
    "메일": ("송신", "외부반출"),
    "유출": ("정보유출", "정보보안"),
    "반출": ("정보보안", "외부반출"),
    # 안전 도메인
    "사고": ("안전사고", "재해"),
    "다친": ("산업재해", "안전"),
    "부상": ("산업재해", "안전", "초동조치", "응급조치", "병원후송"),
    # 안전 도메인 보강 (한국어 동사 어간 변형 + 구어체)
    "다쳤": ("산업재해", "안전사고", "재해", "응급조치", "초동조치", "응급조치", "병원후송", "구급", "보안실"),
    "다쳐": ("산업재해", "안전사고", "재해", "초동조치", "응급조치", "병원후송"),
    "다칠": ("산업재해", "안전사고", "초동조치", "응급조치"),
    "부상": ("산업재해", "안전사고", "초동조치", "응급조치", "병원후송"),
    "손님": ("고객",),
    "응급": ("응급조치", "안전사고", "초동조치", "병원후송", "구급", "보안실"),
    # 안전 도메인 보강 2 (낙상/추락/일반 사고)
    "넘어": ("낙상", "전도", "추락", "안전사고", "고객상해", "초동조치", "응급조치"),
    "넘어져": ("낙상", "전도", "추락", "안전사고", "고객상해", "초동조치", "응급조치", "병원후송"),
    "미끄": ("낙상", "전도", "안전사고"),
    "떨어": ("추락", "낙상", "안전사고"),
    "다쳤음": ("산업재해", "안전사고", "재해", "응급조치", "인사사고", "고객상해"),
    "안전보건": ("안전보건", "재해예방", "산업안전"),
}


def _nexus_expand_with_synonyms(tokens: list) -> list:
    """자연어 토큰에 대응하는 사규 용어를 OR 후보에 추가."""
    expanded = list(tokens)
    seen = set(tokens)
    for tok in tokens:
        for key, synonyms in _NEXUS_NL_TO_REGULATORY.items():
            if key in tok:  # 부분 매칭으로 조사 잔재까지 잡음
                for syn in synonyms:
                    if syn not in seen:
                        expanded.append(syn)
                        seen.add(syn)
    return expanded


# =====================================================================
# 사건사고 분류 Taxonomy (사규 SSGDF-A-GU-01 / -A-GU-02 에서 직접 추출)
# =====================================================================

# 일반 사건사고 보고지침: 대분류 13개 / 중분류 57개
_NEXUS_GENERAL_INCIDENT_TAXONOMY = {
    "안전관리": ("공사관리", "화재사고", "탄화사고", "소방안전", "시설안전", "작업안전", "차량사고", "재해사고"),
    "외부대응": ("언론보도", "점포집회", "수사협조", "기관점검"),
    "상품품질": ("품질기준", "유통기한", "이물질발견"),
    "물류관리": ("배송관리",),
    "자산관리": ("매장관리", "회사자산", "재고자산", "자산손괴", "자산분실"),
    "매출관리": ("비정상매출", "상품권판매", "오류발생", "지불관리"),
    "인사사고": ("직원상해", "직원질병", "고객상해", "고객질병", "취식후병증", "인사관리", "응급대응"),
    "고객관리": ("고객난동", "고객분실", "고객불만", "고객절취"),
    "거래행위": ("불공정행위", "거래관리"),
    "조직관리": ("횡령수수", "부정계산", "부정적립", "직원절취"),
    "정보보안": ("회사정보", "고객정보", "악성코드"),
    "근무기강": ("근무태만", "부당한지시", "부실보고", "사내금전거래", "성희롱", "폭언폭력", "괴롭힘"),
    "IT사고": ("온라인몰장애", "시스템장애"),
}

# 중대 사건사고 보고지침: 5개 분류
_NEXUS_SEVERE_INCIDENT_TAXONOMY = {
    "인사사고": ("사망", "중상", "성범죄", "강력범죄", "감염병"),
    "안전사고": ("식품", "식중독", "화재", "시설물붕괴", "테러"),
    "정보보안": ("개인정보유출", "회사자료유출", "해킹"),
    "대외": ("분쟁", "민원", "법규위반", "집회"),
}

# 자연어 토큰 -> [(대분류, 중분류 또는 None)] 매핑
# 키는 사용자가 자연어로 자주 쓰는 어간/단어. 부분 매칭으로 조사 잔재까지 잡음.
_NEXUS_NL_TO_INCIDENT_NODES = {
    # 인사사고 / 안전 응급 도메인
    "다쳤":   [("인사사고", "고객상해"), ("인사사고", "직원상해"), ("안전사고", None)],
    "다쳐":   [("인사사고", "고객상해"), ("인사사고", "직원상해")],
    "다칠":   [("인사사고", "고객상해")],
    "다친":   [("인사사고", "직원상해"), ("인사사고", "고객상해")],
    "부상":   [("인사사고", "직원상해"), ("인사사고", "고객상해")],
    "넘어":   [("인사사고", "고객상해"), ("안전관리", "시설안전")],
    "쓰러":   [("인사사고", None), ("안전사고", None)],
    "사망":   [("인사사고", "사망")],
    "응급":   [("인사사고", "고객상해"), ("인사사고", "직원상해")],
    "손님":   [("인사사고", "고객상해")],  # PR #94: '고객관리' false positive 제거 (고객 부상 의도는 인사사고 only)
    "병증":   [("인사사고", "고객질병"), ("인사사고", "취식후병증")],
    "아파":   [("인사사고", "직원질병"), ("인사사고", "고객질병")],
    # 인사사고 / 안전 응급 도메인 — 종결형 직접 매핑 ('응급대응' 노드 emit
    # 으로 AEO 출입통제 차별화). 기존 "다쳤" 키는 본 블록에서 override.
    # 12 키 모두 동일 값 리스트 사용.
    "넘어졌어": [("인사사고", "고객상해"), ("인사사고", "응급대응"), ("인사사고", "시설안전")],
    "넘어졌":   [("인사사고", "고객상해"), ("인사사고", "응급대응"), ("인사사고", "시설안전")],
    "넘어짐":   [("인사사고", "고객상해"), ("인사사고", "응급대응"), ("인사사고", "시설안전")],
    "넘어진":   [("인사사고", "고객상해"), ("인사사고", "응급대응"), ("인사사고", "시설안전")],
    "다쳤어요": [("인사사고", "고객상해"), ("인사사고", "응급대응"), ("인사사고", "시설안전")],
    "다쳤어":   [("인사사고", "고객상해"), ("인사사고", "응급대응"), ("인사사고", "시설안전")],
    "다쳤음":   [("인사사고", "고객상해"), ("인사사고", "응급대응"), ("인사사고", "시설안전")],
    "다쳤":     [("인사사고", "고객상해"), ("인사사고", "응급대응"), ("인사사고", "시설안전")],
    "미끄러져": [("인사사고", "고객상해"), ("인사사고", "응급대응"), ("인사사고", "시설안전")],
    "미끄러짐": [("인사사고", "고객상해"), ("인사사고", "응급대응"), ("인사사고", "시설안전")],
    "전도":     [("인사사고", "고객상해"), ("인사사고", "응급대응"), ("인사사고", "시설안전")],
    "낙상":     [("인사사고", "고객상해"), ("인사사고", "응급대응"), ("인사사고", "시설안전")],

    # 고객관리 도메인
    "두고":   [("고객관리", "고객분실")],
    "잊고":   [("고객관리", "고객분실")],
    "잃어":   [("고객관리", "고객분실")],
    "난동":   [("고객관리", "고객난동")],
    "컴플레인": [("고객관리", "고객불만")],
    "민원":   [("외부대응", None), ("고객관리", "고객불만"), ("대외", "민원")],

    # 자산관리 도메인
    "도난":   [("자산관리", "자산분실"), ("고객관리", "고객절취")],
    "분실":   [("자산관리", "자산분실"), ("고객관리", "고객분실")],
    "손괴":   [("자산관리", "자산손괴")],

    # 조직관리 / 윤리 / 금품 도메인
    "선물":   [("조직관리", "횡령수수")],
    "명절":   [("조직관리", "횡령수수")],
    "거래처": [("조직관리", "횡령수수"), ("거래행위", None)],
    "접대":   [("조직관리", "횡령수수")],
    "횡령":   [("조직관리", "횡령수수")],
    "유용":   [("조직관리", "횡령수수")],
    "절취":   [("조직관리", "직원절취"), ("고객관리", "고객절취")],

    # 정보보안 도메인
    "유출":   [("정보보안", "회사정보"), ("정보보안", "고객정보"), ("정보보안", "회사자료유출"), ("정보보안", "개인정보유출")],
    "외부":   [("정보보안", "회사정보")],
    "메일":   [("정보보안", "회사정보")],
    "반출":   [("정보보안", "회사정보")],
    "개인정보": [("정보보안", "고객정보"), ("정보보안", "개인정보유출")],
    "해킹":   [("정보보안", "해킹")],
    "악성":   [("정보보안", "악성코드")],
    "바이러스": [("정보보안", "악성코드")],

    # 근무기강 도메인
    "성희롱": [("근무기강", "성희롱")],
    "성추행": [("근무기강", "성희롱"), ("인사사고", "성범죄")],
    "폭언":   [("근무기강", "폭언폭력")],
    "폭력":   [("근무기강", "폭언폭력")],
    "괴롭":   [("근무기강", "괴롭힘")],
    "갑질":   [("근무기강", "부당한지시"), ("근무기강", "괴롭힘")],
    "결근":   [("근무기강", "근무태만")],
    "지각":   [("근무기강", "근무태만")],
    # PR-Phase-10-Fix-C: HR routing 보강 (N9 부조금 query 의 카테고리 오인식 fix).
    "부조금": [("근무기강", "복리후생")],
    "경조금": [("근무기강", "복리후생")],
    # PR-Phase-10.1-Fix-D: 외부강의/대외출강 매핑 — N6 강의료 query retrieval
    # 복구. SQL audit 결과 (CSR) 대외출강 운영 지침의 auto_keywords 에 "강사료"
    # 만 등록되어 사용자 query "강의료" 와 mismatch. + meta.incident_nodes 정정
    # (DB UPDATE 별개 작업). query_rewriter trigger 매핑 13개 추가:
    "강의료": [("거래행위", "외부강의신고")],
    "강사료": [("거래행위", "외부강의신고")],
    "강연료": [("거래행위", "외부강의신고")],
    "사례금": [("거래행위", "외부강의신고")],
    "외부 강의": [("거래행위", "외부강의신고")],
    "외부강의": [("거래행위", "외부강의신고")],
    "외부 강연": [("거래행위", "외부강의신고")],
    "대외 출강": [("거래행위", "외부강의신고")],
    "대외출강": [("거래행위", "외부강의신고")],
    "출강 신고": [("거래행위", "외부강의신고")],
    "강의 신고": [("거래행위", "외부강의신고")],
    "원고료": [("거래행위", "외부강의신고")],
    "기고료": [("거래행위", "외부강의신고")],

    # 안전관리 도메인 (사고 유형)
    "화재":   [("안전관리", "화재사고"), ("안전사고", "화재")],
    "불이":   [("안전관리", "화재사고"), ("안전사고", "화재")],
    "지진":   [("안전관리", "재해사고"), ("안전사고", None)],
    "차량":   [("안전관리", "차량사고")],

    # 상품품질 도메인
    "유통기한": [("상품품질", "유통기한")],
    "이물질": [("상품품질", "이물질발견")],
    "식중독": [("안전사고", "식중독")],

    # 대외 도메인
    "언론":   [("외부대응", "언론보도")],
    "기자":   [("외부대응", "언론보도")],
    "집회":   [("외부대응", "점포집회"), ("대외", "집회")],
    "시위":   [("외부대응", "점포집회"), ("대외", "집회")],
    "경찰":   [("외부대응", "수사협조"), ("대외", None)],
    "수사":   [("외부대응", "수사협조"), ("대외", None)],

    # IT사고 도메인
    "장애":   [("IT사고", "시스템장애"), ("IT사고", "온라인몰장애")],
    "먹통":   [("IT사고", "시스템장애")],

    # === Phase 2.1: 성희롱 ===
    "성희롱":         [("성희롱", "윤리보고")],
    "성추행":         [("성희롱", "윤리보고")],
    "성폭력":         [("성희롱", "윤리보고")],
    "성적 발언":       [("성희롱", "윤리보고")],
    "성적인 농담":      [("성희롱", "윤리보고")],
    "성희롱 당했":     [("성희롱", "윤리보고")],
    "성희롱 신고":     [("성희롱", "윤리보고")],
    # PR-Phase-13-Fix-B: 단독 명사 query 매핑 (현업 인계 핫픽스).
    # "성희롱" trigger 와 기능 중복이나 명시성 위해 추가.
    "성희롱 정의":     [("성희롱", None)],

    # === Phase 2.2: 직장 내 괴롭힘 ===
    "괴롭힘":         [("괴롭힘", "윤리보고")],
    "직장 내 괴롭힘":   [("괴롭힘", "윤리보고")],
    "폭언":           [("괴롭힘", "윤리보고")],
    "갑질":           [("괴롭힘", "윤리보고")],
    "따돌림":         [("괴롭힘", "윤리보고")],
    "왕따":           [("괴롭힘", "윤리보고")],
    "괴롭힘 당했":     [("괴롭힘", "윤리보고")],
    "상사가 괴롭":     [("괴롭힘", "윤리보고")],
    # PR-Fix-Domain-Surfacing: 운영 검증(log id=1404) 에서 "팀장이 계속
    # 막말하고 인격모독을 합니다" query 의 incident_node 분류 빈 set →
    # L1_RPC skip → (인사) 직장 내 괴롭힘 예방·대응지침 매칭 0 회귀 fix.
    # 일상어("무시","비난") 는 false positive 위험으로 제외. 명확한
    # 괴롭힘-맥락 어휘 4개만 추가.
    "막말":           [("괴롭힘", "윤리보고"), ("근무기강", "괴롭힘")],
    "인격모독":        [("괴롭힘", "윤리보고"), ("근무기강", "괴롭힘")],
    "모독":           [("괴롭힘", "윤리보고")],
    "비하":           [("괴롭힘", "윤리보고")],

    # === Phase 2.3: 정보유출 ===
    "정보유출":        [("정보유출", None)],
    "정보 유출":       [("정보유출", None)],
    # PR-Phase-13-Fix-B: 단독 명사 query 매핑 (현업 인계 핫픽스).
    "정보보호":        [("정보보안", None)],

    # === Phase 2.4: 공정거래 (PR-Phase-4 — Q10 매핑 부재 fix) ===
    # 운영 검증(Q10) 에서 "협력사 판매수수료 부당 변경" query 가 광범위
    # ["비위행위","윤리위반"] 만 추출되어 (영업) CSR경영방침 + (공통) 임직원
    # 징계기준 만 매칭, 핵심 (공정거래) 판매수수료 결정 및 변경 지침 매칭 0
    # 회귀 fix. 공정거래 전용 노드 추가로 도메인 분리.
    "판매수수료":      [("공정거래위반", "윤리보고"), ("비위행위", None)],
    "협력사":          [("공정거래위반", "윤리보고")],
    "협력회사":        [("공정거래위반", "윤리보고")],
    "거래조건":        [("공정거래위반", "윤리보고")],
    "부당한 요구":     [("공정거래위반", "윤리보고"), ("비위행위", None)],
    "거래상 지위":     [("공정거래위반", "윤리보고")],
    "표시광고":        [("공정거래위반", None)],
    "광고 표시":       [("공정거래위반", None)],
    "특약매입":        [("공정거래위반", None)],
    "판촉비":          [("공정거래위반", None)],
    "입점":            [("공정거래위반", None)],
    "퇴점":            [("공정거래위반", None)],
    "반품":            [("공정거래위반", None)],
    # PR-Phase-13-Fix-B: 단독 명사 query 매핑 (현업 인계 핫픽스).
    "공정거래":        [("공정거래위반", "윤리보고")],
    "공정거래위반":     [("공정거래위반", "윤리보고")],
    "공정거래 위반":    [("공정거래위반", "윤리보고")],

    # === Phase 2.5: 환경 (PR-Phase-4 — Q14 매핑 부재 fix) ===
    # 운영 검증(Q14) 에서 "폐기물 부적정 처리" query 가 nodes=[] → force-include
    # skip → 무관 doc (안전) 실종아동/(영업) 매장 습득물 매칭 회귀. 환경
    # 도메인 신규 노드 어휘 추가로 환경 query 정확 매칭.
    "폐기물":          [("환경관리", "환경법규")],
    "폐기물 처리":     [("환경관리", "환경법규")],
    "폐기물처리":      [("환경관리", "환경법규")],
    "환경법규":        [("환경법규", None)],
    "환경 법규":       [("환경법규", None)],
    "환경경영":        [("환경관리", None)],
    "환경 사고":       [("환경관리", "사건사고보고")],
    "오염":            [("환경관리", "환경법규")],
    "유해물질":        [("환경관리", "환경법규")],
    "화학물질":        [("환경관리", "환경법규")],
    "ISO 14001":      [("환경관리", None)],

    # === Phase 2.6: 정보보안 단독 키워드 (PR-Phase-4 — Q15 fix) ===
    # 운영 검증(Q15) 에서 "정보보안 사고 발생 시 어떻게 보고" query 가
    # 사건사고 보고 절차 도메인으로만 분류되어 (정보보안) 사규 매칭 0.
    # "정보보안" 단독 키워드를 정보보안 도메인 trigger 로 명시.
    "정보보안":        [("정보보안", None)],
    "정보보안 사고":   [("정보보안", "사건사고보고")],
    "보안사고":        [("정보보안", "사건사고보고")],
    "보안 사고":       [("정보보안", "사건사고보고")],
    "보안 위반":       [("정보보안", "비위행위")],
    "보안위반":        [("정보보안", "비위행위")],
    "개인정보":        [("정보유출", None)],
    "개인정보 유출":    [("정보유출", None)],
    "고객정보":        [("정보유출", None)],
    "고객정보 유출":    [("정보유출", None)],
    "자료 유출":       [("정보유출", None)],
    "기밀 유출":       [("정보유출", None)],
    "외부 유출":       [("정보유출", None)],
    "데이터 유출":     [("정보유출", None)],
    "문서 유출":       [("정보유출", None)],
    "파일 유출":       [("정보유출", None)],
    "USB로 가져갔":   [("정보유출", None)],
    "이메일로 보냈":   [("정보유출", None)],

    # === Phase 2.4: 근로자안전 (직원 부상/사망) ===
    "직원이 다쳤":     [("근로자안전", "인사사고")],
    "직원 다쳤":       [("근로자안전", "인사사고")],
    "직원 부상":       [("근로자안전", "인사사고")],
    "직원 상해":       [("근로자안전", "인사사고")],
    "근로자 다쳤":     [("근로자안전", "인사사고")],
    "작업 중 다쳤":    [("근로자안전", "인사사고")],
    "일하다 다쳤":     [("근로자안전", "인사사고")],
    "안전사고":        [("근로자안전", "인사사고"), ("안전점검", None)],
    "산업재해":        [("근로자안전", "인사사고")],
    "중대재해":        [("근로자안전", "인사사고"), ("응급대응", None)],
    "사망사고":        [("근로자안전", "인사사고"), ("응급대응", None)],
    "사망":           [("근로자안전", "인사사고"), ("응급대응", None)],

    # === Phase 2.5: 매장사고 비고객 (화재/정전/실종 등) ===
    "매장 화재":       [("매장사고", "응급대응")],
    "화재":           [("매장사고", "응급대응")],
    "불났":           [("매장사고", "응급대응")],
    "정전":           [("매장사고", "응급대응")],
    "단수":           [("매장사고", "응급대응")],
    "매장 사고":       [("매장사고", "사건사고보고")],
    "실종 아동":       [("응급대응", "매장사고")],
    "아이 잃어버렸":   [("응급대응", "매장사고")],
    "미아":           [("응급대응", "매장사고")],
    "어린이 다쳤":     [("고객상해", "매장사고")],
    "아이가 다쳤":     [("고객상해", "매장사고")],
    "비상상황":        [("응급대응", "사건사고보고")],

    # === Hotfix: 횡령/배임/금전사고 (실 사용자 query 발견) ===
    "횡령":           [("횡령", "배임"), ("금전사고", "비위행위"), ("윤리보고", None)],
    "배임":           [("횡령", "배임"), ("금전사고", "비위행위"), ("윤리보고", None)],
    "절도":           [("횡령", "절도"), ("금전사고", "비위행위")],
    "훔치":           [("횡령", "절도"), ("금전사고", "비위행위")],
    "훔침":           [("횡령", "절도"), ("금전사고", "비위행위")],
    "훔쳤":           [("횡령", "절도"), ("금전사고", "비위행위")],
    "훔쳐":           [("횡령", "절도"), ("금전사고", "비위행위")],
    "비위":           [("횡령", "배임"), ("비위행위", "윤리보고")],
    "부정사용":        [("횡령", "배임"), ("비위행위", None)],
    "부정 사용":       [("횡령", "배임"), ("비위행위", None)],
    "회사 돈":         [("횡령", "금전사고"), ("비위행위", None)],
    "회사 자금":       [("횡령", "배임"), ("금전사고", "비위행위")],
    "회사 돈을 훔":    [("횡령", "절도"), ("금전사고", "비위행위")],
    "자금 유용":       [("횡령", "배임"), ("금전사고", None)],
    "공금":           [("횡령", "금전사고")],
    "공금 횡령":       [("횡령", "배임"), ("금전사고", "비위행위")],
    "뇌물":           [("뇌물", "비위행위"), ("윤리위반", None)],
    "부정청탁":        [("뇌물", "비위행위"), ("윤리위반", None)],
    "리베이트":        [("뇌물", "비위행위"), ("윤리위반", None)],

    # === PR-Fix-Keyword-Mapping: CREDO + 협력회사 + 처벌 도메인 키워드 보강 ===
    # 매핑 노드는 DB SQL 결과의 실제 doc.meta.incident_nodes 와 정렬:
    #   - "윤리보고" → CREDO (윤리보고), 임직원 징계기준, 클린뱅크
    #   - "윤리위반" → 임직원 징계기준, 클린뱅크, 부당한 경영활동 지침
    #   - "비위행위" → 임직원 징계기준, 클린뱅크
    # 기존 사용 노드만 사용 (새 노드 추가 X, taxonomy 영향 0).
    # DB meta 무변경 (Phase A 회귀 패턴 차단).

    # #5 CREDO 직접 질문 — CREDO chunks force-include 위한 매핑
    "CREDO":          [("윤리보고", None), ("윤리위반", None)],
    "크레도":          [("윤리보고", None), ("윤리위반", None)],
    "강령":           [("윤리보고", None), ("윤리위반", None)],
    "행동강령":        [("윤리보고", None), ("윤리위반", None)],
    "핵심가치":        [("윤리보고", None), ("윤리위반", None)],
    "핵심 가치":       [("윤리보고", None), ("윤리위반", None)],
    "윤리경영":        [("윤리보고", None), ("윤리위반", None)],

    # #4 협력회사 부당 비용 — 임직원 징계기준 + 부당한 경영활동 지침 force-include
    "협력회사":        [("비위행위", None), ("윤리위반", None)],
    "부당 비용":       [("비위행위", None), ("윤리위반", None)],
    "비용 요구":       [("비위행위", None), ("윤리위반", None)],
    "부당하게":        [("비위행위", None), ("윤리위반", None)],

    # #4 보조 — 처벌·징계 질문에 임직원 징계기준 매칭 강화
    "처벌":           [("윤리위반", None)],
    "징계 수위":       [("윤리위반", None)],

    # === PR-Fix-ForceInclude-Domain-Expand: 환경/총무 도메인 trigger 보강 ===
    # (환경) 도메인 docs (비상시대비대응 / 환경 사건·시정조치 / 환경경영매뉴얼)
    # 와 (총무) 도메인 docs (인감 관리지침) force_include 작동 위해 trigger
    # 노드 매핑 추가. INCIDENT_NODE_TO_DOMAIN 의 environment/total_affairs
    # 매핑과 L3_FALLBACK_BY_DOMAIN whitelist 와 동시 작동.
    "환경 사고":       [("환경사고", None)],
    "환경 사건":       [("환경사고", None)],
    "환경 위반":       [("환경위반", None)],
    "환경경영":        [("환경경영", None)],
    "환경 리스크":     [("환경경영", None)],
    "비상시":          [("비상시대비", None)],
    "인감":            [("인감관리", None)],
    "인장":            [("인감관리", None)],
    "도장":            [("인감관리", None)],
}


def _nexus_expand_with_incident_taxonomy(tokens: list) -> list:
    """
    NL 토큰을 사규 taxonomy 노드명으로 확장.
    반환: 추가할 분류명(대분류 + 중분류)의 중복 제거된 리스트.
    """
    extra = []
    seen = set()
    if not tokens:
        return extra
    for tok in tokens:
        for trigger, node_list in _NEXUS_NL_TO_INCIDENT_NODES.items():
            if trigger in tok:
                for level1, level2 in node_list:
                    if level1 and level1 not in seen:
                        extra.append(level1)
                        seen.add(level1)
                    if level2 and level2 not in seen:
                        extra.append(level2)
                        seen.add(level2)
    return extra


def nexus_classify_to_incident_nodes(text: str) -> list[str]:
    """사용자 입력 text 에서 incident 노드 추출.

    `_NEXUS_NL_TO_INCIDENT_NODES` 를 사용해 트리거 토큰이 등장하면 해당
    노드들을 수집. retrieval boost rerank 에서
    `document.meta.incident_nodes` 와 교집합 계산용.

    Returns: 정렬된 노드 리스트 (예: ['고객상해', '매장사고']).
    """
    if not text:
        return []
    nodes: set[str] = set()
    for trigger, node_list in _NEXUS_NL_TO_INCIDENT_NODES.items():
        if trigger in text:
            for level1, level2 in node_list:
                if level1:
                    nodes.add(level1)
                if level2:
                    nodes.add(level2)
    return sorted(nodes)


def nexus_build_keyword_tsquery(text: str, original: str | None = None) -> str:
    """자연어/재작성 쿼리를 prefix tsquery 문자열로 변환.

    예: '고객이 매장에 처리하나요' -> '고객:* | 매장:* | 처리:*'

    original: 사용자 원문(rewritten 적용 전). 전달 시 원문 토큰도 같이
    dict 매핑에 노출되어, Gemini rewriter 가 운영 동사("넘어졌어"/"다쳤")
    를 abstract 키워드로 치환해도 dict expansion 이 트리거된다.
    None 이면 기존 동작 (text 만 사용) — 100% 후방 호환.
    """
    if not text:
        return ""
    tokens = re.findall(r"[가-힣A-Za-z0-9]+", text)
    cleaned: list[str] = []
    for tok in tokens:
        for p in _KOREAN_PARTICLES:
            if tok.endswith(p) and len(tok) > len(p) + 1:
                tok = tok[: -len(p)]
                break
        if len(tok) >= 2:
            cleaned.append(tok)
    if original:
        # 원본 자연어의 토큰도 같이 dict 매핑에 노출
        original_tokens = re.findall(r"[가-힣A-Za-z0-9]+", original)
        for tok in original_tokens:
            for p in _KOREAN_PARTICLES:
                if tok.endswith(p) and len(tok) > len(p) + 1:
                    tok = tok[: -len(p)]
                    break
            if len(tok) >= 2:
                cleaned.append(tok)
    seen: set[str] = set()
    uniq: list[str] = []
    for t in cleaned:
        if t not in seen:
            seen.add(t)
            uniq.append(t)
    uniq = _nexus_expand_with_synonyms(uniq)
    uniq = uniq + _nexus_expand_with_incident_taxonomy(uniq)
    return " | ".join(f"{t}:*" for t in uniq)


def nexus_build_pgroonga_query(text: str, original: str | None = None) -> str:
    """자연어/재작성 쿼리를 pgroonga &@~ 호환 OR query 로 변환.
    예: '고객이 매장에 처리하나요' -> '고객 OR 매장 OR 처리'
    pgroonga 의 &@~ 연산자는 띄어쓰기를 AND 로 해석하므로 명시적 OR
    키워드 필요. 띄어쓰기 default 와 `||` 는 0건 매칭됨이 SQL 검증으로
    확정 (2026-05-13). 같은 동의어 확장/incident taxonomy 적용 —
    tsquery 빌더와 동일 토큰 풀.
    original: 사용자 원문(rewritten 적용 전). 전달 시 원문 토큰도 dict
    매핑에 노출되어, rewriter 가 동사("넘어졌어"/"다쳤")를 abstract
    키워드로 치환해도 dict expansion 이 트리거된다.
    """
    if not text:
        return ""
    tokens = re.findall(r"[가-힣A-Za-z0-9]+", text)
    cleaned: list[str] = []
    for tok in tokens:
        for p in _KOREAN_PARTICLES:
            if tok.endswith(p) and len(tok) > len(p) + 1:
                tok = tok[: -len(p)]
                break
        if len(tok) >= 2:
            cleaned.append(tok)
    if original:
        original_tokens = re.findall(r"[가-힣A-Za-z0-9]+", original)
        for tok in original_tokens:
            for p in _KOREAN_PARTICLES:
                if tok.endswith(p) and len(tok) > len(p) + 1:
                    tok = tok[: -len(p)]
                    break
            if len(tok) >= 2:
                cleaned.append(tok)
    seen: set[str] = set()
    uniq: list[str] = []
    for t in cleaned:
        if t not in seen:
            seen.add(t)
            uniq.append(t)
    uniq = _nexus_expand_with_synonyms(uniq)
    uniq = uniq + _nexus_expand_with_incident_taxonomy(uniq)
    # pgroonga &@~ 형식 — 명시적 OR. 띄어쓰기 default 는 AND 로 해석되어 recall 처참.
    return " OR ".join(uniq)
