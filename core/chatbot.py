"""챗봇 엔진 — 검색→Gemini 생성→후처리(출처/심각모드)→로깅.

운영 시점 최신 안정 모델은 NEXUS_CHAT_MODEL 환경변수로 추상화한다.
temperature/top_p 는 환각 제어를 위해 0/0.1 고정이 기본값이며,
필요한 경우에만 환경변수로 미세조정한다.
"""

from __future__ import annotations

import os
import re
import time
from collections import Counter, OrderedDict
from dataclasses import dataclass, field
from typing import Any, Callable

from .config import settings, load_hotlines
from .critical_mode import CriticalDetection, detect, enforce_structure, load_keywords
from .pii_filter import mask_pii
from .prompts import SYSTEM_PROMPT, build_user_prompt
from .retriever import hybrid_search


# SYSTEM_PROMPT 가 강제하는 [검색 과정] 섹션 마커. LLM 응답에서 본문과
# 검토 과정을 분리하는 anchor. 마커 없으면 process 는 빈 문자열로 간주
# 하고 사용자 화면에서 expander 자체를 숨긴다 (마커 누락 fallback).
SEARCH_PROCESS_MARKER = "[검색 과정]"


def _split_answer_and_process(raw: str) -> tuple[str, str]:
    """LLM 응답에서 [검색 과정] 섹션 분리.

    마커 없으면 process 는 빈 문자열 → 사용자 화면 expander 자동 숨김.
    """
    if SEARCH_PROCESS_MARKER not in raw:
        return raw.strip(), ""
    head, tail = raw.split(SEARCH_PROCESS_MARKER, 1)
    return head.rstrip(), tail.strip()


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


# 권장 행동 섹션 헤더 (시스템 프롬프트가 강제하는 출력 구조 ④) 의 markdown
# 패턴. 답변 내 일반 numbered list (예: 사규 인용 '1. 정의 2. 적용범위') 가
# 권장 행동으로 잘못 추출되지 않도록 섹션 본문에서만 추출.
# 종료는 다음 섹션(⑤/출처/역질문/[참조/---) 또는 문서 끝(\Z). re.M 의 $ 는
# line-end 라 lookahead 가 0자 body 로 끝나는 결함 → \Z 로 대체.
_RE_ACTION_SECTION = re.compile(
    r"(?:^|\n)\s*(?:④|##?#?\s*권장\s*행동|\*\*?권장\s*행동\*\*?|3\.\s*즉시\s*실행)"
    r"([\s\S]*?)(?=\n\s*(?:⑤|##?#?\s*출처|##?#?\s*역질문|\[참조|---)|\Z)",
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
    for attempt in range(_GEMINI_BACKOFF_ATTEMPTS):
        _ex = ThreadPoolExecutor(max_workers=1)
        try:
            _fut = _ex.submit(cli.models.generate_content,
                              model=s.chat_model, contents=user, config=cfg)
            res = _fut.result(timeout=60.0)
            break
        except _Timeout as e:
            last_err = RuntimeError("Gemini 호출이 60초 내 응답하지 않았습니다.")
            if attempt < _GEMINI_BACKOFF_ATTEMPTS - 1:
                time.sleep(_GEMINI_BACKOFF_BASE * (2 ** attempt))
                continue
            raise last_err from e
        except Exception as e:
            last_err = e
            if _is_transient(e) and attempt < _GEMINI_BACKOFF_ATTEMPTS - 1:
                wait = _GEMINI_BACKOFF_BASE * (2 ** attempt)
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
    return text, "", s.chat_model


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

    kwargs: dict = {
        "model": s.claude_model,
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

    return ("".join(text_parts).strip(),
            "",
            s.claude_model)


_PROVIDER_FUNCS = {"gemini": _gen_gemini, "claude": _gen_claude}


def _gen(system: str, user: str, *, include_thinking: bool) -> tuple[str, str, str, str, bool]:
    """Provider dispatcher. Returns (text, thinking, provider, model_id, used_fallback).

    primary 가 transient(503/429) 실패하면 fallback 으로 1회 자동 전환.
    비전이성 에러(인증·인풋 문제)는 즉시 raise.

    used_fallback: primary 가 transient 실패 후 fallback 분기에서 응답을 받았는지.
    """
    s = settings()
    primary = (s.chat_provider or "gemini").lower()
    fallback = (s.chat_fallback_provider or "").lower()

    chain: list[str] = [primary]
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
            if not _is_transient(e):
                raise
            # transient → 다음 provider 시도. 다음 시도부터는 fallback 분기.
            used_fallback = True
            continue
    if last_err is not None:
        raise last_err
    raise RuntimeError("No chat provider configured")


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
    ("rule", 3),
    ("penalty", 2),
    ("case", 2),
])


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
    result: list[dict] = []
    for kind, n in ratios.items():
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

    # Prompt injection 1차 필터 — LLM 호출 전 차단으로 토큰 비용·로깅 노이즈 절감.
    # 매치되면 LLM 미호출 + critical 트리거 안 함 + 별도 로그만 남기고 거절.
    if _looks_like_injection(question):
        try:
            supabase.table("query_logs").insert({
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
            }).execute()
        except Exception as _e:
            import sys as _sys
            print(f"[query_logs INSERT failed — blocked] {_e}", file=_sys.stderr, flush=True)
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

    # 카테고리 필터: 단일 카테고리 선택 시 ['공통', 선택] 합집합으로 폭을 약간 넓힘.
    cats: list[str] | None
    if category and category != "전체":
        cats = list({"공통", category})
    else:
        cats = None

    # 심각 사안일 때는 안전 카테고리도 우선적으로 합집합에 포함
    if detection.triggered:
        if detection.kind == "safety":
            cats = list(set((cats or []) + ["안전", "공통"]))
        elif detection.kind == "harassment":
            cats = list(set((cats or []) + ["공통"]))

    t0 = time.perf_counter()

    _emit("search_start")
    # doc_kind 분산: 큰 풀에서 검색 후 비율로 잘라냄. 한 doc_kind 가 풀에서
    # 우세할 때 다른 kind 가 풀에서 빠질 위험 완화 위해 합계 + 여유분 3.
    pool_size = sum(_DOC_KIND_RATIOS.values()) + 3
    contexts_raw = hybrid_search(
        supabase, question=masked, categories=cats, top_k=pool_size,
    )
    contexts = _balance_by_doc_kind(contexts_raw)
    _emit("search_done", {
        "doc_titles": [c.get("doc_title", "") for c in contexts if c.get("doc_title")],
        "doc_kind_counts": dict(Counter(c.get("doc_kind") for c in contexts)),
        "total": len(contexts),
    })

    user = build_user_prompt(masked, contexts, prev_turn=prev_turn)
    _emit("generate")
    raw, _legacy_thinking, used_provider, used_model, used_fallback = _gen(
        SYSTEM_PROMPT, user, include_thinking=False,
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
    else:
        final = answer_text

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
    try:
        ins = supabase.table("query_logs").insert({
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
        }).execute()
        if ins.data:
            query_log_id = ins.data[0].get("id")
    except Exception as _e:
        import sys as _sys
        print(f"[query_logs INSERT failed] {_e}", file=_sys.stderr, flush=True)

    _emit("complete")
    return Answer(
        text=final,
        is_critical=detection.triggered,
        critical_kind=detection.kind,
        contexts=contexts,
        masked_question=masked,
        thinking=effective_process,
        elapsed=elapsed,
        query_log_id=query_log_id,
    )


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
