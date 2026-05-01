"""Gemini 임베딩 래퍼 — 검색/적재 양쪽에서 단일 진입점 사용.

운영 시점 최신 안정 모델은 `NEXUS_EMBED_MODEL` 환경변수로 추상화한다.
출력 차원은 `NEXUS_EMBED_DIM` 와 일치해야 하며 DB 스키마(vector(768))도 동일.
"""

from __future__ import annotations

from typing import Iterable

from .config import settings


def _client():
    from google import genai
    return genai.Client(api_key=settings().gemini_api_key)


def embed_one(text: str, *, task_type: str = "RETRIEVAL_QUERY") -> list[float]:
    s = settings()
    # NOTE: genai.Client 를 임시 객체로 두면 호출 직전에 GC 되며
    # 내부 httpx 클라이언트가 닫혀 "Cannot send a request, as the client
    # has been closed" 가 발생한다. 반드시 로컬 변수로 잡아둘 것.
    cli = _client()
    res = cli.models.embed_content(
        model=s.embed_model,
        contents=text,
        config={"task_type": task_type, "output_dimensionality": s.embed_dim},
    )
    return list(res.embeddings[0].values)


def embed_many(texts: Iterable[str], *, task_type: str = "RETRIEVAL_DOCUMENT",
               max_workers: int = 4, per_call_timeout: float = 30.0) -> list[list[float]]:
    """청크 임베딩 병렬화. Gemini embed_content 는 단일 string 만 받지만
    ThreadPoolExecutor 로 동시 처리해 적재 시간을 단축한다.
    max_workers=4 가 API rate limit + 네트워크 대기 균형에 적정.
    per_call_timeout 초 안에 한 호출이 안 끝나면 RuntimeError. Gemini hang 시
    admin 적재 화면이 무한 spinner 상태로 빠지는 사고 방지.
    순서 보장: 인덱스로 결과 누적 후 순서대로 반환.
    """
    from concurrent.futures import ThreadPoolExecutor, TimeoutError as _Timeout
    s = settings()
    items = list(texts)
    if not items:
        return []

    def _one(t: str) -> list[float]:
        cli = _client()
        res = cli.models.embed_content(
            model=s.embed_model,
            contents=t,
            config={"task_type": task_type, "output_dimensionality": s.embed_dim},
        )
        return list(res.embeddings[0].values)

    workers = max(1, min(max_workers, len(items)))
    out: list[list[float] | None] = [None] * len(items)
    # with-block 종료 시 shutdown(wait=True) 가 호출되면 timeout 된 thread 가
    # 끝날 때까지 영원히 대기 → 사용자에겐 spinner 만 돌고 timeout 메시지 안
    # 보임. 수동 ex 관리 + finally shutdown(wait=False, cancel_futures=True)
    # 로 timeout 즉시 반영.
    ex = ThreadPoolExecutor(max_workers=workers)
    try:
        futures = {ex.submit(_one, t): i for i, t in enumerate(items)}
        for fut, idx in futures.items():
            try:
                out[idx] = fut.result(timeout=per_call_timeout)
            except _Timeout as e:
                raise RuntimeError(
                    f"임베딩 호출이 {per_call_timeout}초 내 응답하지 않았습니다 "
                    f"(chunk {idx}/{len(items)}). Gemini API 상태 확인 필요."
                ) from e
    finally:
        ex.shutdown(wait=False, cancel_futures=True)
    return [o for o in out if o is not None]
