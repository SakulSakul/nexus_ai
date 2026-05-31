"""헬퍼 LLM(reranker / oos judge / rewriter) fail-open 가시화 (FMEA R1).

이 헬퍼들은 실패 시 예외를 안 던지고 fail-open(raw 순서 / 1.0 / 원문 쿼리)
하므로 장애가 silent 하다. 프로세스 수명 동안의 실패를 in-memory 로 집계해
운영 모니터링 Dashboard 에서 가시화 + 임계 초과 시 회로 '열림' 표시한다.

NOTE: 프로세스 메모리 기반 — reboot(매 머지) 시 리셋. 프로덕션(reboot 드묾)
에서 Flash-Lite 등 헬퍼 장애 episode 탐지가 목적. 교차-재시작 영속이 필요하면
nexus_audit_logs(core/audit/logger.py) 로 확장. stdlib only — 순환참조 0.
"""
from __future__ import annotations

import threading
import time
from collections import deque

_LOCK = threading.Lock()
_CAP = 500  # helper 당 최근 실패 timestamp 최대 보관
_FAILURES: dict[str, deque] = {}


def record(name: str) -> None:
    """헬퍼 실패 1건 기록 — best-effort, 절대 raise 하지 않는다."""
    try:
        now = time.time()
        with _LOCK:
            dq = _FAILURES.get(name)
            if dq is None:
                dq = deque(maxlen=_CAP)
                _FAILURES[name] = dq
            dq.append(now)
    except Exception:
        pass


def recent_count(name: str, window_s: float = 3600.0) -> int:
    cutoff = time.time() - window_s
    with _LOCK:
        dq = _FAILURES.get(name)
        if not dq:
            return 0
        return sum(1 for t in dq if t >= cutoff)


def is_open(name: str, threshold: int, window_s: float = 60.0) -> bool:
    """회로 'open'(장애 의심) — window 내 실패 >= threshold."""
    return recent_count(name, window_s) >= threshold


def snapshot(window_s: float = 3600.0) -> dict[str, int]:
    with _LOCK:
        names = list(_FAILURES.keys())
    return {n: recent_count(n, window_s) for n in names}
