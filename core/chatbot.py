"""챗봇 엔진 — 검색→Gemini 생성→후처리(출처/심각모드)→로깅.

운영 시점 최신 안정 모델은 NEXUS_CHAT_MODEL 환경변수로 추상화한다.
temperature/top_p 는 환각 제어를 위해 0/0.1 고정이 기본값이며,
필요한 경우에만 환경변수로 미세조정한다.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any

from .config import settings, load_hotlines
from .critical_mode import CriticalDetection, detect, enforce_structure, load_keywords
from .pii_filter import mask_pii
from .prompts import SYSTEM_PROMPT, build_user_prompt
from .retriever import hybrid_search


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


def _is_transient(e: Exception) -> bool:
    """503/429/RESOURCE_EXHAUSTED 류 모델 트래픽 폭주 신호 식별.
    primary 가 이 케이스로 실패하면 fallback provider 로 1회 전환 가능."""
    msg = str(e).lower()
    return any(h.lower() in msg for h in _TRANSIENT_HINTS)


def _gen_gemini(system: str, user: str, *, include_thinking: bool) -> tuple[str, str, str]:
    """Gemini 호출. Returns (text, thinking, model_id)."""
    from google import genai
    from google.genai import types
    s = settings()
    cli = genai.Client(api_key=s.gemini_api_key)

    try:
        if include_thinking:
            cfg = types.GenerateContentConfig(
                system_instruction=system,
                temperature=s.temperature,
                top_p=s.top_p,
                thinking_config=types.ThinkingConfig(include_thoughts=True),
            )
        else:
            cfg = types.GenerateContentConfig(
                system_instruction=system,
                temperature=s.temperature,
                top_p=s.top_p,
            )
    except Exception:
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
    for attempt in range(3):
        _ex = ThreadPoolExecutor(max_workers=1)
        try:
            _fut = _ex.submit(cli.models.generate_content,
                              model=s.chat_model, contents=user, config=cfg)
            res = _fut.result(timeout=60.0)
            break
        except _Timeout as e:
            last_err = RuntimeError("Gemini 호출이 60초 내 응답하지 않았습니다.")
            if attempt < 2:
                time.sleep(1.5 * (2 ** attempt))
                continue
            raise last_err from e
        except Exception as e:
            last_err = e
            if _is_transient(e) and attempt < 2:
                time.sleep(1.5 * (2 ** attempt))   # 1.5s → 3s
                continue
            raise
        finally:
            _ex.shutdown(wait=False, cancel_futures=True)
    if res is None and last_err is not None:
        raise last_err

    thinking_parts: list[str] = []
    text_parts: list[str] = []
    try:
        for part in res.candidates[0].content.parts:
            if getattr(part, "thought", False):
                thinking_parts.append(part.text or "")
            else:
                text_parts.append(part.text or "")
    except Exception:
        text_parts = [res.text or ""]

    text = "".join(text_parts).strip() or (res.text or "").strip()
    thinking = "".join(thinking_parts).strip()
    return text, thinking, s.chat_model


def _gen_claude(system: str, user: str, *, include_thinking: bool) -> tuple[str, str, str]:
    """Claude 호출. Returns (text, thinking, model_id).

    Opus 4.7 기준:
    - temperature/top_p/top_k 사용 불가 (400). 프롬프트로 결정성 제어.
    - thinking 은 adaptive only. display='summarized' 로 사용자 노출 활성.
    - effort 는 output_config 안에 넣음 (top-level 아님).
    """
    import anthropic
    s = settings()
    if not s.anthropic_api_key:
        raise RuntimeError("ANTHROPIC_API_KEY 가 설정되지 않았습니다.")
    # 60초 timeout — anthropic SDK 기본은 10분이라 사용자 무한 대기 위험.
    # Opus 4.7 thinking + 16K max_tokens 케이스도 보통 30초 내 완료.
    cli = anthropic.Anthropic(api_key=s.anthropic_api_key, timeout=60.0)

    kwargs: dict = {
        "model": s.claude_model,
        "max_tokens": 16000,
        "system": system,
        "messages": [{"role": "user", "content": user}],
    }
    if s.claude_effort:
        kwargs["output_config"] = {"effort": s.claude_effort}
    if include_thinking:
        # display='summarized' 가 없으면 Opus 4.7 default('omitted') 로 인해 thinking
        # 텍스트가 비어 표시됨. 베타 답변 신뢰성 검증을 위해 명시적으로 활성화.
        kwargs["thinking"] = {"type": "adaptive", "display": "summarized"}
    else:
        kwargs["thinking"] = {"type": "disabled"}

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

    thinking_parts: list[str] = []
    text_parts: list[str] = []
    for block in res.content:
        if block.type == "thinking":
            thinking_parts.append(getattr(block, "thinking", "") or "")
        elif block.type == "text":
            text_parts.append(getattr(block, "text", "") or "")

    return ("".join(text_parts).strip(),
            "".join(thinking_parts).strip(),
            s.claude_model)


_PROVIDER_FUNCS = {"gemini": _gen_gemini, "claude": _gen_claude}


def _gen(system: str, user: str, *, include_thinking: bool) -> tuple[str, str, str, str]:
    """Provider dispatcher. Returns (text, thinking, provider, model_id).

    primary 가 transient(503/429) 실패하면 fallback 으로 1회 자동 전환.
    비전이성 에러(인증·인풋 문제)는 즉시 raise.
    """
    s = settings()
    primary = (s.chat_provider or "gemini").lower()
    fallback = (s.chat_fallback_provider or "").lower()

    chain: list[str] = [primary]
    if fallback and fallback != primary:
        chain.append(fallback)

    last_err: Exception | None = None
    for prov in chain:
        fn = _PROVIDER_FUNCS.get(prov)
        if fn is None:
            continue
        # fallback=claude 인데 ANTHROPIC_API_KEY 미설정이면 조용히 skip
        if prov == "claude" and not s.anthropic_api_key:
            continue
        try:
            text, thinking, model_id = fn(system, user, include_thinking=include_thinking)
            return text, thinking, prov, model_id
        except Exception as e:
            last_err = e
            if not _is_transient(e):
                raise
            # transient → 다음 provider 시도
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


def _extract_action_items(answer: str) -> list[str]:
    return [m.group(1).strip() for m in _RE_ACTION_BLOCK.finditer(answer)][:3]


def ask(
    supabase: Any,
    *,
    question: str,
    category: str | None,
    extra_pii_terms: list[str] | None = None,
) -> Answer:
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
                "env":                 s.env_tag,
                "embed_model_version": s.embed_model,
                "chat_provider":       "blocked",
                "chat_model_version":  None,
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

    contexts = hybrid_search(supabase, question=masked, categories=cats, top_k=s.top_k)

    user = build_user_prompt(masked, contexts)
    raw, thinking, used_provider, used_model = _gen(
        SYSTEM_PROMPT, user, include_thinking=s.show_thinking,
    )
    raw = _ensure_citation(raw, contexts)

    if detection.triggered:
        actions = _extract_action_items(raw)
        hotlines = load_hotlines(supabase)
        final = enforce_structure(
            base_answer=raw,
            kind=detection.kind or "safety",
            action_items=actions,
            hotlines=hotlines,
        )
    else:
        final = raw

    elapsed = time.perf_counter() - t0

    # 질의 로그 (마스킹 후 본문만 저장, 원본은 즉시 폐기).
    # 베타 식별(env) · 임베딩 모델 버전 · SSO/RBAC 슬롯(null) 을 함께 기록.
    # insert 결과 id 는 사용자 피드백(👍/👎) 갱신용으로 호출자에 반환.
    query_log_id: int | None = None
    try:
        ins = supabase.table("query_logs").insert({
            "category":             category if category and category != "전체" else None,
            "query_masked":         masked,
            "is_critical":          detection.triggered,
            "critical_kind":        detection.kind,
            "hit_chunk_ids":        [c.get("chunk_id") for c in contexts if c.get("chunk_id")],
            "env":                  s.env_tag,
            "embed_model_version":  s.embed_model,
            "chat_provider":        used_provider,
            "chat_model_version":   used_model,
            # user_id_hash / access_level 은 회사 SSO 도입 후 채움.
        }).execute()
        if ins.data:
            query_log_id = ins.data[0].get("id")
    except Exception as _e:
        import sys as _sys
        print(f"[query_logs INSERT failed] {_e}", file=_sys.stderr, flush=True)

    return Answer(
        text=final,
        is_critical=detection.triggered,
        critical_kind=detection.kind,
        contexts=contexts,
        masked_question=masked,
        thinking=thinking,
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
