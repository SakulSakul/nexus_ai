"""PR-Doc-Router: Semantic Doc Router — 의도→문서 매핑의 구조적 해법.

배경 (2026-07-21 사쿨 확정 — "두더지잡기 금지, 구조적으로 fix"):
- "중국 리서치 업체가 인터뷰에 응해주면 시간당 50만원 사례" 류 질문이
  (a) OOS 게이트에서 paraphrase 6개 중 5개 오차단,
  (b) 게이트를 통과해도 정답 문서 (CSR) 대외출강 운영 지침 미회수 →
      인접 사규(CSR경영방침/징계기준)로 프레임 어긋난 답변.
- 근본원인: 의도→문서 연결이 전부 수작업 substring 사전에 의존 —
  _NEXUS_NL_TO_INCIDENT_NODES trigger / L3 whitelist / auto_keywords 점수 /
  CATEGORY_KEYWORDS. 사전에 없는 새 표현("인터뷰", "리서치", "사례 하겠다고")
  이 오면 전 레이어가 동시에 뚫린다 (같은 클래스의 장치이기 때문).
- 구조 해법: **닫힌 목록 의미 선택.** active 사규 전체 카탈로그(제목+키워드)를
  프롬프트에 넣고 LLM 이 관련 문서 0~3개 + scope 를 JSON 으로 1회 판정.
  표현 다양성은 LLM 의미 매칭이 흡수하고, 닫힌 목록 선택이라 환각 불가.
  OOS 판정도 카탈로그를 보면서 내리므로 근거가 생긴다 — "목록의 어떤 문서와도
  무관 + 열거된 행정 카테고리 해당"일 때만 out, 애매하면 in (비대칭 비용:
  컴플라이언스 질문 오차단 비용 >> 잡담이 검색 타는 비용).

안전 도입 (하우스 스타일 — faq_cache / oos_router flag 선례):
- ENABLE_DOC_ROUTER 기본 false → 머지 시 ZERO regression.
- 실패는 절대 raise 안 함 — fail-open {"ok": False, "scope": "in",
  "doc_ids": []} = 기존 파이프라인 그대로. helper_health.record("doc_router")
  로 silent 장애 가시화 (FMEA R1 선례).
- 질문 단위 in-process 캐시 — OOS 게이트(oos_router.gated_oos_decision)와
  retriever(hybrid_search Layer R)가 같은 질문에 각각 호출해도 LLM 1회.
- 카탈로그 캐시 TTL 300s — 문서 추가/비활성화는 admin 작업 후 5분 내 반영.

호출자:
- core/oos_router.py:gated_oos_decision — OOS 구제 1차 판정.
- core/retriever.py:hybrid_search Layer R — 선택 doc force-include union.
"""
from __future__ import annotations

import json
import re
import sys
import threading
import time
from typing import Any

from . import helper_health
from .config import get_secret, settings

# ── Feature flag (기본 OFF — secrets 의 ENABLE_DOC_ROUTER="true" 로 활성화) ──
ENABLE_DOC_ROUTER: bool = (
    get_secret("ENABLE_DOC_ROUTER", "false").lower() == "true"
)

# reranker/judge 와 동일 계열 기본 모델 (JSON structured output 검증된 경로).
_ROUTER_MODEL: str = get_secret(
    "DOC_ROUTER_MODEL",
    get_secret("NEXUS_RERANK_MODEL", "gemini-3.1-flash-lite"),
)
_ROUTER_TEMPERATURE: float = 0.0
_ROUTER_MAX_OUTPUT_TOKENS: int = 512
_ROUTER_TIMEOUT_S: float = 6.0     # reranker 와 동일 예산 — 초과 시 fail-open
_MAX_SELECTED_DOCS: int = 3

# ── 캐시 ────────────────────────────────────────────────────────────
_CATALOG_TTL_S: float = 300.0
_ROUTE_CACHE_MAX: int = 64

_lock = threading.Lock()
_catalog_cache: dict = {"ts": 0.0, "docs": []}
_route_cache: dict[str, dict] = {}          # question -> result (insertion order)


_SYSTEM_TEXT = """당신은 신세계디에프 사규 챗봇 DF COMPASS 의 문서 라우터입니다.
사용자 질문을 읽고, 아래 [사규 카탈로그]에서 답변 근거가 될 수 있는 문서를
0~3개 고르고, 질문이 사규 챗봇 범위(scope) 안인지 판정합니다.

[판단 원칙 — 매우 중요]
1. 표현이 아니라 **의도**로 판단하세요. 사용자는 사규 용어를 모릅니다.
   - "외부 업체가 돈을 주며 인터뷰/자문/강연을 요청" → 대외출강·외부강의,
     금품 수수, 이해충돌 관련 문서.
   - "거래처가 선물을 보냈다" → 윤리·클린 관련 문서.
   - "이런 걸 해도 되는지" 류의 행동 판단 질문은 거의 항상 사규 관련입니다.
2. 확신이 없어도 관련 **가능성**이 있으면 고르세요 (0~3개). 챗봇이 검증합니다.
3. scope="out" 은 다음에 **명확히** 해당하고 관련 문서가 0개일 때만:
   IT 시스템 장애(VPN/PC/네트워크), 시설·비품 예약(회의실/명함/주차),
   개인 인사 행정(휴가·연차·근태·인사평가·연봉·승진·채용),
   타사 사규, 잡담·테스트·일반상식(날씨/인사말).
4. 다음은 **항상 scope="in"** 입니다:
   외부 기관·업체·개인의 접촉/제안/금전·선물·향응 제공, 임직원 행동의
   허용 여부 판단, 신고·보고·위반·사고·피해 관련, 징계·윤리·보안 관련.
5. 애매하면 scope="in" (보수적 default — 사규 질문을 잘못 차단하는 비용이
   잡담을 통과시키는 비용보다 훨씬 큽니다).

[출력 — JSON only]
{"scope": "in" 또는 "out", "selected": [{"idx": <카탈로그 번호>, "why": "<한 줄 근거>"}]}
선택 없음이면 "selected": []. 다른 텍스트 금지."""


def _load_catalog(supabase: Any) -> list[dict]:
    """active 사규 카탈로그 (id/title/doc_kind/auto_keywords) — TTL 캐시.

    실패 시 빈 리스트 (호출자 fail-open). L2.5(_compute_v3_matches) 가 매 query
    동일 테이블을 fetch 하는 선례가 있어 부하 신규 증가는 없고, TTL 캐시로
    오히려 감소.
    """
    now = time.time()
    with _lock:
        if _catalog_cache["docs"] and now - _catalog_cache["ts"] < _CATALOG_TTL_S:
            return _catalog_cache["docs"]
    try:
        res = (
            supabase.table("nexus_documents")
            .select("id, title, doc_kind, auto_keywords")
            .eq("status", "active")
            .execute()
        )
        docs = [d for d in (res.data or []) if d.get("id") and d.get("title")]
        docs.sort(key=lambda d: str(d.get("title") or ""))  # 결정적 idx 부여
        with _lock:
            _catalog_cache["ts"] = now
            _catalog_cache["docs"] = docs
        return docs
    except Exception as e:
        print(
            f"[doc_router:catalog] FAILED: {type(e).__name__}: {e}",
            file=sys.stderr, flush=True,
        )
        return []


def _build_catalog_lines(docs: list[dict]) -> str:
    """카탈로그 → 프롬프트 라인. '<idx>. <title> — 키워드: a, b, c' 형식.

    auto_keywords 는 상위 5개만 (프롬프트 길이 절제 — 문서 수십 개 × 5 키워드
    ≈ 2~3K tokens, Flash-Lite 컨텍스트 대비 무시 가능).
    """
    lines: list[str] = []
    for i, d in enumerate(docs):
        kws = [
            str(k).strip() for k in (d.get("auto_keywords") or [])[:5]
            if isinstance(k, str) and str(k).strip()
        ]
        kw_part = f" — 키워드: {', '.join(kws)}" if kws else ""
        lines.append(f"{i}. {d.get('title')}{kw_part}")
    return "\n".join(lines)


def _parse_router_response(text: str, docs: list[dict]) -> dict | None:
    """LLM JSON 응답 → 검증된 결과 dict. 파싱/검증 실패 시 None (fail-open).

    닫힌 목록 강제: idx 가 카탈로그 범위 밖이면 무시 (환각 차단).
    """
    if not text:
        return None
    # 방어: 코드펜스/전후 텍스트 섞임 대비 첫 JSON object 추출.
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    scope = str(data.get("scope") or "").strip().lower()
    if scope not in ("in", "out"):
        return None
    selected = data.get("selected")
    if not isinstance(selected, list):
        selected = []
    doc_ids: list[str] = []
    titles: list[str] = []
    reasons: list[str] = []
    seen: set = set()
    # cap 은 "유효 항목 3개" 기준 — 검증 전 pre-slice 를 하면 무효 항목
    # (범위 밖 idx 등) 이 예산을 소모해 유효 선택이 잘린다 (단위테스트 검출).
    # 입력 자체는 max_output_tokens 로 유계 + 방어 상한 32.
    for item in selected[:32]:
        if not isinstance(item, dict):
            continue
        idx = item.get("idx")
        # bool 은 int 서브클래스 — {"idx": true} 가 docs[1] 로 새는 것 차단.
        if (not isinstance(idx, int) or isinstance(idx, bool)
                or idx < 0 or idx >= len(docs)):
            continue  # 닫힌 목록 밖 — 무시
        d = docs[idx]
        if d["id"] in seen:
            continue
        seen.add(d["id"])
        doc_ids.append(d["id"])
        titles.append(str(d.get("title") or ""))
        reasons.append(str(item.get("why") or "")[:120])
        if len(doc_ids) >= _MAX_SELECTED_DOCS:
            break
    return {"scope": scope, "doc_ids": doc_ids, "titles": titles, "reasons": reasons}


def _call_llm(question: str, docs: list[dict]) -> dict | None:
    """Gemini 1회 호출 (timeout 스레드 가드) → 파싱 결과 or None."""
    try:
        from google import genai
        from google.genai import types
    except Exception:
        return None
    s = settings()
    if not s.gemini_api_key:
        return None

    holder: dict = {}

    def _worker() -> None:
        try:
            cli = genai.Client(api_key=s.gemini_api_key)
            cfg = types.GenerateContentConfig(
                system_instruction=_SYSTEM_TEXT,
                temperature=_ROUTER_TEMPERATURE,
                max_output_tokens=_ROUTER_MAX_OUTPUT_TOKENS,
                response_mime_type="application/json",
            )
            prompt = (
                f"[사규 카탈로그]\n{_build_catalog_lines(docs)}\n\n"
                f"[사용자 질문]\n{question}"
            )
            res = cli.models.generate_content(
                model=_ROUTER_MODEL, contents=prompt, config=cfg,
            )
            # nexus_reranker._extract_response_text 와 동일 추출 패턴.
            parts: list[str] = []
            try:
                for part in res.candidates[0].content.parts:  # type: ignore[attr-defined]
                    if getattr(part, "thought", False):
                        continue
                    parts.append(getattr(part, "text", "") or "")
            except Exception:
                parts = [getattr(res, "text", "") or ""]
            holder["text"] = "".join(parts).strip() or (getattr(res, "text", "") or "")
        except Exception as e:
            holder["error"] = e

    t = threading.Thread(target=_worker, daemon=True)
    t.start()
    t.join(_ROUTER_TIMEOUT_S)
    if t.is_alive() or "error" in holder:
        err = holder.get("error")
        print(
            f"[doc_router] LLM FAILED "
            f"({'timeout' if t.is_alive() else type(err).__name__}): {err}",
            file=sys.stderr, flush=True,
        )
        return None
    return _parse_router_response(holder.get("text") or "", docs)


def route_docs(supabase: Any, question: str) -> dict:
    """질문 → {"ok", "scope", "doc_ids", "titles", "reasons", "elapsed"}.

    ok=False 는 fail-open (LLM/카탈로그/파싱 실패) — 호출자는 기존 경로를
    그대로 타야 한다. ok=True 이고 doc_ids=[] 이며 scope="in" 은 "사규 관련
    같지만 특정 문서 확신 없음" — 정상 파이프라인(vector/BM25)에 맡긴다.
    절대 raise 하지 않는다.
    """
    q = (question or "").strip()
    fail_open = {
        "ok": False, "scope": "in", "doc_ids": [], "titles": [],
        "reasons": [], "elapsed": 0.0,
    }
    if not q:
        return fail_open
    with _lock:
        cached = _route_cache.get(q)
    if cached is not None:
        return cached

    start = time.perf_counter()
    try:
        docs = _load_catalog(supabase)
        if not docs:
            helper_health.record("doc_router")
            return fail_open
        parsed = _call_llm(q, docs)
        if parsed is None:
            helper_health.record("doc_router")
            return fail_open
        result = {
            "ok": True,
            "scope": parsed["scope"],
            "doc_ids": parsed["doc_ids"],
            "titles": parsed["titles"],
            "reasons": parsed["reasons"],
            "elapsed": time.perf_counter() - start,
        }
        print(
            f"[doc_router] OK scope={result['scope']} "
            f"docs={[t[:30] for t in result['titles']]} "
            f"elapsed={result['elapsed']:.2f}s q_head={q[:50]!r}",
            file=sys.stderr, flush=True,
        )
        with _lock:
            if len(_route_cache) >= _ROUTE_CACHE_MAX:
                _route_cache.pop(next(iter(_route_cache)))
            _route_cache[q] = result
        return result
    except Exception as e:
        # 마지막 방어선 — silent fail 금지 원칙 (CLAUDE.md Part 2-D)
        print(
            f"[doc_router] FAILED (outer): {type(e).__name__}: {e}",
            file=sys.stderr, flush=True,
        )
        helper_health.record("doc_router")
        return fail_open
