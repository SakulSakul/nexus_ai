"""챗봇 엔진 — 검색→Gemini 생성→후처리(출처/심각모드)→로깅.

운영 시점 최신 안정 모델은 NEXUS_CHAT_MODEL 환경변수로 추상화한다.
temperature/top_p 는 환각 제어를 위해 0/0.1 고정이 기본값이며,
필요한 경우에만 환경변수로 미세조정한다.
"""

from __future__ import annotations

import os
import re
import sys
import time
from contextvars import ContextVar
from collections import Counter, OrderedDict
from dataclasses import dataclass, field
from typing import Any, Callable, Iterator, Optional

from .config import settings, load_hotlines
from .critical_mode import CriticalDetection, detect, enforce_structure, load_keywords
from .pii_filter import mask_pii
from .prompts import SYSTEM_PROMPT, build_user_prompt
from .multi_facet import detect_multi_facet  # PR-MultiFacet shadow gate
from .retriever import _chunk_domain, hybrid_search
from .disambiguation import detect_ambiguity, format_choice_suggestion
from .query_classifier import classify_query, ENABLE_QUERY_CLASSIFIER_LOGGING
from .faq_cache import faq_cache_get, ENABLE_FAST_PATH
from .answer_guard import SAFE_NO_CONTEXT, SAFE_EMPTY_COMPLETION, EmptyCompletionError
from .config import get_secret as _ncg_get_secret
ENABLE_NO_CONTEXT_GATE = (_ncg_get_secret("ENABLE_NO_CONTEXT_GATE", "false") or "false").lower() == "true"
ENABLE_OOS_RELEVANCE_GATE = (_ncg_get_secret("ENABLE_OOS_RELEVANCE_GATE", "false") or "false").lower() == "true"
from .ambiguity import detect_bare_ambiguity, ENABLE_AMBIGUITY_ASKBACK
from .oos_router import ENABLE_OOS_ROUTING
from .grounded_suggestions import ENABLE_GROUNDED_SUGGESTIONS, grounded_suggestions


# ── Eval Mode: 모델 override (PR-Model-Self-Test) ──────────────
# 모델 테스트 탭에서 회차 실행 시 운영 chat_model 대신 평가 대상
# 모델로 강제 호출. ContextVar 로 thread-safe 격리 — run_review 가
# set/reset 토큰을 관리하며 단일 회차 스코프에서만 활성.
# None 이면 기존 운영 경로 (s.chat_model / fallback chain) 유지.
_EVAL_MODEL_ID: ContextVar[Optional[str]] = ContextVar(
    "eval_model_id", default=None,
)


def _resolve_eval_model(expected_provider: str) -> Optional[str]:
    """eval override 값이 expected_provider 와 매치되면 model_id 반환.
    매치 안 되거나 override 없으면 None — 운영 모델 사용.
    gemini-* → gemini, claude-* → claude 로 prefix 매칭."""
    mid = _EVAL_MODEL_ID.get()
    if not mid:
        return None
    if expected_provider == "gemini" and mid.startswith("gemini-"):
        return mid
    if expected_provider == "claude" and mid.startswith("claude-"):
        return mid
    return None


def _resolve_eval_provider() -> Optional[str]:
    """eval override 가 있으면 추론된 provider, 없으면 None."""
    mid = _EVAL_MODEL_ID.get()
    if not mid:
        return None
    if mid.startswith("gemini-"):
        return "gemini"
    if mid.startswith("claude-"):
        return "claude"
    return None


# SYSTEM_PROMPT 가 강제하는 [검색 과정] 섹션 마커. LLM 응답에서 본문과
# 검토 과정을 분리하는 anchor. 마커 없으면 process 는 빈 문자열로 간주
# 하고 사용자 화면에서 expander 자체를 숨긴다 (마커 누락 fallback).
SEARCH_PROCESS_MARKER = "[검색 과정]"
# PR-Fun1 작업 3: 답변 본문 뒤에 LLM 이 출력하는 후속 질문 카드 마커.
# 사용자 화면에 raw 노출되면 안 되므로 stream filter 와 본문 split 단계에서
# 분리된다. 사규 본문에 우연히 등장할 가능성 0 (회사 사규에 영문 대문자
# 마커 없음). Critical Mode 답변 가이드 7번에 의해 critical 답변에서는
# LLM 이 본 블록 자체를 출력하지 않도록 지시되어 있다.
SUGGESTIONS_MARKER = "[SUGGESTIONS]"
SUGGESTIONS_END_MARKER = "[/SUGGESTIONS]"


# ── 카테고리 자동 추론 ──────────────────────────────────────────
# 사용자 질의에서 도메인 키워드를 매칭해 hybrid_search 의 카테고리
# 필터로 사용. 명시 카테고리 인자(ask 의 category) 가 있으면 그것을
# 우선하고, 추론 실패(None) 시 전체 검색(기존 동작) 으로 fallback.
# Phase 4 운영 데이터로 키워드 정밀화 예정.
CATEGORY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "인사": (
        "성희롱", "괴롭힘", "갑질", "징계기준",
        "인수인계", "동호회", "자율준수", "조직문화",
        "근태", "휴가", "퇴사", "인사평가",
    ),
    "공통": (
        "CREDO", "크레도", "핵심가치", "신세계그룹",
        "사건사고", "민감정보", "기부금", "사규관리",
        "임직원 징계", "윤리", "행동강령",
    ),
    "CSR": (
        "클린뱅크", "강사료", "선물", "수수", "상품권",
        "대외출강", "외부강연", "외부 강의",
    ),
    "공정거래": (
        "반품", "입점", "퇴점", "판촉", "표시광고",
        "협력회사", "경영정보", "비용전가", "할인광고",
        "SNS 인플루언서",
    ),
    "정보보안": (
        "정보보안", "정보보호", "개발보안", "운영보안",
        "생활보안", "보안 정책",
    ),
    "안전": (
        "중대재해", "재해", "응급", "응급조치", "화재",
        "추락", "쓰러진", "의식을 잃은", "실종아동",
        "어린이 안전", "공기질", "위험성평가", "휴게시설",
        "전기기계", "안전보건", "비상시", "비상시대비",
    ),
    "재무": (
        "회계", "재무", "예산", "출장비", "교통비", "택시", "택시비", "시내교통",
        "법인카드", "지출", "결제", "지불", "미수금",
        "내부회계", "전결", "제3채무", "자산 실사",
        "상품반출입", "상품재고", "매출금", "출납",
    ),
    "총무": (
        "인감", "구매", "인테리어", "이사회",
        "영상정보기기", "CCTV",
    ),
    "영업": (
        "AEO", "보세화물", "출입통제", "거래업체",
        "매장 습득물", "물류 안전",
    ),
    "환경": (
        "환경", "녹색 구매", "환경경영", "환경영향평가",
        "환경 리스크", "환경운영", "환경 사건",
    ),
}


def _shadow_log_multi_facet(contexts: list, tag: str = "balanced") -> None:
    """PR-MultiFacet-Shadow: 게이트 판정 로그만 (행동 변화 없음)."""
    import sys
    try:
        _mf = detect_multi_facet(contexts)
        print(
            f"[multi_facet:shadow:{tag}] is_mf={_mf.is_multi_facet} "
            f"domains={_mf.distinct_domains} dominant={_mf.dominant_category} "
            f"facets={[f.category for f in _mf.facets]}",
            file=sys.stderr, flush=True,
        )
    except Exception as _e:
        print(f"[multi_facet:shadow] err={_e}", file=sys.stderr, flush=True)


def infer_categories(question: str, max_cats: int = 3) -> list[str] | None:
    """질의에서 카테고리 자동 추론. hit 점수 합계 내림차순 상위 max_cats.

    매칭 키워드가 하나도 없으면 None — 호출자는 기존 전체 검색 fallback.
    회귀 안전: 명시 인자 우선, 추론 실패 시 기존 동작 유지.
    """
    if not question or not question.strip():
        return None
    # PR-19.x 사내 동의어 인지 — 매칭 전 단일 출처(_NEXUS_NL_TO_REGULATORY)로
    # question 을 확장한 사본(_match_text)으로 카테고리 매칭. 원문 보존(표시/로그
    # 영향 0). 협력사원=파견사원=판촉사원 등 synonym 클래스를 한 길목에서 정렬.
    _match_text = question
    try:
        from .nexus_query_rewriter import _NEXUS_NL_TO_REGULATORY
        _extra: list[str] = []
        for _k, _syns in _NEXUS_NL_TO_REGULATORY.items():
            if _k in question:
                _extra.extend(_syns)
        if _extra:
            _match_text = question + " " + " ".join(dict.fromkeys(_extra))
    except Exception:
        _match_text = question  # 회귀 안전 — 실패 시 원문
    hits: dict[str, int] = {}
    for cat, kws in CATEGORY_KEYWORDS.items():
        for kw in kws:
            if kw in _match_text:
                hits[cat] = hits.get(cat, 0) + 1
    if not hits:
        return None
    sorted_cats = sorted(hits.items(), key=lambda x: x[1], reverse=True)
    return [c for c, _ in sorted_cats[:max_cats]]


def _split_answer_and_process(raw: str) -> tuple[str, str]:
    """LLM 응답에서 [검색 과정] 섹션 분리.

    마커 없으면 process 는 빈 문자열 → 사용자 화면 expander 자동 숨김.
    """
    if SEARCH_PROCESS_MARKER not in raw:
        return raw.strip(), ""
    head, tail = raw.split(SEARCH_PROCESS_MARKER, 1)
    return head.rstrip(), tail.strip()


def _split_suggestions(answer: str) -> tuple[str, list[str]]:
    """답변 본문에서 [SUGGESTIONS] 블록 분리 (PR-Fun1 작업 3).

    - 마커 [SUGGESTIONS] ... [/SUGGESTIONS] 안의 "- " bullet 한 줄씩 추출.
    - 본문에서는 블록 통째로 제거 후 trailing 공백 정리.
    - 마커 없으면 (answer, []) 반환.
    - 끝 마커 없이 시작 마커만 있으면 본문 끝까지가 블록 — robust 처리.
    - critical 답변은 prompts.py 에 의해 본 블록 자체가 안 생성됨 — 다만
      LLM 이 일관성 깨고 출력하더라도 본 함수가 본문에서 잘라내므로 사용자
      화면에 raw 노출되는 사고는 차단 (이중 방어). UI 단의 ans.is_critical
      분기는 카드 비활성으로 추가 방어.
    """
    if SUGGESTIONS_MARKER not in answer:
        return answer, []
    head, tail = answer.split(SUGGESTIONS_MARKER, 1)
    if SUGGESTIONS_END_MARKER in tail:
        block, _ = tail.split(SUGGESTIONS_END_MARKER, 1)
    else:
        block = tail
    # bullet 추출 — "- ", "* ", "1. " 형식 모두 허용. 한 줄 내 trim.
    items: list[str] = []
    for line in block.splitlines():
        s = line.strip()
        if not s:
            continue
        # leading bullet 마커 제거
        for prefix in ("- ", "* ", "• "):
            if s.startswith(prefix):
                s = s[len(prefix):].strip()
                break
        else:
            # "1. ", "2. " 같은 numbered list
            m = re.match(r"^\d+[\.\)]\s*(.+)$", s)
            if m:
                s = m.group(1).strip()
            else:
                # bullet 없는 평문 — fallback 으로 그대로 추가
                pass
        if s:
            items.append(s)
    # 최대 3개 cap (prompts.py 가 3개 명시 — LLM 변형 안전망)
    return head.rstrip(), items[:3]


# [검색 과정] 4단계(①②③④) 헤더 정형화 패턴.
# - leading \s* : 직전 본문의 trailing 공백/개행을 흡수해 단락 사이가
#   '본문 \n\n**②' 가 아닌 '본문\n\n**②' 로 깔끔히 분리되게 한다.
# - 캡처1: ①②③④ 마커
# - 캡처2: 마커 뒤부터 콜론 직전까지 (lazy 매칭, 단계명. 줄바꿈/콜론 제외)
# 본문에 콜론이 있어도 lazy 매칭이라 첫 콜론에서 끊겨 헤더만 정확히 변환.
_PROCESS_STEP_PATTERN = re.compile(r"\s*([①②③④])\s*([^:\n]+?)\s*:\s*")


def _format_process_section(process: str) -> str:
    """① ② ③ ④ 4단계를 '**마커 단계명**\\n\\n본문' 형식으로 변환.

    LLM 이 한 줄로 이어 쓰거나 헤더 강조 없이 출력하는 경우의 안전망.
    answer_text 는 이 함수를 거치지 않으므로 본문에 마커가 우연히 등장
    해도 변형되지 않는다.
    """
    if not process:
        return process
    formatted = _PROCESS_STEP_PATTERN.sub(r"\n\n**\1 \2**\n\n", process)
    return formatted.strip()


# 권장 행동 섹션 헤더 (시스템 프롬프트가 강제하는 출력 구조 ③) 의 markdown
# 패턴. 답변 내 일반 numbered list (예: 사규 인용 '1. 정의 2. 적용범위') 가
# 권장 행동으로 잘못 추출되지 않도록 섹션 본문에서만 추출.
# 종료는 다음 섹션(④/출처/역질문/[참조/---) 또는 문서 끝(\Z). re.M 의 $ 는
# line-end 라 lookahead 가 0자 body 로 끝나는 결함 → \Z 로 대체.
_RE_ACTION_SECTION = re.compile(
    r"(?:^|\n)\s*(?:③|##?#?\s*권장\s*행동|\*\*?권장\s*행동\*\*?|3\.\s*즉시\s*실행)"
    r"([\s\S]*?)(?=\n\s*(?:④|##?#?\s*출처|##?#?\s*역질문|\[참조|---)|\Z)",
)
_RE_ACTION_BLOCK = re.compile(r"(?:^|\n)\s*\d+\.\s+(.+)")

# Prompt injection 1차 필터 — LLM 호출 전에 명백한 공격 패턴을 차단.
# 매치되면 LLM 을 호출하지 않고 정중한 거절을 즉시 반환.
# 규칙: '이전/위 + 지시/명령' 같은 정상 비즈니스 단어 조합은 false-positive
# 가 너무 많아서, 반드시 'cancel verb (무시/잊/덮어/ignore/override)' 까지
# 동반된 경우만 차단.
_INJECTION_PATTERNS = (
    # KO: '이전/위/기존/모든 ... 지시/명령/규칙/프롬프트 ... 무시/잊/덮어/취소'
    re.compile(
        r"(?:이전|위|기존|모든|앞)\s*[가-힣\s]{0,8}"
        r"(?:지시|명령|규칙|프롬프트|prompt|instruction)[가-힣을를\s]{0,8}"
        r"(?:무시|잊어|잊고|버려|덮어|취소|reset)",
        re.I,
    ),
    # EN: 'ignore previous instruction' style
    re.compile(
        r"(?:ignore|disregard|forget|override)\s+(?:all\s+)?(?:previous|above|prior|earlier)\s+"
        r"(?:instruction|prompt|rule|message|context)s?",
        re.I,
    ),
    # System prompt 출력 요구
    re.compile(
        r"(?:system\s*prompt|시스템\s*프롬프트)\s*(?:을|를)?\s*"
        r"(?:출력|보여|공개|reveal|show|print|leak|덤프|dump)",
        re.I,
    ),
    # 역할 변경 + LLM 어휘 동반
    re.compile(
        r"역할\s*을?\s*(?:바꾸|변경|전환).*(?:AI|GPT|Claude|Gemini|어시스턴트|assistant)",
        re.I,
    ),
    # admin/dev 모드 활성화
    re.compile(
        r"(?:관리자|admin|developer)\s*(?:모드|mode)\s*(?:로|을|를)?\s*"
        r"(?:전환|진입|enable|activate)",
        re.I,
    ),
    # jailbreak slang
    re.compile(r"jailbreak|DAN\s+mode|do\s+anything\s+now", re.I),
)


def _looks_like_injection(text: str) -> bool:
    """명백한 prompt injection 시그니처 감지. 보수적으로 운영(false-positive
    회피) — 진짜 사규 질문에 'jailbreak' 키워드 들어갈 일은 거의 없음."""
    if not text:
        return False
    return any(p.search(text) for p in _INJECTION_PATTERNS)


# ── PR-Beta-Hotfix-1: query_logs INSERT 진단 로깅 ───────────
# 기존 try/except 가 `print(f"[query_logs INSERT failed] {_e}")` 로 짧게만
# 출력해 Streamlit Cloud Logs 에서 진짜 원인 파악이 어려웠다. 본 헬퍼는:
#   · 실패 시: exception type + PostgREST 상세 (message/code/details/hint/
#     status_code) + payload 컬럼 list 까지 한 줄로 stderr 출력.
#   · 성공 시: row id + 컬럼 수 stderr 출력 (volume 낮음, 정상 흐름 확인).
#
# prefix `[QUERY_LOGS INSERT FAIL]` / `[QUERY_LOGS INSERT OK]` 는 Streamlit
# Cloud Logs 탭에서 grep 으로 즉시 추출 가능하도록 고정 토큰. 이 모듈에서만
# 사용되는 진단 헬퍼라 underscore prefix 로 보호 (식별자 무수정 가드 준수).

_QUERY_LOG_FAIL_PREFIX = "[QUERY_LOGS INSERT FAIL]"
_QUERY_LOG_OK_PREFIX = "[QUERY_LOGS INSERT OK]"
_QUERY_LOG_ROLE_DIAG_PREFIX = "[QUERY_LOGS ROLE_DIAG]"

# PR-Beta-Hotfix-2: role 진단 1회 caching. 같은 process 내 첫 INSERT
# 실패 시점에만 nexus_diagnose_role RPC 호출 → stderr dump. 이후 호출은
# skip (volume 보호 + Streamlit Cloud Logs 가독성). 프로세스 재시작 시
# (Streamlit Reboot 등) 다시 활성.
_ROLE_DIAGNOSTIC_LOGGED = False


def _log_role_diagnostic_once(supabase: Any) -> None:
    """첫 호출 시점에 nexus_diagnose_role RPC 호출 → 현재 connection 의
    role 정보를 stderr 출력 (PR-Beta-Hotfix-2).

    반환 컬럼: curr_user / curr_role / sess_user / curr_schema / curr_database.
    INSERT 가 'permission denied for table' (42501) 로 실패할 때 실제로
    PostgREST 가 어떤 role 로 connect 했는지 즉시 확인 가능.

    - 함수 미존재 (db/16 미적용) 시: RPC 호출이 실패 → 별도 prefix 로 기록.
    - 1회만 실행 — module-level flag 로 dedup. 같은 프로세스 내 반복 INSERT
      실패가 나도 진단은 한 번만 (volume 폭증 차단).
    """
    global _ROLE_DIAGNOSTIC_LOGGED
    if _ROLE_DIAGNOSTIC_LOGGED:
        return
    _ROLE_DIAGNOSTIC_LOGGED = True
    import sys
    if supabase is None:
        print(f"{_QUERY_LOG_ROLE_DIAG_PREFIX} skipped (supabase=None)",
              file=sys.stderr, flush=True)
        return
    try:
        res = supabase.rpc("nexus_diagnose_role", {}).execute()
        info = res.data if res and res.data else "(no data)"
        print(f"{_QUERY_LOG_ROLE_DIAG_PREFIX} {info}",
              file=sys.stderr, flush=True)
    except Exception as _e:
        print(
            f"{_QUERY_LOG_ROLE_DIAG_PREFIX} FAIL  type={type(_e).__name__}  "
            f"msg={_e}  hint=db/16 마이그레이션 미적용 가능 — "
            f"nexus_diagnose_role 함수 부재",
            file=sys.stderr, flush=True,
        )


def _log_query_logs_insert_failure(
    payload_keys: list[str],
    err: Exception,
    supabase: Any | None = None,
) -> None:
    """query_logs INSERT 실패 시 max-verbose stderr 출력 (PR-Beta-Hotfix-1).

    payload_keys: payload dict 의 key list. 컬럼 mismatch 진단용.
    err: 발생한 예외. PostgREST APIError 의 경우 .message/.code/.details/
         .hint/.status_code 속성을 추가 노출.
    supabase: PR-Beta-Hotfix-2 — first-failure role diagnostic 호출용.
              생략 시 role diag skip (회귀 안전).
    """
    import sys
    parts = [
        f"{_QUERY_LOG_FAIL_PREFIX}",
        f"type={type(err).__name__}",
        f"msg={err}",
    ]
    for attr in ("message", "code", "details", "hint", "status_code"):
        val = getattr(err, attr, None)
        if val is not None and val != "":
            parts.append(f"{attr}={val}")
    parts.append(f"payload_columns={payload_keys}")
    print("  ".join(parts), file=sys.stderr, flush=True)
    # 첫 실패 시점에 role 진단 1회 dump — 같은 process 내 dedup.
    _log_role_diagnostic_once(supabase)


def _log_query_logs_insert_success(
    row_id: int | None,
    payload_keys: list[str],
    supabase: Any | None = None,
) -> None:
    """query_logs INSERT 성공 시 row id + 컬럼 수 stderr 출력. 정상 흐름
    가시화로 미래 silent fail 즉시 감지 (last_ts gap 으로 추론 안 해도 됨).

    PR-Beta-Hotfix-4: supabase optional 인자 + 첫 호출 시 role 진단 1회.
    실패 path 와 동일하게 [QUERY_LOGS ROLE_DIAG] 노출 → 성공 시에도 어떤
    role 로 INSERT 됐는지 즉시 확인 가능.
    """
    import sys
    print(
        f"{_QUERY_LOG_OK_PREFIX}  id={row_id}  cols={len(payload_keys)}",
        file=sys.stderr, flush=True,
    )
    # 같은 process 내 1회만 dump — 이미 logged 면 skip (failure path 와
    # 동일 _ROLE_DIAGNOSTIC_LOGGED guard 공유).
    _log_role_diagnostic_once(supabase)


def _log_faq_cache_hit(
    supabase: Any, *, masked: str, category: str | None, s: Any,
    elapsed_ms: int = 0,
) -> int | None:
    """PR-Phase-18.2: Fast Path cache hit 을 query_logs 에 경량 기록.

    chat_provider="faq_cache" / elapsed_ms = ask 진입부터 cache hit 반환 직전
    까지의 실측(Option B, PR-Phase-18.3.1) 으로 표시해 hit rate·👍/👎 피드백
    과 사용자 체감 latency 를 진실하게 기록한다. 실패해도 응답 흐름 불변
    (try/except 흡수). 반환: query_logs.id 또는 None (피드백 update 용).
    """
    _payload = {
        "category":            category if category and category != "전체" else None,
        "query_masked":        masked,
        "is_critical":         False,
        "critical_kind":       None,
        "hit_chunk_ids":       [],
        "hit_categories":      [],
        "env":                 s.env_tag,
        "embed_model_version": s.embed_model,
        "chat_provider":       "faq_cache",
        "chat_model_version":  None,
        "elapsed_ms":          elapsed_ms,
        "used_fallback":       False,
    }
    try:
        ins = supabase.table("query_logs").insert(_payload).execute()
        _qid = ins.data[0].get("id") if ins.data else None
        _log_query_logs_insert_success(_qid, list(_payload.keys()), supabase=supabase)
        return _qid
    except Exception as _e:
        _log_query_logs_insert_failure(list(_payload.keys()), _e, supabase=supabase)
        return None


def _log_ambiguity_askback(
    supabase: Any, *, masked: str, category: str | None, s: Any,
    elapsed_ms: int = 0,
) -> int | None:
    """PR-Ambiguity-Askback: 모호 bare 토큰 역질문 short-circuit 을 query_logs
    에 경량 기록. chat_provider="ambiguity_askback" 로 라우팅 비율·빈도를
    Dashboard 에서 가시화. 실패해도 응답 흐름 불변 (try/except 흡수).
    """
    _payload = {
        "category":            category if category and category != "전체" else None,
        "query_masked":        masked,
        "is_critical":         False,
        "critical_kind":       None,
        "hit_chunk_ids":       [],
        "hit_categories":      [],
        "env":                 s.env_tag,
        "embed_model_version": s.embed_model,
        "chat_provider":       "ambiguity_askback",
        "chat_model_version":  None,
        "elapsed_ms":          elapsed_ms,
        "used_fallback":       False,
    }
    try:
        ins = supabase.table("query_logs").insert(_payload).execute()
        _qid = ins.data[0].get("id") if ins.data else None
        _log_query_logs_insert_success(_qid, list(_payload.keys()), supabase=supabase)
        return _qid
    except Exception as _e:
        _log_query_logs_insert_failure(list(_payload.keys()), _e, supabase=supabase)
        return None


def _log_oos_skip(
    supabase: Any, *, masked: str, category: str | None, s: Any,
    elapsed_ms: int = 0,
    provider: str = "oos_skip",
) -> int | None:
    """PR-Phase-18.5.2: OOS Fast Skip 을 query_logs 에 경량 기록.

    chat_provider="oos_skip" / elapsed_ms = classify_query 실측(Option B) →
    18.3 모니터링 Dashboard 가 hit rate·실 latency 분포를 진실하게 표시.
    query_log_id 반환 → 👍/👎 피드백 가능. _log_faq_cache_hit 패턴 미러링.
    실패해도 응답 흐름 불변 (try/except 흡수).
    """
    _payload = {
        "category":            category if category and category != "전체" else None,
        "query_masked":        masked,
        "is_critical":         False,
        "critical_kind":       None,
        "hit_chunk_ids":       [],
        "hit_categories":      [],
        "env":                 s.env_tag,
        "embed_model_version": s.embed_model,
        "chat_provider":       provider,
        "chat_model_version":  None,
        "elapsed_ms":          elapsed_ms,
        "used_fallback":       False,
    }
    try:
        ins = supabase.table("query_logs").insert(_payload).execute()
        _qid = ins.data[0].get("id") if ins.data else None
        _log_query_logs_insert_success(_qid, list(_payload.keys()), supabase=supabase)
        return _qid
    except Exception as _e:
        _log_query_logs_insert_failure(list(_payload.keys()), _e, supabase=supabase)
        return None


@dataclass
class Answer:
    text: str
    is_critical: bool
    critical_kind: str | None
    contexts: list[dict]
    masked_question: str
    thinking: str = field(default="")
    elapsed: float = field(default=0.0)
    # query_logs.id (insert 결과). 사용자 피드백(👍/👎) 갱신 시 이 id 로 update.
    # insert 실패 시 None.
    query_log_id: int | None = field(default=None)
    # PR-C1 신뢰도. "high" | "medium" | "low" — app.py 의 chip 표시·
    # 디버깅용. ask_stream chunk 단계에선 비결정 → "done" 시점에만 채워짐.
    confidence: str = field(default="high")
    # contexts best RRF score (1/(60+r_vec) + 1/(60+r_kw)). 0.0~~0.0328.
    best_score: float = field(default=0.0)
    # PR-Fun1 작업 3: LLM 이 답변 끝에 출력한 후속 질문 카드 (3개 cap).
    # critical 답변에는 빈 list (prompts.py 가 생성 자체 차단). UI 가
    # ans.is_critical 분기로 추가 방어.
    suggestions: list[str] = field(default_factory=list)
    # PR-1: OOS 라우팅 답변 표식 — render.py 가 전용 카드로 분기. 기본 False.
    is_oos: bool = field(default=False)
    # PR-Ambiguity-Askback: 의도 명확화 역질문 선택지. 비어있지 않으면 UI 가
    # 일반 답변 chrome 대신 선택지 버튼을 렌더 (클릭 → sub-intent 재질의).
    # 각 항목 = {"label": 버튼 텍스트, "query": 재질의 문구}.
    clarify_choices: list[dict] = field(default_factory=list)


# ── PR-C1: Confidence-aware 단호도 ───────────────────────────
# best_score 의 RRF 단위 임계값으로 high/medium/low 분류.
# critical 트리거 시는 [Critical Mode 답변 가이드] 가 우선 — confidence
# prefix 비활성 (ask/ask_stream 호출 측에서 분기).

_CONFIDENCE_PREFIX = (
    "[NOTE — 시스템 운영 신호]\n"
    "이 질문에 대한 사규 검색의 신뢰도가 낮다고 판정되었습니다. "
    "[신뢰도 가이드] 섹션을 활성화하여 답변하세요. 단호 어휘 대신 "
    "추정형 표현을 쓰고, 답변 끝에 \"정확한 사항은 [라우팅 부서 분기 - 동적] 가 "
    "결정한 부서에 확인 바랍니다\" 한 줄을 추가하세요 (사규 본문 관리부서 우선). "
    "인라인 인용 (📎 + 볼드) 형식과 "
    "[참조: ...] 통합 출처 표기는 그대로 유지합니다.\n\n"
)


def _classify_confidence(best_score: float, hit_count: int) -> str:
    """[DEPRECATED — PR-Q1.4 이후 사용 안 함]

    PR-C1 v1 의 단일 RRF threshold 분류기. PR-Q1.3 진단 결과 kw search
    가 사실상 죽어 있어 (pg_bigm 미설치 + tsvector 한국어 미지원) 모든
    query 의 best_score 가 1/61 ≈ 0.0164 로 고정 — 분류 효과 무. 본
    함수는 호환성 유지 목적으로 코드만 보존하고 호출 측은 confidence.
    calculate_confidence 로 전환됨. kw search 부활 시 재사용 여지.
    """
    if hit_count <= 0:
        return "low"
    s = settings()
    if best_score >= s.confidence_high:
        return "high"
    if best_score >= s.confidence_medium:
        return "medium"
    return "low"


def _maybe_prefix_system_prompt(
    base_prompt: str, *, is_critical: bool, confidence: str,
) -> str:
    """confidence == 'low' AND critical 아닐 때만 prefix 활성 (PR-Q1.4).

    medium 은 chip (🟡) 만 표시하고 본문 톤은 단호하게 유지 — 사용자가
    "보조 참고" 신호로 자체 판단할 수 있게. low 일 때만 추정형 톤 +
    인사교육팀·CSR팀 안내 prefix 가 LLM system_instruction 에 prepend.

    critical 트리거 시는 [Critical Mode 답변 가이드] 가 우선이므로
    톤 완화 prefix 를 활성하지 않는다 (회사 보호 차원의 단호한 신고
    안내가 우선).
    """
    if is_critical:
        return base_prompt
    if confidence != "low":
        return base_prompt
    # PR-Revert-Confidence-Prefix-Append: Hit rate 향상 효과 X
    # (5/17 검증: 8.5%→14.3% 만, low query 거의 없어 변경 영역 X).
    # 더하여 Q5/Q11/Q13 의 length 회귀 발견 → 원상 복귀.
    return _CONFIDENCE_PREFIX + base_prompt


_TRANSIENT_HINTS = (
    "503", "UNAVAILABLE", "429", "RESOURCE_EXHAUSTED",
    "high demand", "overloaded", "overload",
)

# Gemini transient(429/503/RESOURCE_EXHAUSTED) 응답 시 backoff. Streamlit
# Cloud free tier 검수 회차에서 분당 quota 초과로 회차 멈춤이 빈번 → 충분한
# 회복 시간 확보. 기본 15s × 2^n × 5회 = 15→30→60→120→240s (총 ~470s).
# 정상 응답 흐름엔 무영향(transient 미발생 시 backoff 진입 자체 안 함).
_GEMINI_BACKOFF_BASE = float(os.getenv("GEMINI_BACKOFF_BASE", "15"))
_GEMINI_BACKOFF_ATTEMPTS = int(os.getenv("GEMINI_BACKOFF_ATTEMPTS", "5"))
# PR-fix-synth-timeout: 합성 호출(스트리밍/비스트리밍)이 Streamlit run 을
# 무한정/수 분 블록 → dangling 유발하던 근본원인 차단. 하드 한도 가드.
_SYNTH_OVERALL_TIMEOUT = float(os.getenv("NEXUS_SYNTH_OVERALL_TIMEOUT", "150"))
_SYNTH_STREAM_CHUNK_TIMEOUT = float(os.getenv("NEXUS_SYNTH_STREAM_CHUNK_TIMEOUT", "45"))


def _is_transient(e: Exception) -> bool:
    """503/429/RESOURCE_EXHAUSTED 류 모델 트래픽 폭주 신호 식별.
    primary 가 이 케이스로 실패하면 fallback provider 로 1회 전환 가능."""
    msg = str(e).lower()
    return any(h.lower() in msg for h in _TRANSIENT_HINTS)


def _gen_gemini(system: str, user: str, *, include_thinking: bool) -> tuple[str, str, str]:
    """Gemini 호출. Returns (text, thinking, model_id).

    raw thinking parts 는 SYSTEM_PROMPT 의 [검색 과정] 섹션으로 대체되어
    더 이상 추출하지 않는다. include_thinking 파라미터는 외부 호출자
    회귀 회피를 위해 시그니처만 유지하되 내부 동작은 항상 비활성.
    thinking 토큰은 답변 토큰 대비 2~3배 비용이라 비활성화로 비용·
    latency 부수 절감.
    """
    from google import genai
    from google.genai import types
    s = settings()
    cli = genai.Client(api_key=s.gemini_api_key)

    # PR-CAG-Integration: Explicit Cache 활성 + canonical SYSTEM_PROMPT 일 때
    # cached_content path. critical 모드 / low-confidence prefix 가 적용된 system
    # (≠ SYSTEM_PROMPT) 은 cache 우회 — 안전망 100% 유지.
    _cag_cache_name: Optional[str] = None
    try:
        from .nexus_cag_manager import is_cag_enabled, get_cache_name
        if is_cag_enabled() and system == SYSTEM_PROMPT:
            _cag_cache_name = get_cache_name()
    except Exception as _cag_err:
        print(
            f"[cag] WARN integration skipped (gen): "
            f"{type(_cag_err).__name__}: {_cag_err}",
            file=sys.stderr, flush=True,
        )

    if _cag_cache_name:
        # cached_content 사용 시 system_instruction 함께 못 설정 (SDK 제약).
        cfg = types.GenerateContentConfig(
            cached_content=_cag_cache_name,
            temperature=s.temperature,
            top_p=s.top_p,
        )
        print(
            f"[cag] using cached_content={_cag_cache_name}",
            file=sys.stderr, flush=True,
        )
    else:
        cfg = types.GenerateContentConfig(
            system_instruction=system,
            temperature=s.temperature,
            top_p=s.top_p,
        )

    # Gemini SDK 는 client-level timeout 설정이 일관되지 않아 ThreadPoolExecutor
    # 로 wrap. 60초 안에 응답 없으면 RuntimeError → 사용자에게 친화 메시지.
    # with-block 자동 shutdown(wait=True) 는 timeout thread 를 무한 대기시키므로
    # 수동 ex 관리 + finally shutdown(wait=False, cancel_futures=True).
    from concurrent.futures import ThreadPoolExecutor, TimeoutError as _Timeout
    res = None
    last_err: Exception | None = None
    _eval_model = _resolve_eval_model("gemini")
    _model_to_use = _eval_model or s.chat_model
    # PR-fix-synth-timeout: 전체 wall-clock deadline 으로 60초×최대5회 백오프
    # 누적(최악 수 분) 블록 차단. 회당 timeout 을 잔여 예산으로 cap + deadline
    # 초과 시 더 이상 재시도/sleep 안 함 → 친화 메시지로 빠른 전환.
    _ask_deadline = time.monotonic() + _SYNTH_OVERALL_TIMEOUT
    for attempt in range(_GEMINI_BACKOFF_ATTEMPTS):
        _ex = ThreadPoolExecutor(max_workers=1)
        try:
            _rem = _ask_deadline - time.monotonic()
            if _rem <= 0:
                last_err = RuntimeError(
                    f"Gemini 합성이 전체 {_SYNTH_OVERALL_TIMEOUT:.0f}초 한도 초과 — 응답 지연 중단(deadline guard)"
                )
                break
            _fut = _ex.submit(cli.models.generate_content,
                              model=_model_to_use, contents=user, config=cfg)
            res = _fut.result(timeout=max(1.0, min(60.0, _rem)))
            break
        except _Timeout as e:
            last_err = RuntimeError("Gemini 호출이 60초 내 응답하지 않았습니다.")
            if attempt < _GEMINI_BACKOFF_ATTEMPTS - 1 and time.monotonic() < _ask_deadline:
                time.sleep(min(_GEMINI_BACKOFF_BASE * (2 ** attempt),
                               max(0.0, _ask_deadline - time.monotonic())))
                continue
            raise last_err from e
        except Exception as e:
            last_err = e
            if (_is_transient(e) and attempt < _GEMINI_BACKOFF_ATTEMPTS - 1
                    and time.monotonic() < _ask_deadline):
                wait = min(_GEMINI_BACKOFF_BASE * (2 ** attempt),
                           max(0.0, _ask_deadline - time.monotonic()))
                print(
                    f"[Gemini backoff] attempt {attempt+1}/"
                    f"{_GEMINI_BACKOFF_ATTEMPTS} sleep {wait:.0f}s",
                    flush=True,
                )
                time.sleep(wait)
                continue
            raise
        finally:
            _ex.shutdown(wait=False, cancel_futures=True)
    if res is None and last_err is not None:
        raise last_err

    # PR-Add-Gemini-Cache-Monitoring: implicit caching hit 율 + 비용 절감 측정.
    # response.usage_metadata.cached_content_token_count = 캐시 hit 토큰 수.
    # best-effort — 예외 시 답변 흐름 무영향 (logs 만 skip).
    try:
        _um = getattr(res, "usage_metadata", None)
        if _um is not None:
            _cached = getattr(_um, "cached_content_token_count", 0) or 0
            _prompt = getattr(_um, "prompt_token_count", 0) or 0
            _hit_rate = (100.0 * _cached / _prompt) if _prompt else 0.0
            print(
                f"[chatbot:gemini:cache] cached_tokens={_cached} "
                f"prompt_tokens={_prompt} hit_rate={_hit_rate:.1f}% "
                f"model={_model_to_use}",
                flush=True,
            )
    except Exception as _cache_log_err:
        print(
            f"[chatbot:gemini:cache] WARN log skipped: "
            f"{type(_cache_log_err).__name__}",
            flush=True,
        )

    text_parts: list[str] = []
    try:
        for part in res.candidates[0].content.parts:
            # thought 파트는 [검색 과정] 통합으로 더 이상 사용하지 않음 → drop.
            if getattr(part, "thought", False):
                continue
            text_parts.append(part.text or "")
    except Exception:
        text_parts = [res.text or ""]

    text = "".join(text_parts).strip() or (res.text or "").strip()
    if not text:
        # PR-B 게이트 ②: 빈 완료를 예외로 승격 → _gen fallback / ask 백스톱.
        raise EmptyCompletionError(f"empty completion: model={_model_to_use}")
    return text, "", _model_to_use


def _gen_claude(system: str, user: str, *, include_thinking: bool) -> tuple[str, str, str]:
    """Claude 호출. Returns (text, thinking, model_id).

    Opus 4.7 기준:
    - temperature/top_p/top_k 사용 불가 (400). 프롬프트로 결정성 제어.
    - effort 는 output_config 안에 넣음 (top-level 아님).
    - raw thinking 은 SYSTEM_PROMPT 의 [검색 과정] 섹션으로 대체되어 더
      이상 추출하지 않음. include_thinking 파라미터는 외부 호출자 회귀
      회피를 위해 시그니처만 유지하되 내부 동작은 항상 disabled.
    """
    import anthropic
    s = settings()
    if not s.anthropic_api_key:
        raise RuntimeError("ANTHROPIC_API_KEY 가 설정되지 않았습니다.")
    # 60초 timeout — anthropic SDK 기본은 10분이라 사용자 무한 대기 위험.
    # max_retries=0 — SDK auto-retry 비활성. 우리 외곽 retry 와 중첩되면
    # 최악 케이스 540초까지 대기해 Streamlit 504 발생 + 사용자 spinner 영원.
    cli = anthropic.Anthropic(api_key=s.anthropic_api_key,
                              timeout=60.0, max_retries=0)

    _eval_model = _resolve_eval_model("claude")
    _model_to_use = _eval_model or s.claude_model
    kwargs: dict = {
        "model": _model_to_use,
        "max_tokens": 16000,
        "system": system,
        "messages": [{"role": "user", "content": user}],
        "thinking": {"type": "disabled"},
    }
    if s.claude_effort:
        kwargs["output_config"] = {"effort": s.claude_effort}

    res = None
    last_err: Exception | None = None
    for attempt in range(3):
        try:
            res = cli.messages.create(**kwargs)
            break
        except anthropic.RateLimitError as e:
            last_err = e
            if attempt < 2:
                time.sleep(1.5 * (2 ** attempt)); continue
            raise
        except anthropic.APIStatusError as e:
            last_err = e
            if e.status_code >= 500 and attempt < 2:
                time.sleep(1.5 * (2 ** attempt)); continue
            raise
        except anthropic.APIConnectionError as e:
            last_err = e
            if attempt < 2:
                time.sleep(1.5 * (2 ** attempt)); continue
            raise
    if res is None and last_err is not None:
        raise last_err

    text_parts: list[str] = []
    for block in res.content:
        # thinking 블록은 비활성화 상태라 정상적으로는 등장하지 않으나,
        # 모델/SDK 가 예상 외로 흘릴 경우에 대비해 명시적으로 drop.
        if block.type == "text":
            text_parts.append(getattr(block, "text", "") or "")

    _claude_text = "".join(text_parts).strip()
    if not _claude_text:
        # PR-B 게이트 ②: 빈 완료를 예외로 승격.
        raise EmptyCompletionError(f"empty completion: model={_model_to_use}")
    return (_claude_text, "", _model_to_use)


_PROVIDER_FUNCS = {"gemini": _gen_gemini, "claude": _gen_claude}


def _gen(system: str, user: str, *, include_thinking: bool) -> tuple[str, str, str, str, bool]:
    """Provider dispatcher. Returns (text, thinking, provider, model_id, used_fallback).

    primary 가 transient(503/429) 실패하면 fallback 으로 1회 자동 전환.
    비전이성 에러(인증·인풋 문제)는 즉시 raise.

    used_fallback: primary 가 transient 실패 후 fallback 분기에서 응답을 받았는지.
    """
    s = settings()
    # eval override 가 있으면 단일 provider 만 사용 — fallback chain
    # 우회. 평가 회차에서 모델별 순수 응답 측정 보장 (다른 모델 응답
    # 으로 fallback 되면 회차 결과 무의미).
    _eval_provider = _resolve_eval_provider()
    if _eval_provider:
        chain: list[str] = [_eval_provider]
    else:
        primary = (s.chat_provider or "gemini").lower()
        fallback = (s.chat_fallback_provider or "").lower()
        chain = [primary]
        if fallback and fallback != primary:
            chain.append(fallback)

    last_err: Exception | None = None
    used_fallback = False
    for prov in chain:
        fn = _PROVIDER_FUNCS.get(prov)
        if fn is None:
            continue
        # fallback=claude 인데 ANTHROPIC_API_KEY 미설정이면 조용히 skip
        if prov == "claude" and not s.anthropic_api_key:
            continue
        try:
            text, thinking, model_id = fn(system, user, include_thinking=include_thinking)
            return text, thinking, prov, model_id, used_fallback
        except Exception as e:
            last_err = e
            # PR-B 게이트 ②: 빈 완료도 provider 전환(구제) 대상에 포함.
            if not (_is_transient(e) or isinstance(e, EmptyCompletionError)):
                raise
            # transient/빈완료 → 다음 provider 시도. 다음 시도부터는 fallback 분기.
            used_fallback = True
            continue
    if last_err is not None:
        raise last_err
    raise RuntimeError("No chat provider configured")


def _prepend_question_quote(answer: str, question: str) -> str:
    """답변 본문 앞에 사용자 질문 원문 quote 줄을 mechanical 하게 붙인다.

    PR-Quality-4: LLM 이 system prompt 의 quote 지시를 무시하고
    "안전관리" → "[익명]" 같은 변형을 일으키는 결함 차단 — quote 를
    LLM 외부 (Python 단) 에서 강제 prepend. system prompt 의 [출력 구조]
    에서 ① 이해 확인 항목은 폐기됨.

    question 은 마스킹 후 텍스트 사용 — answer 본문이 마스킹 기준이라
    quote 줄도 동일 기준으로 일관되게 한다. PII 가 quote 줄에 raw 노출
    되는 사고도 차단.
    """
    q = (question or "").strip()
    if not q:
        return answer
    return f"질문하신 내용: '{q}'\n\n{answer.lstrip()}"


def _normalize_hr_dept_name(text: str) -> str:
    """rule 4-1-A 결정적 강제: 사용자 안내·권장·신고 문구의 '인사팀' →
    '인사교육팀' (조직개편 현행 조직명). 단, 사규-필드 직접 인용
    ("관리부서: 인사팀" 등 옛 표기)은 '사규 본문이 진실' 원칙대로 보존.
    LLM 이 프롬프트 룰(4-1-A)을 누락해 안내문에 '인사팀'을 흘리는 누출의
    결정적 안전망 — 본문 최종 조립 직후 단일 지점에서 강제. '인사교육팀'은
    '인사팀'을 부분문자열로 포함하지 않아 이중변환 없음."""
    if not text or "인사팀" not in text:
        return text
    _PROTECT = ("관리부서: 인사팀", "관리부서:인사팀", "관리부서 인사팀")
    _saved = {}
    out = text
    for _i, _pat in enumerate(_PROTECT):
        if _pat in out:
            _tok = "ZZHRFIELDZZ%d" % _i
            _saved[_tok] = _pat
            out = out.replace(_pat, _tok)
    out = out.replace("인사팀", "인사교육팀")
    for _tok, _pat in _saved.items():
        out = out.replace(_tok, _pat)
    return out


def _ensure_citation(answer: str, contexts: list[dict]) -> str:
    if "[참조:" in answer:
        return answer
    cites: list[str] = []
    for c in contexts:
        title = c.get("doc_title") or c.get("title") or "문서"
        if c.get("article_no"):
            cites.append(f"{title} {c['article_no']}")
        elif c.get("case_no"):
            cites.append(f"사례집 #{c['case_no']}")
        else:
            cites.append(title)
    if not cites:
        return answer + "\n\n[참조: 검색 결과 없음]"
    return answer + f"\n\n[참조: {', '.join(cites[:5])}]"


# 토큰 분리(한글 + 영문 + 숫자) — citation 정규화 fuzzy 매칭용
_TOKEN_RE = re.compile(r"[\w가-힣]+")
# 조항 추출 (제N조 / 제N조의M / 제N조 제M항)
_ARTICLE_RE = re.compile(r"(제\s*\d+\s*조(?:의\s*\d+)?(?:\s*제\s*\d+\s*항)?)")
# [참조: ...] 블록 매칭 — 본문 내 다중 출현 모두 처리
_CITE_BLOCK_RE = re.compile(r"\[참조:\s*([^\]]+)\]")
# citation 정규화 임계값 — 너무 낮으면 오인 매칭, 너무 높으면 변형 미커버.
# 0.6 은 "(CSR) 클린뱅크 운영 지침" vs "클린뱅크 운영지침" 케이스 통과 기준.
_CITATION_NORMALIZE_THRESHOLD = 0.6


def _tokens(s: str) -> set[str]:
    return {t.lower() for t in _TOKEN_RE.findall(s)}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _normalize_citation_block(answer: str, contexts: list[dict]) -> str:
    """LLM 이 [참조: ...] 안에 변형 출력했을 때 contexts 의 정확한
    doc_title 로 교체. 매칭 신뢰도(jaccard) ≥ 0.6 인 경우만 교체. 못
    찾으면 원본 유지(회귀 안전). 사례집 형식은 변환 외.

    예: LLM "[참조: 클린뱅크 운영지침 제3조]"
         + contexts [{"doc_title": "(CSR) 클린뱅크 운영 지침", ...}]
         → "[참조: (CSR) 클린뱅크 운영 지침 제3조]"
    """
    if not contexts or "[참조:" not in answer:
        return answer

    doc_titles: list[tuple[str, set[str]]] = []
    for c in contexts:
        t = c.get("doc_title") or c.get("title")
        if t:
            doc_titles.append((t, _tokens(t)))
    if not doc_titles:
        return answer

    def _replace(match: re.Match[str]) -> str:
        block_inner = match.group(1).strip()
        # 사례집(#N) 인용은 doc_title 매칭 대상 아님 — 원본 유지
        if "사례집" in block_inner:
            return match.group(0)

        sources = [s.strip() for s in block_inner.split(",") if s.strip()]
        normalized: list[str] = []
        for src in sources:
            src_tokens = _tokens(src)
            if not src_tokens:
                normalized.append(src)
                continue
            best_score = 0.0
            best_title: str | None = None
            for title, t_tokens in doc_titles:
                score = _jaccard(src_tokens, t_tokens)
                if score > best_score:
                    best_score = score
                    best_title = title
            if best_score >= _CITATION_NORMALIZE_THRESHOLD and best_title:
                article_match = _ARTICLE_RE.search(src)
                article = article_match.group(1) if article_match else ""
                normalized.append(f"{best_title} {article}".rstrip())
            else:
                normalized.append(src)
        return f"[참조: {', '.join(normalized)}]"

    return _CITE_BLOCK_RE.sub(_replace, answer)


def _extract_action_items(answer: str) -> list[str]:
    """권장 행동 섹션 본문에서만 numbered list 추출. 사규 인용에 포함된
    일반 numbered list (정의/적용범위/위반 시 등) 가 권장 행동으로 오인되어
    enforce_structure 답변 구조를 왜곡하던 결함 방지."""
    sec = _RE_ACTION_SECTION.search(answer)
    target = sec.group(1) if sec else answer
    return [m.group(1).strip() for m in _RE_ACTION_BLOCK.finditer(target)][:3]


# doc_kind 별 분산 비율 (베타 단계 고정. 운영 중 조정 필요 시
# NEXUS_DOC_KIND_RATIOS 환경변수로 외부화 검토).
# 의미 그룹: {rule, penalty} = 사규 기준 블록, {case} = 사건사례 블록.
# SYSTEM_PROMPT 의 [출력 구조] ③ 가 두 블록을 각각 채우도록 의무화하므로
# retriever 결과가 한 doc_kind 만 잡혀 잘리면 상대 블록이 폴백 메시지로
# 깨짐 → 사용자 답변 품질 저하. 본 분산으로 양 블록 모두 들어가도록 보장.
_DOC_KIND_RATIOS: "OrderedDict[str, int]" = OrderedDict([
    ("rule", 5),
    ("penalty", 2),
    ("case", 2),
])

# Phase 6 (PR #101): universal SOP preservation cap.
# Phase 1.5 의 unconditional 보존이 7 슬롯을 universal SOP 만으로 채워
# 카테고리 specific docs 누락. 5 chunks 까지 보존 — 나머지는 category 청크용.
_UNIVERSAL_SOP_MAX_CHUNKS: int = 5

# PR-Fix-DocKind-Preserve: doc_kind=penalty/case 강제 보존 cap.
# hybrid_search 가 한국어 kw 매칭 부족(text_tsv='simple')으로 penalty/case
# 사규를 pool 안에 못 띄울 때, contexts_raw 안의 해당 chunks 를 universal_sop
# 와 동등 패턴으로 추가 보존. categories 필터는 이미 적용됨.
_FORCE_KIND_MAX: dict[str, int] = {"penalty": 2, "case": 2}

# Phase 6 → PR-Fix-DocKind-Preserve: retriever pool 확장 — penalty/case 사규
# 가 raw pool 안에 들어올 확률 증가 (vector-only ranking 에서 일반적 사규의
# 점수가 specific 사규보다 낮은 회귀 완화).
_POOL_SIZE_MARGIN: int = 60  # PR-A-Expand-Pool-Size: 30 → 60 (raw pool ~67 chunks, Q13 type recall ↑)


def _balance_by_doc_kind(
    contexts: list[dict],
    ratios: "OrderedDict[str, int]" = _DOC_KIND_RATIOS,
) -> list[dict]:
    """검색 결과를 doc_kind 별 비율로 분산 추출.

    - 입력 contexts 는 점수 내림차순 정렬 가정 (RPC RRF score desc).
    - 각 doc_kind 에서 ratios[kind] 만큼 추출 (있는 만큼만).
    - 부족해도 다른 kind 로 메우지 않음 — 빈 자리는 SYSTEM_PROMPT 폴백
      "해당 유형 문서가 검색되지 않았습니다" 가 사용자에게 정직한 신호.
    - 결과 순서: ratios 정의 순(rule → penalty → case) 으로 의미 그룹별
      인접 배치. 각 그룹 내에서는 입력 점수 순서를 보존.
    - unknown doc_kind 는 무시.
    """
    if not contexts:
        return []
    by_kind: dict[str, list[dict]] = {kind: [] for kind in ratios}
    for c in contexts:
        kind = c.get("doc_kind")
        if kind in by_kind:
            by_kind[kind].append(c)
    # PR-Balance-Force-Include-Priority: force_included_by_intent=True 청크를
    # 각 doc_kind 그룹 앞으로 stable-sort. raw_chunks 끝에 rrf_score=0 으로
    # union 된 force 청크가 Reranker top-N + cap=ratios[kind] 에서 탈락해
    # LLM 컨텍스트에 빠지던 회귀(예: 출장비 "사규 미발견") fix. 동일 우선순위
    # 청크끼리는 입력(Reranker) 순서 보존.
    # PR-RPC-Priority: force chunk 우선 + 그 안에서 cross-cutting (공통)/
    # universal-SOP 는 후순위. rule bucket cap(ratios[kind]) 에서 도메인 사규
    # force chunk 가 (공통) 사건사고 보고지침 force chunk 에 밀려 잘리던 회귀 fix.
    for kind in by_kind:
        by_kind[kind].sort(
            key=lambda c: (
                not c.get("force_included_by_intent", False),
                (_chunk_domain(c) == "공통") or bool(c.get("is_universal_sop")),
            )
        )
    result: list[dict] = []
    for kind, n in ratios.items():
        # PR-Fix-Penalty-All-Chunks: penalty 는 cap 무시 — retriever 단계에서
        # 강제 보존한 임직원 징계기준 등 모든 penalty 청크가 LLM 컨텍스트에
        # 그대로 전달되어야 답변 ⚖️ 징계 기준 섹션의 구체 표 인용 보장.
        if kind == "penalty":
            result.extend(by_kind[kind])
        else:
            result.extend(by_kind[kind][:n])
    return result


def ask(
    supabase: Any,
    *,
    question: str,
    category: str | None,
    extra_pii_terms: list[str] | None = None,
    progress_callback: Callable[[str, dict], None] | None = None,
    prev_turn: dict | None = None,
    hard_category: str | None = None,
) -> Answer:
    """답변 생성 entry point.

    progress_callback: 단계별 진행 알림(stage, payload). app.py 의 st.status
    UI 가 사용. None 이면 emit 비활성. 콜백 내부 예외는 흡수되어 ask 본 흐름을
    깨뜨리지 않음. injection early-exit 분기에서는 호출되지 않음.

    stage 순서 (정상 흐름): "analyze" → "search_start" → "search_done" →
    "generate" → "complete". "search_done" payload 는
    {doc_titles, doc_kind_counts, total} 키를 담는다.

    prev_turn: {"question": str, "answer": str} 또는 None. 사용자가 "🔗 관련
    질문" 모드를 선택해 직전 1턴 컨텍스트를 유지할 때 app.py 가 전달.
    None 이면 단일 턴 동작(기존). build_user_prompt 가 <이전 대화> 섹션을
    프롬프트 앞에 prepend 한다. injection early-exit 분기는 prev_turn 무시.
    """
    def _emit(stage: str, payload: dict | None = None) -> None:
        if progress_callback is None:
            return
        try:
            progress_callback(stage, payload or {})
        except Exception:
            pass  # callback 실패가 ask 본 흐름을 깨면 안 됨

    s = settings()
    # PR-Phase-18.3.1: Option B — t0 를 ask 진입부로 이동해 Fast Path /
    # OOS Skip / 정상 pipeline 모두 동일한 "ask 진입~답변 반환" 전체 시간을
    # elapsed_ms 로 측정. retrieval 직전(과거 위치) 의 t0 는 아래에서 제거.
    t0 = time.perf_counter()

    # PR-Phase-17.1: Query Classifier Shadow Mode — logging 전용 (action 없음).
    # 기본 비활성(ENABLE_QUERY_CLASSIFIER_LOGGING=false) → 호출 자체 미실행 →
    # ZERO regression. 실패해도 본 흐름 영향 없음 (classify_query 내부 흡수).
    if ENABLE_QUERY_CLASSIFIER_LOGGING:
        try:
            # PR-Phase-19.2.3: 동의어 확장된 query 로 분류 (사내 약어 OOS 차단)
            classify_query(question, supabase=supabase)
        except Exception as _qc_e:
            print(f"[query_classifier:shadow] error: {_qc_e}",
                  file=sys.stderr, flush=True)

    # Prompt injection 1차 필터 — LLM 호출 전 차단으로 토큰 비용·로깅 노이즈 절감.
    # 매치되면 LLM 미호출 + critical 트리거 안 함 + 별도 로그만 남기고 거절.
    if _looks_like_injection(question):
        _block_payload = {
            "category":            category if category and category != "전체" else None,
            "query_masked":        "[BLOCKED — prompt injection signature]",
            "is_critical":         False,
            "critical_kind":       None,
            "hit_chunk_ids":       [],
            "hit_categories":      [],
            "env":                 s.env_tag,
            "embed_model_version": s.embed_model,
            "chat_provider":       "blocked",
            "chat_model_version":  None,
            "elapsed_ms":          0,
            "used_fallback":       False,
        }
        try:
            _ins = supabase.table("query_logs").insert(_block_payload).execute()
            _row_id = _ins.data[0].get("id") if _ins.data else None
            _log_query_logs_insert_success(
                _row_id, list(_block_payload.keys()), supabase=supabase,
            )
        except Exception as _e:
            _log_query_logs_insert_failure(
                list(_block_payload.keys()), _e, supabase=supabase,
            )
        return Answer(
            text=("해당 요청은 처리할 수 없습니다. 사규·윤리강령·사례집 관련 "
                  "질문을 해주세요.\n\n[참조: 검색 결과 없음]"),
            is_critical=False,
            critical_kind=None,
            contexts=[],
            masked_question="[BLOCKED]",
            thinking="",
            elapsed=0.0,
            query_log_id=None,
        )

    _emit("analyze")
    masked = mask_pii(question, extra_pii_terms or [])

    # 심각 사안 트리거 감지 (마스킹 전 원문 기준이 더 정확하므로 원문에도 검사)
    keywords = load_keywords(supabase)
    detection: CriticalDetection = detect(question, keywords)
    if not detection.triggered:
        detection = detect(masked, keywords)

    # PR-Ambiguity-Askback: 내용 없는 모호 bare 토큰("발주"/"감사") → 검색·합성
    # 전에 short-circuit 하여 의도 명확화 역질문 반환 (거짓 "없음" 환각 차단 +
    # 자원 절약). detect() 이후라 critical 은 위에서 triggered=True → 이 gate
    # 우회. 사용자가 선택지 클릭 → 구체 sub-intent 재질의 → 정상 RAG. flag OFF 기본.
    if ENABLE_AMBIGUITY_ASKBACK and not detection.triggered:
        _ambig = detect_bare_ambiguity(question)
        if _ambig:
            _ab_elapsed = time.perf_counter() - t0
            _log_ambiguity_askback(
                supabase, masked=masked, category=category, s=s,
                elapsed_ms=int(_ab_elapsed * 1000),
            )
            _emit("complete")
            return Answer(
                text=_ambig["prompt"],
                is_critical=False,
                critical_kind=None,
                contexts=[],
                masked_question=masked,
                elapsed=_ab_elapsed,
                query_log_id=None,
                confidence="high",
                clarify_choices=_ambig["choices"],
            )

    # PR-Phase-18.2: FAQ Fast Path — 승인된 비-critical 캐시 hit 시 즉시 반환.
    # detect() 이후라 critical 쿼리는 위에서 detection.triggered=True 로 판정 →
    # 이 gate 우회 → 정상 critical pipeline(핫라인) 진입 보장. 또한 faq_cache_get
    # 은 approved·is_critical=false 만 반환 → 이중 가드. flag OFF(기본) 시 미진입.
    if ENABLE_FAST_PATH and not detection.triggered:
        _faq_hit = faq_cache_get(question)
        if _faq_hit:
            _fp_elapsed = time.perf_counter() - t0
            _qid = _log_faq_cache_hit(
                supabase, masked=masked, category=category, s=s,
                elapsed_ms=int(_fp_elapsed * 1000),
            )
            _emit("complete")
            return Answer(
                text=_faq_hit["answer_text"],
                is_critical=False,
                critical_kind=None,
                contexts=[],
                masked_question=masked,
                elapsed=_fp_elapsed,
                query_log_id=_qid,
                confidence="high",
            )

    # PR-Phase-18.5.2: OOS Fast Skip — 사규 범위 밖 query → 라우팅 안내.
    # 안전 가드 (4중):
    #   1) detect() 이후라 critical 키워드 매치는 위에서 triggered=True 로 우회
    #   2) not detection.triggered 가드 (detect 통과한 critical-adjacent 도 차단)
    #   3) CLASSIFIER_PROMPT Negative Prompting (#271, 21개 위험 키워드)
    #   4) _DEFAULT_OOS_MESSAGE 의 self-correction 문단 (사용자 재시도 가이드)
    # classify_query 실패 default="standard" → OOS 미진입 → 정상 pipeline (안전).
    if ENABLE_OOS_ROUTING and not detection.triggered:
        _cls = classify_query(question, supabase=supabase)
        if _cls.get("category") == "out_of_scope":
            from .oos_router import gated_oos_decision
            if gated_oos_decision(supabase, question):
                from .oos_router import oos_routing_message
                # PR-Phase-18.3.1: Option B — classifier-only 측정에서 ask 진입부
                # t0 기준 전체 시간으로 교체 (사용자 체감 latency 정합).
                _oos_elapsed = time.perf_counter() - t0
                _qid = _log_oos_skip(
                    supabase, masked=masked, category=category, s=s,
                    elapsed_ms=int(_oos_elapsed * 1000),
                )
                _emit("complete")
                return Answer(
                    text=oos_routing_message(supabase),
                    is_critical=False,
                    critical_kind=None,
                    contexts=[],
                    masked_question=masked,
                    elapsed=_oos_elapsed,
                    query_log_id=_qid,
                    confidence="high",
                    is_oos=True,
                )
            # PR-OOS-Gate: 관련 사규 발견 -> OOS 취소, 정상 파이프라인 진행(override)
            _log_oos_skip(
                supabase, masked=masked, category=category, s=s,
                elapsed_ms=int((time.perf_counter() - t0) * 1000),
                provider="oos_override",
            )

    # 카테고리 필터:
    # 1) 명시 인자(category) 가 있으면 그것 + '공통' 합집합으로 폭 넓힘
    # 2) 명시 인자 없으면 질의에서 자동 추론(infer_categories) — 상위 3개
    #    + '공통' 합집합. retrieval 정확도 향상 목표
    # 3) 추론도 실패하면 None (전체 검색) — 기존 동작 fallback
    cats: list[str] | None
    if hard_category and not detection.triggered:
        # PR-Hard-Scope: 명시적 도메인 선택 → base 검색도 {공통, cat} 로 스코프
        # (force-include 단계는 hybrid_search 내부 hard_scope_category 가 처리).
        cats = list({"공통", hard_category})
    elif category and category != "전체":
        cats = list({"공통", category})
    else:
        inferred = infer_categories(question)
        if inferred:
            cats = list(set(inferred) | {"공통"})
        else:
            cats = None

    # 심각 사안일 때는 안전 카테고리도 우선적으로 합집합에 포함
    if detection.triggered:
        if detection.kind == "safety":
            cats = list(set((cats or []) + ["안전", "공통"]))
        elif detection.kind == "harassment":
            cats = list(set((cats or []) + ["공통"]))

    # PR-Phase-18.3.1: t0 는 ask 진입부(상단)에서 정의됨 — 여기는 의도적
    # 미정의 (Option B: 진입~retrieval 직전 elapsed 도 포함하기 위함).

    _emit("search_start")
    # doc_kind 분산: 큰 풀에서 검색 후 비율로 잘라냄. 한 doc_kind 가 풀에서
    # 우세할 때 다른 kind 가 풀에서 빠질 위험 완화 위해 합계 + 여유분 _POOL_SIZE_MARGIN.
    pool_size = sum(_DOC_KIND_RATIOS.values()) + _POOL_SIZE_MARGIN
    # PR-UI-Sub-Stage-Visualization: hybrid_search 의 sub-stage emit pass.
    contexts_raw = hybrid_search(
        supabase, question=masked, raw_question=question, categories=cats,
        top_k=pool_size, progress_callback=progress_callback,
        hard_scope_category=(hard_category if not detection.triggered else None),
    )
    contexts = _balance_by_doc_kind(contexts_raw)
    _shadow_log_multi_facet(contexts)
    _shadow_log_multi_facet(contexts_raw, "raw")
    # Phase 1.5 (PR #95) → Phase 6 (PR #101): universal SOP 청크 보존, _UNIVERSAL_SOP_MAX_CHUNKS 까지 cap.
    # _balance_by_doc_kind 의 rule=3 cap 으로 universal SOP 가 drop 되는 회귀 차단 +
    # 7 슬롯 모두 universal SOP 로 차서 카테고리 specific docs 누락하던 회귀 차단.
    _balanced_ids = {c.get("chunk_id") for c in contexts if c.get("chunk_id")}
    _sop_preserved = 0
    for c in contexts_raw:
        if not c.get("is_universal_sop"):
            continue
        if _sop_preserved >= _UNIVERSAL_SOP_MAX_CHUNKS:
            break
        cid = c.get("chunk_id")
        if cid and cid not in _balanced_ids:
            contexts.append(c)
            _balanced_ids.add(cid)
            _sop_preserved += 1
    if _sop_preserved:
        import sys as _sys
        print(
            f"[chatbot:ask] universal_sop_preserved={_sop_preserved}/{_UNIVERSAL_SOP_MAX_CHUNKS} "
            f"contexts_after_balance={len(contexts)}",
            file=_sys.stderr, flush=True,
        )
    # PR-Fix-DocKind-Preserve: doc_kind=penalty/case 도 동일 패턴으로 강제 보존.
    # universal_sop 와 같은 흐름 — contexts_raw 안의 해당 kind chunks 를
    # _FORCE_KIND_MAX 까지 contexts 에 추가. categories 필터는 hybrid_search 단계에서 적용됨.
    _kind_preserved: dict[str, int] = {k: 0 for k in _FORCE_KIND_MAX}
    for c in contexts_raw:
        kind = c.get("doc_kind")
        if kind not in _FORCE_KIND_MAX:
            continue
        if _kind_preserved[kind] >= _FORCE_KIND_MAX[kind]:
            continue
        cid = c.get("chunk_id")
        if cid and cid not in _balanced_ids:
            contexts.append(c)
            _balanced_ids.add(cid)
            _kind_preserved[kind] += 1
    if any(_kind_preserved.values()):
        import sys as _sys_fk
        print(
            f"[chatbot:ask] force_kind_preserved={_kind_preserved} "
            f"contexts_after_force_kind={len(contexts)}",
            file=_sys_fk.stderr, flush=True,
        )
    _emit("search_done", {
        "doc_titles": [c.get("doc_title", "") for c in contexts if c.get("doc_title")],
        "doc_kind_counts": dict(Counter(c.get("doc_kind") for c in contexts)),
        "total": len(contexts),
    })

    # PR-Q1.4: 멀티 시그널 confidence (hit_count + doc_kind_diversity +
    # category_match). best_score 는 디버깅·Answer 노출용으로만 산출.
    from .confidence import calculate_confidence
    _scores = [float(c.get("score") or 0.0) for c in contexts]
    best_score = max(_scores) if _scores else 0.0
    confidence = calculate_confidence(masked, contexts)
    system_prompt_eff = _maybe_prefix_system_prompt(
        SYSTEM_PROMPT,
        is_critical=detection.triggered, confidence=confidence,
    )

    # PR-A 게이트 ①: 검색 0건 → LLM 미호출 결정적 거절 (R-2/V-1 차단). flag OFF 기본.
    if ENABLE_NO_CONTEXT_GATE and not contexts:
        _emit("complete")
        return Answer(
            text=SAFE_NO_CONTEXT,
            is_critical=detection.triggered,
            critical_kind=detection.kind,
            contexts=[],
            masked_question=masked,
            elapsed=time.perf_counter() - t0,
            query_log_id=None,
            confidence="low",
        )

    # PR-B 게이트 ②: 검색은 됐으나 관련성 미달 → OOS 카드로 deflect.
    #   분류기 누락('휴가'=standard 오분류 등)의 최종 안전망. confidence!=high 일
    #   때만 judge_relevance 1콜(좋은 답엔 지연 0). 임계 0.85=OOS 게이트 동일 보정.
    #   flag OFF 기본 · judge 실패 시 fail-open(1.0)→정상 진행.
    if (ENABLE_OOS_RELEVANCE_GATE and contexts and not detection.triggered
            and confidence != "high"):
        from .nexus_reranker import judge_relevance
        from .oos_router import _OOS_OVERRIDE_THRESHOLD, oos_routing_message
        if judge_relevance(question, contexts) < _OOS_OVERRIDE_THRESHOLD:
            _rg_elapsed = time.perf_counter() - t0
            _rg_qid = _log_oos_skip(
                supabase, masked=masked, category=category, s=s,
                elapsed_ms=int(_rg_elapsed * 1000),
                provider="oos_relevance_gate",
            )
            _emit("complete")
            return Answer(
                text=oos_routing_message(supabase),
                is_critical=False,
                critical_kind=None,
                contexts=[],
                masked_question=masked,
                elapsed=_rg_elapsed,
                query_log_id=_rg_qid,
                confidence="high",
                is_oos=True,
            )

    user = build_user_prompt(masked, contexts, prev_turn=prev_turn)
    _emit("generate")
    try:
        raw, _legacy_thinking, used_provider, used_model, used_fallback = _gen(
            system_prompt_eff, user, include_thinking=False,
        )
    except EmptyCompletionError:
        # PR-B 게이트 ②: 모든 provider 빈 완료 소진 → 결정적 백스톱.
        _emit("complete")
        return Answer(
            text=SAFE_EMPTY_COMPLETION,
            is_critical=detection.triggered,
            critical_kind=detection.kind,
            contexts=contexts,
            masked_question=masked,
            elapsed=time.perf_counter() - t0,
            query_log_id=None,
            confidence="low",
        )
    # [검색 과정] 섹션을 본문에서 분리. 본문 후처리(_ensure_citation,
    # enforce_structure) 는 answer 부분만 받게 해서 [검색 과정] 텍스트가
    # 답변에 raw 로 노출되거나 hotline 구조 안으로 섞이는 사고 차단.
    answer_text, process_text_raw = _split_answer_and_process(raw)
    # ①②③④ 4단계를 '**마커 단계명**\n\n본문' markdown 으로 정형화 — LLM 이
    # 한 줄로 이어 쓰거나 헤더 강조 없이 출력하는 경우의 안전망. answer_text
    # 는 이 단계를 거치지 않아 본문 내 우연한 마커는 변형되지 않음.
    process_text = _format_process_section(process_text_raw)
    # 운영 모드(NEXUS_SHOW_THINKING=false) 에서는 process 추출은 하되 사용자
    # 화면에 노출하지 않는다. SYSTEM_PROMPT instruction 은 토글과 무관하게
    # 항상 활성 — instruction 동적 분기는 prompt 안정성을 깨뜨릴 수 있음.
    effective_process = process_text if s.show_thinking else ""

    # PR-Fun1: [SUGGESTIONS] 블록 분리 — citation 정규화·enforce_structure
    # 보다 먼저 잘라내야 본문 후처리가 카드용 메타에 영향 안 받는다.
    # critical 답변은 prompts 에 의해 생성 차단이지만 LLM 일관성 깨짐 대비
    # 본문에서도 잘라낸다 (이중 방어).
    answer_text, suggestions = _split_suggestions(answer_text)

    answer_text = _ensure_citation(answer_text, contexts)
    # LLM 변형 출력 정규화 — [참조:] 블록 안의 doc_title 을 contexts 기준
    # 정확 형태로 교체. 임계값 미달 시 원본 유지(회귀 안전).
    answer_text = _normalize_citation_block(answer_text, contexts)

    if detection.triggered:
        actions = _extract_action_items(answer_text)
        hotlines = load_hotlines(supabase)
        final = enforce_structure(
            base_answer=answer_text,
            kind=detection.kind or "safety",
            action_items=actions,
            hotlines=hotlines,
        )
        # critical 답변엔 카드 노출 X (이중 방어 — UI 단도 같은 분기).
        suggestions = []
    else:
        final = answer_text

    # Layer 3 (PR #83 → PR #84 → PR #86): 답변 사후 검증 + 구조화 사규 기준 주입.
    # validator user_incident_nodes 는 retriever 와 동기화 — question + rewritten
    # union (단독 question 만으로는 retriever 가 매칭한 노드를 못 잡을 때 있음).
    # chunks 는 contexts_raw 사용 — force_included_by_intent / is_universal_sop /
    # doc_title 메타 보존 (_balance_by_doc_kind 가 일부 drop 한 force 청크까지 복구).
    try:
        import sys as _sys
        from .citation_verifier import log_verification_result
        from .synthesis_validator import validate_and_repair_answer
        from .nexus_query_rewriter import nexus_classify_to_incident_nodes
        # PR-root-domain-coherence: 합성 단계 노드셋은 사용자 raw 질문의 결정적
        # 분류만 권위로 사용. LLM 재작성 분류 union 은 도메인 드리프트(예:
        # "협력사원" 재작성 시 "갑질/괴롭힘" 유입 → 괴롭힘 incident 노드)를 일으켜
        # STRUCTURED_INJECT·Domain-Lock·카테고리를 한꺼번에 오염시키므로 합성
        # 노드셋에서 제외. 검색 단계(L1_RPC) broad union 은 그대로 — "검색은 넓게,
        # 합성은 정합하게". 태거 내부 synonym 확장으로 약어 surfacing 회귀 없음.
        _user_nodes = sorted(set(nexus_classify_to_incident_nodes(question or "")))
        # PR-Phase-10.2-Fix-E: Domain-Lock 의 chunk matched 의존성 제거 위해
        # contexts_raw 의 모든 chunks 에 _user_incident_nodes 첨부. balanced
        # contexts 는 동일 dict 참조라 category_visual 0순위 Domain-Lock 이 활용.
        for _c in (contexts_raw or []):
            if isinstance(_c, dict):
                _c["_user_incident_nodes"] = list(_user_nodes)
        print(
            f"[chatbot:ask:validator_input] user_incident_nodes={_user_nodes} "
            f"chunks_raw={len(contexts_raw or [])} "
            f"chunks_balanced={len(contexts or [])}",
            file=_sys.stderr, flush=True,
        )
        # PR-Phase-11.2-Fix-H: Citation Verification Layer 통합.
        # 답변 인용 ↔ contexts_raw 의 doc_title 매칭 검증 + 로깅 (Phase-12
        # Strict Constraint 규칙 ② 준수 측정). 측정 layer 만 — 답변 흐름 불변.
        try:
            log_verification_result(final, contexts_raw or [])
        except Exception:
            pass
        final, _ = validate_and_repair_answer(
            final, chunks=contexts_raw, user_incident_nodes=_user_nodes,
        )
    except Exception as _val_e:
        # PR-C: silent → observed. fail-open 유지(raise 안 함). 4단 구조
        # 소실(format invariant 위반)을 stderr + Admin UI 로 가시화.
        import sys as _sys
        print(
            f"[synthesis:validator:DEGRADED] {type(_val_e).__name__}: {_val_e}",
            file=_sys.stderr, flush=True,
        )
        try:
            from .retriever import _signal_critical_error
            _signal_critical_error("validate_and_repair_answer", _val_e)
        except Exception:
            pass

    # PR-Quality-4: 사용자 질문 원문 quote 줄을 mechanical prepend.
    # LLM 외부에서 강제하여 paraphrase·변형 사고 원천 차단.
    # PR-Quality-4 hotfix: PII filter 의 false-positive ("안전관리 책임자"
    # 같은 일반 명사구가 [익명] 으로 변형) 가 quote 줄에 노출되는 사고 차단을
    # 위해 raw question 사용. LLM 입력·DB 로깅은 masked 그대로 유지(이중 보안)
    # 이며 quote 줄은 사용자 본인 화면에만 표시되므로 외부 노출 없음.
    final = _prepend_question_quote(final, question)

    # PR-Disambiguation-Phase1: 모호한 retrieval 의 경우 선택지 표시
    try:
        _ambig = detect_ambiguity(contexts or [], question=question)
        if _ambig.get("is_ambiguous"):
            _suggestion = format_choice_suggestion(_ambig.get("candidate_docs", []))
            if _suggestion:
                final = (final or "") + _suggestion
                print(
                    f"[disambiguation] ambiguous detected reason={_ambig.get('reason')} "
                    f"candidates={len(_ambig.get('candidate_docs', []))}",
                    file=sys.stderr, flush=True,
                )
    except Exception as _e_amb:
        print(f"[disambiguation] WARN skipped: {_e_amb}", file=sys.stderr, flush=True)

    elapsed = time.perf_counter() - t0

    # 질의 로그 (마스킹 후 본문만 저장, 원본은 즉시 폐기).
    # 베타 식별(env) · 임베딩 모델 버전 · SSO/RBAC 슬롯(null) 을 함께 기록.
    # insert 결과 id 는 사용자 피드백(👍/👎) 갱신용으로 호출자에 반환.
    query_log_id: int | None = None
    # multi-category chunk 의 categories 를 평탄화(중복 허용) — radar 가
    # 카테고리별 인용 빈도를 정확히 표시하기 위함. RPC 가 categories 를
    # 반환하지 않는 환경(db/09 미적용)에서는 빈 list 가 적재됨.
    hit_categories: list[str] = []
    for _c in contexts:
        _cats = _c.get("categories") or []
        if isinstance(_cats, list):
            hit_categories.extend([cat for cat in _cats if cat])
    _ask_payload = {
        "category":             category if category and category != "전체" else None,
        "query_masked":         masked,
        "is_critical":          detection.triggered,
        "critical_kind":        detection.kind,
        "hit_chunk_ids":        [c.get("chunk_id") for c in contexts if c.get("chunk_id")],
        "hit_categories":       hit_categories,
        "env":                  s.env_tag,
        "embed_model_version":  s.embed_model,
        "chat_provider":        used_provider,
        "chat_model_version":   used_model,
        "elapsed_ms":           int(elapsed * 1000),
        "used_fallback":        used_fallback,
        # user_id_hash / access_level 은 회사 SSO 도입 후 채움.
    }
    try:
        ins = supabase.table("query_logs").insert(_ask_payload).execute()
        if ins.data:
            query_log_id = ins.data[0].get("id")
        _log_query_logs_insert_success(
            query_log_id, list(_ask_payload.keys()), supabase=supabase,
        )
    except Exception as _e:
        _log_query_logs_insert_failure(
            list(_ask_payload.keys()), _e, supabase=supabase,
        )

    # PR-UI1: 후속질문 출처를 검색 문서 auto_query_examples 로 교체 (grounded).
    # critical 은 위에서 이미 []. 플래그 OFF / grounded 결과 없으면 기존 유지(회귀 안전).
    if ENABLE_GROUNDED_SUGGESTIONS and not detection.triggered:
        # grounded 결과 무조건 채택 — 비면 [] (ungrounded LLM 폴백 차단, 기만 방지)
        suggestions = grounded_suggestions(supabase, contexts, question)
    _emit("complete")
    final = _normalize_hr_dept_name(final)
    return Answer(
        text=final,
        is_critical=detection.triggered,
        critical_kind=detection.kind,
        contexts=contexts,
        masked_question=masked,
        thinking=effective_process,
        elapsed=elapsed,
        query_log_id=query_log_id,
        confidence=confidence,
        best_score=best_score,
        suggestions=suggestions,
    )


def _stall_guarded_stream(cli, model, user, cfg):
    """generate_content_stream 을 백그라운드 스레드+큐로 감싸 stall 시 abort.
    다음 chunk 를 _SYNTH_STREAM_CHUNK_TIMEOUT 초 이상 안 주거나 전체
    _SYNTH_OVERALL_TIMEOUT 초 초과 시 RuntimeError → 호출부가 친화 메시지로
    전환(분 단위 무한 hang 차단). 비스트리밍 ask() 의 deadline 가드와 정합.
    PR-fix-synth-timeout."""
    import queue as _q, threading as _th, time as _t
    _out = _q.Queue()
    _SENT = object()
    _errbox = {}
    def _pump():
        try:
            for _c in cli.models.generate_content_stream(
                model=model, contents=user, config=cfg,
            ):
                _out.put(_c)
        except Exception as _e:  # noqa: BLE001
            _errbox["e"] = _e
        finally:
            _out.put(_SENT)
    _th.Thread(target=_pump, daemon=True).start()
    _deadline = _t.monotonic() + _SYNTH_OVERALL_TIMEOUT
    while True:
        _remain = _deadline - _t.monotonic()
        if _remain <= 0:
            raise RuntimeError(
                f"Gemini 스트림 전체 {_SYNTH_OVERALL_TIMEOUT:.0f}초 초과 — 응답 지연 중단(stall guard)"
            )
        try:
            _item = _out.get(timeout=min(_SYNTH_STREAM_CHUNK_TIMEOUT, _remain))
        except _q.Empty:
            if _remain <= _SYNTH_STREAM_CHUNK_TIMEOUT:
                raise RuntimeError(
                    f"Gemini 스트림 전체 {_SYNTH_OVERALL_TIMEOUT:.0f}초 초과 — 응답 지연 중단(stall guard)"
                )
            raise RuntimeError(
                f"Gemini 스트림이 {_SYNTH_STREAM_CHUNK_TIMEOUT:.0f}초간 무응답 — 응답 지연 중단(stall guard)"
            )
        if _item is _SENT:
            if _errbox.get("e") is not None:
                raise _errbox["e"]
            return
        yield _item


def _gen_gemini_stream(system: str, user: str) -> Iterator[str]:
    """Gemini streaming generator. 청크 단위 yield. transient backoff 동일.

    Claude fallback provider 는 stream 미지원 — primary(Gemini) streaming 만.
    transient(429/503) 시 backoff 후 재시도. 최종 실패 시 raise — ask_stream
    이 ask() 동기 흐름으로 fallback.
    """
    from google import genai
    from google.genai import types
    s = settings()
    cli = genai.Client(api_key=s.gemini_api_key)

    # PR-CAG-Integration: stream 변형에도 동일 cached_content path 적용.
    _cag_cache_name: Optional[str] = None
    try:
        from .nexus_cag_manager import is_cag_enabled, get_cache_name
        if is_cag_enabled() and system == SYSTEM_PROMPT:
            _cag_cache_name = get_cache_name()
    except Exception as _cag_err:
        print(
            f"[cag] WARN integration skipped (stream): "
            f"{type(_cag_err).__name__}: {_cag_err}",
            file=sys.stderr, flush=True,
        )

    if _cag_cache_name:
        cfg = types.GenerateContentConfig(
            cached_content=_cag_cache_name,
            temperature=s.temperature,
            top_p=s.top_p,
        )
        print(
            f"[cag] stream using cached_content={_cag_cache_name}",
            file=sys.stderr, flush=True,
        )
    else:
        cfg = types.GenerateContentConfig(
            system_instruction=system,
            temperature=s.temperature,
            top_p=s.top_p,
        )

    last_err: Exception | None = None
    # PR-Add-Gemini-Cache-Monitoring: chunk 마다 usage_metadata 추적 → 종료 시 logs.
    last_um = None
    for attempt in range(_GEMINI_BACKOFF_ATTEMPTS):
        _yielded_any = False  # PR-B: 빈 완료(yield 0회) 감지용
        try:
            for chunk in _stall_guarded_stream(
                cli, s.chat_model, user, cfg,
            ):
                # usage_metadata 는 stream 종료 chunk 에 최종 값. 매 chunk 추적
                # 으로 중간 값도 cover (SDK 변경 시 안전).
                try:
                    _um = getattr(chunk, "usage_metadata", None)
                    if _um is not None:
                        last_um = _um
                except Exception:
                    pass
                # thought parts drop — SYSTEM_PROMPT 가 [검색 과정] 섹션을
                # text 본문에 포함시키므로 raw thought 는 더 이상 사용 안 함.
                try:
                    parts = chunk.candidates[0].content.parts
                except (AttributeError, IndexError, TypeError):
                    parts = None
                if parts:
                    for part in parts:
                        if getattr(part, "thought", False):
                            continue
                        text = getattr(part, "text", None) or ""
                        if text:
                            _yielded_any = True
                            yield text
                else:
                    text = getattr(chunk, "text", None) or ""
                    if text:
                        _yielded_any = True
                        yield text
            # stream 정상 종료 — cache hit 로그 (best-effort).
            try:
                if last_um is not None:
                    _cached = getattr(last_um, "cached_content_token_count", 0) or 0
                    _prompt = getattr(last_um, "prompt_token_count", 0) or 0
                    _hit_rate = (100.0 * _cached / _prompt) if _prompt else 0.0
                    print(
                        f"[chatbot:gemini_stream:cache] cached_tokens={_cached} "
                        f"prompt_tokens={_prompt} hit_rate={_hit_rate:.1f}% "
                        f"model={s.chat_model}",
                        flush=True,
                    )
            except Exception as _cache_log_err:
                print(
                    f"[chatbot:gemini_stream:cache] WARN log skipped: "
                    f"{type(_cache_log_err).__name__}",
                    flush=True,
                )
            if not _yielded_any:
                # PR-B 게이트 ②: 스트림이 본문 0건으로 정상 종료 → 빈 완료.
                raise EmptyCompletionError(
                    f"empty stream completion: model={s.chat_model}"
                )
            return
        except Exception as e:
            last_err = e
            if _is_transient(e) and attempt < _GEMINI_BACKOFF_ATTEMPTS - 1:
                wait = _GEMINI_BACKOFF_BASE * (2 ** attempt)
                print(
                    f"[Gemini stream backoff] attempt {attempt+1}/"
                    f"{_GEMINI_BACKOFF_ATTEMPTS} sleep {wait:.0f}s",
                    flush=True,
                )
                time.sleep(wait)
                continue
            raise
    if last_err is not None:
        raise last_err


def _stream_filter_process_marker(stream: Iterator[str]) -> Iterator[tuple[str, str]]:
    """raw stream → (kind, text) 튜플 stream 변환.

    yield 종류:
      ("raw", str)    — 모든 청크 (후처리용 raw 누적). 항상 발생
      ("chunk", str)  — 사용자 화면 표시용 본문 토큰. 다음 마커 등장 후
                        chunk yield 중단:
                          - SEARCH_PROCESS_MARKER ([검색 과정])
                          - SUGGESTIONS_MARKER    ([SUGGESTIONS])
                        둘 중 어느 마커든 먼저 등장한 시점 이후는 본문에
                        raw 노출되지 않도록 차단.

    구현: 가장 긴 마커 길이 - 1 만큼 buffer 보류해 마커 prefix 가 청크
    경계에서 잘리는 경우 안전 처리.
    """
    buf = ""
    seen_marker = False
    longest_marker = max(len(SEARCH_PROCESS_MARKER), len(SUGGESTIONS_MARKER))
    for chunk in stream:
        yield ("raw", chunk)
        if seen_marker:
            continue
        buf += chunk
        # 두 마커 중 더 빠른 (작은 idx) 위치를 찾아 split.
        idx_p = buf.find(SEARCH_PROCESS_MARKER)
        idx_s = buf.find(SUGGESTIONS_MARKER)
        candidates = [i for i in (idx_p, idx_s) if i >= 0]
        if candidates:
            cut = min(candidates)
            pre = buf[:cut]
            if pre:
                yield ("chunk", pre)
            seen_marker = True
            buf = ""
        else:
            safe = len(buf) - (longest_marker - 1)
            if safe > 0:
                yield ("chunk", buf[:safe])
                buf = buf[safe:]
    if buf and not seen_marker:
        yield ("chunk", buf)


def ask_stream(
    supabase: Any,
    *,
    question: str,
    category: str | None,
    extra_pii_terms: list[str] | None = None,
    progress_callback: Callable[[str, dict], None] | None = None,
    prev_turn: dict | None = None,
    hard_category: str | None = None,
) -> Iterator[tuple[str, Any]]:
    """Streaming 답변. yield 프로토콜:
        ("chunk", str)   — 점진 표시할 본문 토큰
        ("done", Answer) — 종료 + 후처리 적용된 최종 metadata

    Critical 트리거 / injection 차단 / streaming 예외 시 ask() 동기 흐름에
    위임하고 ("done", Answer) 단일 yield. enforce_structure 4단 답변 구조
    가 답변 전체 리포맷을 요구하기 때문.

    검수 회차(run_review) 등 답변 완성본만 필요한 호출자는 기존 ask() 사용.
    """
    s = settings()
    # PR-Phase-18.3.1: Option B — t0 를 진입부로 이동 (ask 와 동일 정합).
    t0 = time.perf_counter()

    # PR-Phase-17.1: Query Classifier Shadow Mode (ask_stream) — logging 전용.
    if ENABLE_QUERY_CLASSIFIER_LOGGING:
        try:
            # PR-Phase-19.2.3: 동의어 확장된 query 로 분류 (사내 약어 OOS 차단)
            classify_query(question, supabase=supabase)
        except Exception as _qc_e:
            print(f"[query_classifier:shadow] error: {_qc_e}",
                  file=sys.stderr, flush=True)

    def _emit(stage: str, payload: dict | None = None) -> None:
        if progress_callback is None:
            return
        try:
            progress_callback(stage, payload or {})
        except Exception:
            pass

    # injection 차단 — ask() 가 BLOCKED 분기 처리
    if _looks_like_injection(question):
        yield ("done", ask(
            supabase, question=question, category=category,
            extra_pii_terms=extra_pii_terms,
            progress_callback=progress_callback,
            prev_turn=prev_turn,
            hard_category=hard_category,
        ))
        return

    _emit("analyze")
    masked = mask_pii(question, extra_pii_terms or [])
    keywords = load_keywords(supabase)
    detection: CriticalDetection = detect(question, keywords)
    if not detection.triggered:
        detection = detect(masked, keywords)

    # critical 트리거 시 enforce_structure 가 답변 전체 리포맷 → streaming
    # 비활성. ask() 동기 흐름으로 fallback. 답변 한 번에 표시.
    if detection.triggered:
        ans = ask(
            supabase, question=question, category=category,
            extra_pii_terms=extra_pii_terms,
            progress_callback=progress_callback,
            prev_turn=prev_turn,
            hard_category=hard_category,
        )
        yield ("done", ans)
        return

    # PR-Ambiguity-Askback (streaming): 모호 bare 토큰 → 단일 ("done", Answer)
    # yield 후 return (합성·스트리밍 미진입). 위 critical 블록에서 triggered 는
    # 이미 ask() 위임 return → 여기 도달 = non-critical. flag OFF 기본.
    if ENABLE_AMBIGUITY_ASKBACK and not detection.triggered:
        _ambig = detect_bare_ambiguity(question)
        if _ambig:
            _ab_elapsed = time.perf_counter() - t0
            _log_ambiguity_askback(
                supabase, masked=masked, category=category, s=s,
                elapsed_ms=int(_ab_elapsed * 1000),
            )
            _emit("complete")
            yield ("done", Answer(
                text=_ambig["prompt"],
                is_critical=False,
                critical_kind=None,
                contexts=[],
                masked_question=masked,
                elapsed=_ab_elapsed,
                query_log_id=None,
                confidence="high",
                clarify_choices=_ambig["choices"],
            ))
            return

    # PR-Phase-18.2: FAQ Fast Path (streaming) — cache hit 시 단일 done.
    # 위 critical 블록에서 triggered 는 이미 위임 return → 여기 도달 = non-critical.
    # faq_cache_get 의 approved·is_critical=false 가드로 핫라인/미검토 답변 차단.
    if ENABLE_FAST_PATH:
        _faq_hit = faq_cache_get(question)
        if _faq_hit:
            _fp_elapsed = time.perf_counter() - t0
            _qid = _log_faq_cache_hit(
                supabase, masked=masked, category=category, s=s,
                elapsed_ms=int(_fp_elapsed * 1000),
            )
            _emit("complete")
            yield ("done", Answer(
                text=_faq_hit["answer_text"],
                is_critical=False,
                critical_kind=None,
                contexts=[],
                masked_question=masked,
                elapsed=_fp_elapsed,
                query_log_id=_qid,
                confidence="high",
            ))
            return

    # PR-Phase-18.5.2: OOS Fast Skip (streaming) — 단일 done yield.
    # 위 critical 블록(streaming 비활성)에서 triggered 는 이미 ask() 위임 후
    # return → 여기 도달 = non-critical. 가드는 ask() 와 동일 4중 정합.
    if ENABLE_OOS_ROUTING and not detection.triggered:
        _cls = classify_query(question, supabase=supabase)
        if _cls.get("category") == "out_of_scope":
            from .oos_router import gated_oos_decision
            if gated_oos_decision(supabase, question):
                from .oos_router import oos_routing_message
                # PR-Phase-18.3.1: Option B — ask 진입 t0 기준 전체 시간.
                _oos_elapsed = time.perf_counter() - t0
                _qid = _log_oos_skip(
                    supabase, masked=masked, category=category, s=s,
                    elapsed_ms=int(_oos_elapsed * 1000),
                )
                _emit("complete")
                yield ("done", Answer(
                    text=oos_routing_message(supabase),
                    is_critical=False,
                    critical_kind=None,
                    contexts=[],
                    masked_question=masked,
                    elapsed=_oos_elapsed,
                    query_log_id=_qid,
                    confidence="high",
                    is_oos=True,
                ))
                return
            # PR-OOS-Gate: override -> 정상 스트리밍 진행
            _log_oos_skip(
                supabase, masked=masked, category=category, s=s,
                elapsed_ms=int((time.perf_counter() - t0) * 1000),
                provider="oos_override",
            )

    # 일반 모드 — streaming 진행
    cats: list[str] | None
    if hard_category and not detection.triggered:
        cats = list({"공통", hard_category})
    elif category and category != "전체":
        cats = list({"공통", category})
    else:
        inferred = infer_categories(question)
        cats = list(set(inferred) | {"공통"}) if inferred else None

    # PR-Phase-18.3.1: t0 는 ask_stream 진입부에서 정의됨 — 의도적 미정의.
    _emit("search_start")
    pool_size = sum(_DOC_KIND_RATIOS.values()) + _POOL_SIZE_MARGIN
    # PR-UI-Sub-Stage-Visualization: hybrid_search 의 sub-stage emit pass.
    contexts_raw = hybrid_search(
        supabase, question=masked, raw_question=question, categories=cats,
        top_k=pool_size, progress_callback=progress_callback,
        hard_scope_category=(hard_category if not detection.triggered else None),
    )
    contexts = _balance_by_doc_kind(contexts_raw)
    _shadow_log_multi_facet(contexts)
    _shadow_log_multi_facet(contexts_raw, "raw")
    # Phase 1.5 → Phase 6: universal SOP 청크 ratio cap 우회 보존 + max cap.
    _balanced_ids = {c.get("chunk_id") for c in contexts if c.get("chunk_id")}
    _sop_preserved = 0
    for c in contexts_raw:
        if not c.get("is_universal_sop"):
            continue
        if _sop_preserved >= _UNIVERSAL_SOP_MAX_CHUNKS:
            break
        cid = c.get("chunk_id")
        if cid and cid not in _balanced_ids:
            contexts.append(c)
            _balanced_ids.add(cid)
            _sop_preserved += 1
    if _sop_preserved:
        import sys as _sys
        print(
            f"[chatbot:ask_stream] universal_sop_preserved={_sop_preserved}/{_UNIVERSAL_SOP_MAX_CHUNKS} "
            f"contexts_after_balance={len(contexts)}",
            file=_sys.stderr, flush=True,
        )
    # PR-Fix-DocKind-Preserve: ask_stream 도 동일 force-kind preserve.
    _kind_preserved: dict[str, int] = {k: 0 for k in _FORCE_KIND_MAX}
    for c in contexts_raw:
        kind = c.get("doc_kind")
        if kind not in _FORCE_KIND_MAX:
            continue
        if _kind_preserved[kind] >= _FORCE_KIND_MAX[kind]:
            continue
        cid = c.get("chunk_id")
        if cid and cid not in _balanced_ids:
            contexts.append(c)
            _balanced_ids.add(cid)
            _kind_preserved[kind] += 1
    if any(_kind_preserved.values()):
        import sys as _sys_fk2
        print(
            f"[chatbot:ask_stream] force_kind_preserved={_kind_preserved} "
            f"contexts_after_force_kind={len(contexts)}",
            file=_sys_fk2.stderr, flush=True,
        )
    _emit("search_done", {
        "doc_titles": [c.get("doc_title", "") for c in contexts if c.get("doc_title")],
        "doc_kind_counts": dict(Counter(c.get("doc_kind") for c in contexts)),
        "total": len(contexts),
    })

    # PR-Q1.4: 멀티 시그널 confidence (ask 동일 흐름).
    # streaming 경로는 critical 트리거되면 위쪽에서 ask() 동기 위임으로
    # 빠지므로 여기 도달했다는 건 is_critical=False. 그래도 명시 인자로 전달.
    from .confidence import calculate_confidence
    _scores = [float(c.get("score") or 0.0) for c in contexts]
    best_score = max(_scores) if _scores else 0.0
    confidence = calculate_confidence(masked, contexts)
    system_prompt_eff = _maybe_prefix_system_prompt(
        SYSTEM_PROMPT, is_critical=False, confidence=confidence,
    )

    # PR-A 게이트 ①: 검색 0건 → LLM 미호출 결정적 거절 (R-2/V-1 차단). flag OFF 기본.
    if ENABLE_NO_CONTEXT_GATE and not contexts:
        _emit("complete")
        yield ("done", Answer(
            text=SAFE_NO_CONTEXT,
            is_critical=False,
            critical_kind=None,
            contexts=[],
            masked_question=masked,
            elapsed=time.perf_counter() - t0,
            confidence="low",
        ))
        return

    user = build_user_prompt(masked, contexts, prev_turn=prev_turn)
    _emit("generate")

    used_provider = (s.chat_provider or "gemini").lower()
    used_model = s.chat_model
    used_fallback = False

    # PR-Quality-4: 사용자 질문 원문 quote 줄을 LLM 스트림 직전에 mechanical
    # 하게 먼저 yield. LLM 답변은 곧바로 ① 핵심 결론부터 시작하므로 본 줄과
    # 자연스럽게 이어진다 (system prompt [출력 구조] 가 이를 강제).
    # PR-Quality-4 hotfix: PII filter false-positive 차단을 위해 raw question
    # 사용 (LLM·DB 는 masked 유지, quote 줄만 사용자 본인 화면에 raw 표시).
    _q = (question or "").strip()
    quote_prefix = f"질문하신 내용: '{_q}'\n\n" if _q else ""
    if quote_prefix:
        yield ("chunk", quote_prefix)

    raw_full = ""
    try:
        for kind, val in _stream_filter_process_marker(
            _gen_gemini_stream(system_prompt_eff, user)
        ):
            if kind == "raw":
                raw_full += val
            elif kind == "chunk":
                yield ("chunk", val)
    except Exception as stream_err:
        # streaming 실패 → ask() 동기 fallback. 부분 답변 폐기, 처음부터 재시도.
        # 사용자에는 점진 표시되던 본문이 ask() 결과로 한 번에 갱신됨(app.py
        # placeholder 패턴이 final 로 단일 update).
        import sys as _sys
        print(f"[ask_stream → ask fallback] {stream_err}",
              file=_sys.stderr, flush=True)
        ans = ask(
            supabase, question=question, category=category,
            extra_pii_terms=extra_pii_terms,
            progress_callback=progress_callback,
            prev_turn=prev_turn,
            hard_category=hard_category,
        )
        yield ("done", ans)
        return

    # 후처리 — ask() 와 동일 순서
    answer_text, process_text_raw = _split_answer_and_process(raw_full)
    process_text = _format_process_section(process_text_raw)
    effective_process = process_text if s.show_thinking else ""
    # PR-Fun1: [SUGGESTIONS] 카드 분리. critical 흐름은 ask 동기로 위임된
    # 상태라 여기 도달은 is_critical=False — UI 단도 동일 분기.
    answer_text, suggestions = _split_suggestions(answer_text)
    # PR-UI1: 정상 스트리밍 경로(is_critical=False)도 grounded 출처로 교체.
    if ENABLE_GROUNDED_SUGGESTIONS:
        # grounded 결과 무조건 채택 — 비면 [] (ungrounded LLM 폴백 차단, 기만 방지)
        suggestions = grounded_suggestions(supabase, contexts, question)
    answer_text = _ensure_citation(answer_text, contexts)
    answer_text = _normalize_citation_block(answer_text, contexts)
    # Layer 3 (PR #83 → PR #84 → PR #86): 답변 사후 검증 + 구조화 사규 기준 주입.
    # ask() 와 동일 — question + rewritten union, chunks=contexts_raw.
    try:
        import sys as _sys
        from .citation_verifier import log_verification_result
        from .synthesis_validator import validate_and_repair_answer
        from .nexus_query_rewriter import nexus_classify_to_incident_nodes
        # PR-root-domain-coherence: 합성 단계 노드셋은 사용자 raw 질문의 결정적
        # 분류만 권위로 사용. LLM 재작성 분류 union 은 도메인 드리프트(예:
        # "협력사원" 재작성 시 "갑질/괴롭힘" 유입 → 괴롭힘 incident 노드)를 일으켜
        # STRUCTURED_INJECT·Domain-Lock·카테고리를 한꺼번에 오염시키므로 합성
        # 노드셋에서 제외. 검색 단계(L1_RPC) broad union 은 그대로 — "검색은 넓게,
        # 합성은 정합하게". 태거 내부 synonym 확장으로 약어 surfacing 회귀 없음.
        _user_nodes = sorted(set(nexus_classify_to_incident_nodes(question or "")))
        # PR-Phase-10.2-Fix-E: Domain-Lock 의 chunk matched 의존성 제거 위해
        # contexts_raw 의 모든 chunks 에 _user_incident_nodes 첨부. balanced
        # contexts 는 동일 dict 참조라 category_visual 0순위 Domain-Lock 이 활용.
        for _c in (contexts_raw or []):
            if isinstance(_c, dict):
                _c["_user_incident_nodes"] = list(_user_nodes)
        print(
            f"[chatbot:ask_stream:validator_input] user_incident_nodes={_user_nodes} "
            f"chunks_raw={len(contexts_raw or [])} "
            f"chunks_balanced={len(contexts or [])}",
            file=_sys.stderr, flush=True,
        )
        # PR-Phase-11.2-Fix-H: Citation Verification Layer 통합 (ask_stream).
        try:
            log_verification_result(answer_text, contexts_raw or [])
        except Exception:
            pass
        answer_text, _ = validate_and_repair_answer(
            answer_text, chunks=contexts_raw, user_incident_nodes=_user_nodes,
        )
    except Exception as _val_e:
        # PR-C: silent → observed. fail-open 유지(raise 안 함). 4단 구조
        # 소실(format invariant 위반)을 stderr + Admin UI 로 가시화.
        import sys as _sys
        print(
            f"[synthesis:validator:DEGRADED] {type(_val_e).__name__}: {_val_e}",
            file=_sys.stderr, flush=True,
        )
        try:
            from .retriever import _signal_critical_error
            _signal_critical_error("validate_and_repair_answer", _val_e)
        except Exception:
            pass
    # PR-Quality-4: streaming 중 quote_prefix 를 이미 yield 했으므로 최종
    # Answer.text 에도 동일하게 prepend — 화면 placeholder 갱신 시 누락 방지.
    # hotfix: raw question 사용 (위 quote_prefix 와 동일 기준).
    answer_text = _prepend_question_quote(answer_text, question)

    elapsed = time.perf_counter() - t0

    # query_logs INSERT — ask() 와 동일 페이로드
    query_log_id: int | None = None
    hit_categories: list[str] = []
    for _c in contexts:
        _cats = _c.get("categories") or []
        if isinstance(_cats, list):
            hit_categories.extend([cat for cat in _cats if cat])
    _stream_payload = {
        "category":             category if category and category != "전체" else None,
        "query_masked":         masked,
        "is_critical":          False,
        "critical_kind":        None,
        "hit_chunk_ids":        [c.get("chunk_id") for c in contexts if c.get("chunk_id")],
        "hit_categories":       hit_categories,
        "env":                  s.env_tag,
        "embed_model_version":  s.embed_model,
        "chat_provider":        used_provider,
        "chat_model_version":   used_model,
        "elapsed_ms":           int(elapsed * 1000),
        "used_fallback":        used_fallback,
    }
    try:
        ins = supabase.table("query_logs").insert(_stream_payload).execute()
        if ins.data:
            query_log_id = ins.data[0].get("id")
        _log_query_logs_insert_success(
            query_log_id, list(_stream_payload.keys()), supabase=supabase,
        )
    except Exception as _e:
        _log_query_logs_insert_failure(
            list(_stream_payload.keys()), _e, supabase=supabase,
        )

    # PR-Disambiguation-Phase1: 모호한 retrieval 의 경우 선택지 표시 (done Answer 에 반영)
    try:
        _ambig = detect_ambiguity(contexts or [], question=question)
        if _ambig.get("is_ambiguous"):
            _suggestion = format_choice_suggestion(_ambig.get("candidate_docs", []))
            if _suggestion:
                answer_text = (answer_text or "") + _suggestion
                print(
                    f"[disambiguation] ambiguous detected reason={_ambig.get('reason')} "
                    f"candidates={len(_ambig.get('candidate_docs', []))}",
                    file=sys.stderr, flush=True,
                )
    except Exception as _e_amb:
        print(f"[disambiguation] WARN skipped: {_e_amb}", file=sys.stderr, flush=True)

    _emit("complete")
    answer_text = _normalize_hr_dept_name(answer_text)
    yield ("done", Answer(
        text=answer_text,
        is_critical=False,
        critical_kind=None,
        contexts=contexts,
        masked_question=masked,
        thinking=effective_process,
        elapsed=elapsed,
        query_log_id=query_log_id,
        confidence=confidence,
        best_score=best_score,
        suggestions=suggestions,
    ))


def get_avg_latency_seconds(
    supabase: Any, *, sample_size: int = 100, fallback: int = 10,
) -> int:
    """query_logs.elapsed_ms 최근 N건의 P50(중앙값) 을 초 단위로 반환.

    답변 대기 UX 의 "평균 약 N초" 표시용. 평균 대신 P50 을 쓰는 이유는
    backoff/timeout outlier 가 평균을 왜곡하기 때문. 데이터 < 5건이거나
    조회 에러면 fallback(기본 10초). 호출자(app.py) 가 session 단위
    캐시(5분 TTL) 권장 — 매 답변 호출마다 SELECT 하지 않게.

    실제 컬럼명(스키마): elapsed_ms / ts (db/01 + db/07).
    """
    try:
        result = (
            supabase.table("query_logs")
                    .select("elapsed_ms")
                    .order("ts", desc=True)
                    .limit(sample_size)
                    .execute()
        )
        rows = result.data or []
        latencies = [
            r["elapsed_ms"] for r in rows
            if r.get("elapsed_ms") and r["elapsed_ms"] > 0
        ]
        if len(latencies) < 5:
            return fallback
        latencies.sort()
        median_ms = latencies[len(latencies) // 2]
        return max(3, round(median_ms / 1000))
    except Exception:
        return fallback


def record_feedback(supabase: Any, *, query_log_id: int,
                    feedback: int, comment: str | None = None) -> bool:
    """사용자 피드백(👍=1 / 👎=-1) 을 query_logs 에 기록. 성공 여부 반환."""
    if feedback not in (-1, 1):
        return False
    try:
        payload: dict = {"feedback": feedback}
        if comment:
            payload["feedback_comment"] = comment[:500]
        supabase.table("query_logs").update(payload).eq("id", query_log_id).execute()
        return True
    except Exception:
        return False
