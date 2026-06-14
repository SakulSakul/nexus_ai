"""의미 기반 LLM reranker — Gemini 2.5 Flash-Lite.

retriever 의 RRF (vector + BM25) sort 직후 top-N (기본 30) 청크를 Gemini
Flash-Lite 에 전달해 의미 매칭 기반으로 재정렬한다. RRF + 어휘 매칭의
구조적 한계 (도입부/총칙 청크가 구체 정보 청크보다 우선) 를 LLM 의 의미
매칭으로 보완.

설계 원칙:
- 실패는 절대 raise 하지 않는다. graceful fallback (원본 sort 유지) — 회귀 위험 0.
- Top-N 만 reranker 통과 — 꼬리(N 이후)는 원본 순서로 유지.
- Structured JSON output (response_mime_type) — parse 안정성.
- Latency: ~500ms~1s 예상. 사쿨 priority quality > latency.
- 비용: Flash-Lite ~$0.0004/call. 무시 가능 수준.

호출자는 retriever.py 의 RRF sort 직후 한 번. 본 모듈은 외부 노출 함수
`rerank_chunks` 만 사용.
"""

from __future__ import annotations

from . import helper_health  # FMEA R1: fail-open 가시화

import json
import sys
import threading
import time

from .config import get_secret, settings


_RERANK_MODEL = get_secret("NEXUS_RERANK_MODEL", "gemini-3.1-flash-lite")
# PR-Reranker-Top15: top_n 30→15 으로 reranker latency -2.4초.
# Risk: Q13 fix (공정거래 doc) 가 top 15 안에 포함되는지 검증.
_RERANK_TOP_N = 15          # reranker 가 평가할 raw_chunks 상위 N
_CHUNK_PREVIEW_LEN = 400    # 청크당 LLM 에 전달할 text preview 길이 (chars)
_MAX_OUTPUT_TOKENS = 2048   # ranked_ids 30개 + JSON overhead 충분
_RERANK_TEMPERATURE = 0.0   # 결정적 ranking (재현성)
_RERANK_TIMEOUT_S = 6.0    # PR-Reranker-Timeout-v2: 성공 리랭크 ≤5.5s(관측) 보존 + 스파이크 dead-time 4s 절감 (timeout 시 RRF fallback)
_RERANK_MAX_RETRIES = 3       # PR-Reranker-Backoff: 503/429 재시도 횟수
_RERANK_BACKOFF_BASE_S = 1.0  # PR-Reranker-Backoff: exponential backoff base (1s, 2s, 4s)


_SYSTEM_TEXT = """당신은 DF COMPASS 사규 (compliance) 앱의 검색 결과 reranker 입니다.
사용자의 질문에 대해 가장 의미가 잘 맞고 답변에 직접 활용 가능한 청크를 우선 ranking 하세요.

[앱 정체성 — 매우 중요]
DF COMPASS 는 사규 (compliance) 앱입니다. 인사 규정 (휴가/평가/근태/승진/일반
교육·채용 등) 은 별도 인사 규정 앱에서 처리됩니다.
- 인사 규정 query 에 대해 (인사) prefix doc 을 강제로 상위 ranking 하지 않습니다.
  의미 매칭이 약하면 후순위로 두어 graceful '인사교육팀 문의' 라우팅을 유도합니다.
- (인사) prefix doc 중 사규 관련 문서 (예: 직장 내 괴롭힘 예방·대응지침,
  성희롱 예방 지침, 윤리 규정 등) 는 의미 매칭 시 정상 ranking 합니다.

원칙:
- 의미 매칭 우선 (단순 어휘 일치 보다 의미 일치)
- 도메인 매칭 강화 — 질문의 도메인과 문서 제목 prefix 도메인이 일치하는 chunk 우선
- 구체적 정보 우선 (도입부/총칙/목적 보다 절차/표/구체 사례/조항)
- 답변에 직접 인용 가능한 청크 우선 (의무·금지·기준·수위 명시)
- 같은 문서의 청크 중에서는 질문에 가장 구체적으로 답하는 것을 우선
- 도메인 mismatch chunk 는 의미 매칭이 강하지 않은 한 후순위

=== PR-Strengthen-Reranker-Prompt 추가 원칙 ===

[Multi-Domain Query 인식 — 매우 중요]
질문이 여러 도메인을 동시에 cover 하면 각 도메인의 대표 chunk 를 골고루 top 에
보존하세요. 한 도메인의 chunks 가 많다고 그것들로 top 을 도배하면 안 됩니다.

예시:
- "거래처 명절 선물" → (공통) CREDO + (CSR) 클린뱅크 + (공통) 임직원 징계기준
  3 도메인 모두 top 5 안 보존 (한 도메인이 top 5 독점 X)
- "경쟁사 가격 정보 공유" → (공정거래) + (공통) 사건사고 + (공통) 임직원 징계기준
- "인장 도용 사례 발견" → (총무) 인감 관리지침 + (공통) 사건사고 + (공통) 임직원 징계기준
- "외부 강사료 수령" → (CSR) 클린뱅크 + (공통) CREDO

[답변 3-Section 구조 인식]
답변은 3 section 으로 구성됩니다 — 각 section 의 chunks 를 골고루 보존:
1. 📋 사규 기준 — 사규 본문, 의무, 금지, 정의 (도메인 doc 핵심)
2. ⚖️ 징계 기준 — (공통) 임직원 징계기준 의 수위·구분
3. 📂 사건사례 — 보고 절차, 처리 procedure ((공통) 사건사고 보고지침 등)

각 section 의 매칭 chunk 가 모두 top 안에 있어야 풍부한 답변. 한 section 의
chunks 만 ranking 상위 도배되면 답변이 한쪽으로 치우침.

[1-Doc 도메인 보존]
한 query 에 단 1 doc 만 cover 하는 도메인 ((총무) 인감 관리지침, (공정거래)
자율준수 지침 등) 의 chunk 는 의미 매칭이 OK 인 한 다른 도메인 다수 chunks 와
동등하게 top 안에 보존하세요. 의미 매칭 약함을 이유로 drop 하지 마세요.

도메인-query 매핑 예시 (사규 도메인만 — 문서 제목 prefix 기준):
- 사고·재해·응급·안전보건·산업안전·소방 → (안전)
- 자금·예산·결제·경비처리·법인카드·출장비 → (재무)/(총무)
- 인감·인장·도장 → (총무) 인감 관리지침 ⭐ (1-doc 도메인 — 반드시 보존)
- 거래처·협력업체·금품·접대·이해관계자·외부강사료 → (공정거래) + (공통) + (CSR)
- 가격정보·담합·경쟁사 → (공정거래) 자율준수 지침 + (공정거래) 경영정보 ⭐ (보존)
- 정보유출·외부반출·메일송신·USB·해킹·개인정보 → (정보보안)
- 직장 내 괴롭힘·성희롱 → (인사) 직장 내 괴롭힘 예방·대응지침 + (공통)
- 횡령·배임·징계·CREDO·윤리 → (공통)
- 매장운영·고객응대·재고관리 → (영업)
- 환경사고·폐기물·위생·비상시 → (환경) 비상시대비대응 + 환경경영매뉴얼
- 사회공헌·외부협력·클린뱅크·클린신고 → (CSR) ⭐ (보존)

(주의) 휴가·인사평가·신입교육·승진·근태 같은 인사 규정 query 는 의미 매칭
강한 사규 doc 이 없으면 (인사) prefix doc 강제 ranking 하지 않고 graceful
후순위 처리. '인사교육팀 문의' 라우팅이 정답.

출력은 반드시 다음 JSON 형식:
{"ranked_ids": ["<id1>", "<id2>", ...]}

ranked_ids 는 입력으로 받은 모든 chunk id 를 의미 매칭이 좋은 순으로 정렬한 리스트.
입력 청크 모두 포함 (누락/중복 없이)."""


def _build_user_prompt(query: str, chunks: list[dict]) -> str:
    """chunks 의 id + 헤더 + text preview 를 LLM 평가용 prompt 로 빌드."""
    lines = [f"질문: {query}", "", "청크 목록:"]
    for c in chunks:
        cid = str(c.get("id") or "")
        title = c.get("doc_title") or ""
        article = c.get("article_no") or ""
        chunk_idx = c.get("chunk_idx")
        text = (c.get("text") or "")[:_CHUNK_PREVIEW_LEN]
        text = " ".join(text.split())  # 공백/개행 정규화
        header = f"[id={cid}]"
        if title:
            header += f" 문서={title}"
        if article:
            header += f" 조항={article}"
        if chunk_idx is not None:
            header += f" idx={chunk_idx}"
        lines.append(f"{header}\n  {text}")
    return "\n".join(lines)


def _extract_response_text(res: object) -> str:
    """Gemini 응답에서 text 추출 — _gen_gemini 패턴과 동일."""
    text_parts: list[str] = []
    try:
        for part in res.candidates[0].content.parts:  # type: ignore[attr-defined]
            if getattr(part, "thought", False):
                continue
            text_parts.append(getattr(part, "text", "") or "")
    except Exception:
        text_parts = [getattr(res, "text", "") or ""]
    text = "".join(text_parts).strip()
    if not text:
        text = (getattr(res, "text", "") or "").strip()
    return text


def _is_rerank_retryable_error(e: Exception) -> bool:
    """503/429/UNAVAILABLE 같은 일시적 error 판별 (PR-Reranker-Backoff)."""
    msg = str(e).lower()
    return any(
        keyword in msg
        for keyword in ("503", "429", "unavailable", "rate limit", "high demand", "timeout")
    )


def _call_gemini_for_rerank(query: str, chunks: list[dict]) -> list[str]:
    """LLM 호출 → ranked_ids 리스트. 실패 시 빈 리스트."""
    try:
        from google import genai
        from google.genai import types
    except Exception:
        return []

    s = settings()
    if not s.gemini_api_key:
        return []
    if not chunks:
        return []

    user_text = _build_user_prompt(query, chunks)
    cli = genai.Client(api_key=s.gemini_api_key)
    cfg = types.GenerateContentConfig(
        system_instruction=_SYSTEM_TEXT,
        temperature=_RERANK_TEMPERATURE,
        max_output_tokens=_MAX_OUTPUT_TOKENS,
        response_mime_type="application/json",
    )

    # PR-Reranker-Backoff: 503/429 시 exponential backoff retry (PR #202 패턴)
    res = None
    for attempt in range(_RERANK_MAX_RETRIES):
        try:
            res = cli.models.generate_content(
                model=_RERANK_MODEL,
                contents=user_text,
                config=cfg,
            )
            break  # 성공
        except Exception as e:
            is_last = attempt == _RERANK_MAX_RETRIES - 1
            if not _is_rerank_retryable_error(e) or is_last:
                print(
                    f"[reranker] FAILED gemini call "
                    f"(attempt {attempt+1}/{_RERANK_MAX_RETRIES}): "
                    f"{type(e).__name__}: {e}",
                    file=sys.stderr, flush=True,
                )
                return []
            wait_s = _RERANK_BACKOFF_BASE_S * (2 ** attempt)
            print(
                f"[reranker] RETRYABLE error "
                f"(attempt {attempt+1}/{_RERANK_MAX_RETRIES}), "
                f"backoff {wait_s:.1f}s: {type(e).__name__}: {e}",
                file=sys.stderr, flush=True,
            )
            time.sleep(wait_s)

    if res is None:
        return []

    text = _extract_response_text(res)
    if not text:
        print("[reranker] FAILED empty response", file=sys.stderr, flush=True)
        return []

    try:
        data = json.loads(text)
        ranked = data.get("ranked_ids") if isinstance(data, dict) else None
        if not isinstance(ranked, list):
            return []
        return [str(x) for x in ranked]
    except Exception as e:
        print(
            f"[reranker] FAILED json parse: {type(e).__name__}: {e}",
            file=sys.stderr, flush=True,
        )
        return []


def rerank_chunks(query: str, raw_chunks: list[dict]) -> list[dict]:
    """raw_chunks 의 top-N 을 의미 매칭 기반으로 재정렬.

    Flow:
        head = raw_chunks[:N], tail = raw_chunks[N:]
        head 를 Gemini Flash-Lite 에 전달 → ranked_ids 받음
        ranked_ids 기준 head 재정렬 (누락 chunk 는 원본 순서로 뒤에 append)
        반환: reranked_head + tail

    실패 시 raw_chunks 를 그대로 반환 (회귀 위험 0).
    """
    if not query or not raw_chunks:
        return raw_chunks

    head = raw_chunks[:_RERANK_TOP_N]
    tail = raw_chunks[_RERANK_TOP_N:]

    t_start = time.time()

    # PR-Reranker-Timeout: 10s 초과 시 fallback to original order
    result_holder: list = [None]

    def _target():
        try:
            result_holder[0] = _call_gemini_for_rerank(query, head)
        except Exception as e:
            print(
                f"[reranker] thread exception: {type(e).__name__}: {e}",
                file=sys.stderr, flush=True,
            )
            result_holder[0] = []

    th = threading.Thread(target=_target, daemon=True)
    th.start()
    th.join(_RERANK_TIMEOUT_S)

    elapsed_ms = int((time.time() - t_start) * 1000)

    if th.is_alive():
        # timeout — thread 는 background 에서 계속 진행, 결과 무시
        print(
            f"[reranker] TIMEOUT after {elapsed_ms}ms "
            f"(limit={int(_RERANK_TIMEOUT_S*1000)}ms), "
            f"fallback to original order",
            file=sys.stderr, flush=True,
        )
        helper_health.record("reranker")
        return raw_chunks

    ranked_ids = result_holder[0] or []

    if not ranked_ids:
        # graceful fallback — 원본 순서 유지.
        helper_health.record("reranker")
        return raw_chunks

    id_to_chunk: dict = {str(c.get("id") or ""): c for c in head}
    reranked: list = []
    seen: set = set()
    for rid in ranked_ids:
        c = id_to_chunk.get(str(rid))
        if c is None:
            continue
        cid = str(c.get("id") or "")
        if cid in seen:
            continue
        reranked.append(c)
        seen.add(cid)
    # LLM 이 빠뜨린 청크는 원본 순서로 뒤에 append (안전망).
    missing = 0
    for c in head:
        cid = str(c.get("id") or "")
        if cid in seen:
            continue
        reranked.append(c)
        seen.add(cid)
        missing += 1

    print(
        f"[reranker] OK model={_RERANK_MODEL} input={len(head)} "
        f"output={len(reranked)} missing={missing} elapsed_ms={elapsed_ms}",
        file=sys.stderr, flush=True,
    )

    return reranked + tail


# ── PR-OOS-Gate: Reranker-as-judge — 절대 관련도(0.0~1.0) ────────────────
# rerank_chunks 는 순서만 바꾸므로 OOS 게이트용 절대 신호를 따로 산출한다.
# 동일 _RERANK_MODEL / genai 클라이언트 재사용. 실패 시 1.0 (fail-open).
_JUDGE_SYSTEM_TEXT = (
    "당신은 DF COMPASS 사규(compliance) 앱의 관련도 심판입니다. "
    "사용자 질문이 아래 사내 사규 청크들로 실제 답할 수 있는 주제인지 "
    "relevance 0.0~1.0 으로 판정하세요. 청크가 질문 주제를 직접 다루면 "
    "0.7~1.0, 스치면 0.4~0.6, 무관하면 0.0~0.3. "
    'JSON 한 줄로만: {"relevance": <숫자>}'
)


def judge_relevance(query: str, chunks: list[dict]) -> float:
    """질문 vs 사규 청크의 절대 관련도(0.0~1.0). OOS 게이트 전용.
    실패(키 없음·API 오류·파싱 실패) → 1.0 (fail-open: OOS 취소 → 정상 파이프라인)."""
    if not query or not chunks:
        return 1.0
    try:
        from google import genai
        from google.genai import types
    except Exception:
        return 1.0
    s = settings()
    if not s.gemini_api_key:
        return 1.0
    try:
        cli = genai.Client(api_key=s.gemini_api_key)
        cfg = types.GenerateContentConfig(
            system_instruction=_JUDGE_SYSTEM_TEXT,
            temperature=0.0,
            max_output_tokens=64,
            response_mime_type="application/json",
        )
        res = cli.models.generate_content(
            model=_RERANK_MODEL,
            contents=_build_user_prompt(query, chunks[:3]),
            config=cfg,
        )
        data = json.loads(_extract_response_text(res))
        return max(0.0, min(1.0, float(data.get("relevance"))))
    except Exception as e:
        helper_health.record("oos_judge")
        print(f"[oos-judge] FAILED -> fail-open 1.0: {type(e).__name__}: {e}",
              file=sys.stderr, flush=True)
        return 1.0
