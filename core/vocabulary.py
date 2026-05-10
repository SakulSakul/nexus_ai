"""사규 vocabulary loader — PR-Quality-2.

`core/vocabulary.json` 에 저장된 사규 핵심 용어 list 를 읽어 SYSTEM_PROMPT 에
inject 한다. admin 페이지의 "🔤 사규 vocabulary 추출" 버튼이 1회 작업으로
Gemini 에 전체 청크를 보내 list 를 산출 → 사쿨이 검토·보강 → vocabulary.json
으로 commit. 사규는 1년 stable 이라 확장은 이벤트 기반(사규 추가·개정 시).

빈 list (아직 추출 전) 이면 SYSTEM_PROMPT 의 vocabulary 섹션은 통째로 생략 —
LLM 에게 빈 list 를 강요하지 않는다.
"""

from __future__ import annotations

import json
from pathlib import Path


VOCABULARY_PATH = Path(__file__).parent / "vocabulary.json"


def load_vocabulary() -> list[str]:
    """vocabulary.json 을 읽어 list[str] 반환. 파일 없거나 형식 이상이면 [].

    호출 측은 이 결과의 truthiness 로 inject 여부를 판단한다.
    """
    try:
        raw = VOCABULARY_PATH.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError):
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in data:
        if not isinstance(item, str):
            continue
        s = item.strip()
        if not s or s in seen:
            continue
        seen.add(s)
        out.append(s)
    return out
