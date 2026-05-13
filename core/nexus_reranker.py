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

import json
import sys
import time

from .config import get_secret, settings


_RERANK_MODEL = get_secret("NEXUS_RERANK_MODEL", "gemini-2.5-flash-lite")
_RERANK_TOP_N = 30          # reranker 가 평가할 raw_chunks 상위 N
_CHUNK_PREVIEW_LEN = 400    # 청크당 LLM 에 전달할 text preview 길이 (chars)
_MAX_OUTPUT_TOKENS = 2048   # ranked_ids 30개 + JSON overhead 충분
_RERANK_TEMPERATURE = 0.0   # 결정적 ranking (재현성)


_SYSTEM_TEXT = """당신은 사규 검색 결과를 의미 기반으로 재정렬하는 reranker 입니다.
사용자의 질문에 대해 가장 의미가 잘 맞고 답변에 직접 활용 가능한 청크를 우선 ranking 하세요.

원칙:
- 의미 매칭 우선 (단순 어휘 일치 보다 의미 일치)
- 도메인 매칭 강화 — 질문의 도메인과 문서 제목 prefix 도메인이 일치하는 chunk 우선
- 구체적 정보 우선 (도입부/총칙/목적 보다 절차/표/구체 사례/조항)
- 답변에 직접 인용 가능한 청크 우선 (의무·금지·기준·수위 명시)
- 같은 문서의 청크 중에서는 질문에 가장 구체적으로 답하는 것을 우선
- 도메인 mismatch chunk 는 의미 매칭이 강하지 않은 한 후순위

도메인-query 매핑 예시 (문서 제목 prefix 기준):
- 휴가·출장비·인사평가·신입교육·승진·근태 → (인사)
- 사고·재해·응급·안전보건·산업안전·소방 → (안전)
- 자금·예산·결제·경비처리·법인카드 → (재무)
- 거래처·협력업체·금품·접대·이해관계자 → (공정거래)
- 정보유출·외부반출·메일송신·USB·해킹·개인정보 → (정보보안)
- 횡령·배임·직장 내 괴롭힘·성희롱·징계·CREDO·윤리 → (공통)

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
    try:
        cli = genai.Client(api_key=s.gemini_api_key)
        cfg = types.GenerateContentConfig(
            system_instruction=_SYSTEM_TEXT,
            temperature=_RERANK_TEMPERATURE,
            max_output_tokens=_MAX_OUTPUT_TOKENS,
            response_mime_type="application/json",
        )
        res = cli.models.generate_content(
            model=_RERANK_MODEL,
            contents=user_text,
            config=cfg,
        )
    except Exception as e:
        print(
            f"[reranker] FAILED gemini call: {type(e).__name__}: {e}",
            file=sys.stderr, flush=True,
        )
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
    ranked_ids = _call_gemini_for_rerank(query, head)
    elapsed_ms = int((time.time() - t_start) * 1000)

    if not ranked_ids:
        # graceful fallback — 원본 순서 유지.
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
