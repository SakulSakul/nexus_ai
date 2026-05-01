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
               max_workers: int = 4, per_call_timeout: float = 30.0,
               overall_timeout: float | None = None) -> list[list[float]]:
    """청크 임베딩 병렬화. Gemini embed_content 는 단일 string 만 받지만
    ThreadPoolExecutor 로 동시 처리해 적재 시간을 단축한다.
    - per_call_timeout: 1건당 최대 대기 (기본 30초). 초과 시 RuntimeError.
    - overall_timeout: 전체 회차 wall-clock 한도. None 이면 자동 산정
      (per_call_timeout × ceil(N/workers) + 10s 여유). N개 직렬 누적으로
      worst case 50분 대기하던 결함 방지. 초과 시 즉시 raise.
    순서 보장: 인덱스로 결과 누적 후 순서대로 반환.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as _Timeout
    import math as _math
    import time as _time
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
    # 전체 회차 wall-clock 한도. as_completed 의 timeout 인자로 강제.
    if overall_timeout is None:
        overall_timeout = per_call_timeout * _math.ceil(len(items) / workers) + 10.0
    deadline = _time.monotonic() + overall_timeout

    ex = ThreadPoolExecutor(max_workers=workers)
    try:
        futures = {ex.submit(_one, t): i for i, t in enumerate(items)}
        try:
            for fut in as_completed(futures, timeout=overall_timeout):
                remaining = max(0.0, deadline - _time.monotonic())
                idx = futures[fut]
                try:
                    out[idx] = fut.result(timeout=min(per_call_timeout, remaining + 0.5))
                except _Timeout as e:
                    raise RuntimeError(
                        f"임베딩 호출이 {per_call_timeout}초 내 응답하지 않았습니다 "
                        f"(chunk {idx}/{len(items)}). Gemini API 상태 확인 필요."
                    ) from e
        except _Timeout as e:
            raise RuntimeError(
                f"임베딩 회차 전체 wall-clock {overall_timeout:.0f}초 초과. "
                f"완료 {sum(1 for o in out if o is not None)}/{len(items)}. "
                "일괄 재시도 또는 청크 수 분할 권장."
            ) from e
    finally:
        ex.shutdown(wait=False, cancel_futures=True)
    return [o for o in out if o is not None]
