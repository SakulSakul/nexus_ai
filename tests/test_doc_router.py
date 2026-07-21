"""PR-Doc-Router 단위 테스트 — 네트워크/LLM 불필요 (파싱·검증·fail-open).

라우터의 안전 계약 검증:
1. 닫힌 목록 강제 — 카탈로그 범위 밖 idx 는 버린다 (환각 차단).
2. 선택 cap 3 + doc_id dedup.
3. 파싱 실패/비정상 scope → None (호출자 fail-open).
4. route_docs 는 어떤 입력에서도 raise 하지 않는다.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.doc_router import (  # noqa: E402
    _build_catalog_lines,
    _parse_router_response,
    route_docs,
)

DOCS = [
    {"id": "d0", "title": "(CSR) 대외출강 운영 지침", "auto_keywords": ["강의료", "출강"]},
    {"id": "d1", "title": "(공통) 임직원 징계기준", "auto_keywords": []},
    {"id": "d2", "title": "(영업) CSR경영방침", "auto_keywords": ["클린신고"]},
    {"id": "d3", "title": "(재무) 법인카드 관리지침", "auto_keywords": None},
]


def test_catalog_lines_format_and_keywords():
    lines = _build_catalog_lines(DOCS).splitlines()
    assert len(lines) == 4
    assert lines[0].startswith("0. (CSR) 대외출강 운영 지침")
    assert "키워드: 강의료, 출강" in lines[0]
    assert "키워드" not in lines[1]  # 빈 keywords 는 표기 생략
    assert "키워드" not in lines[3]  # None keywords 안전 처리


def test_parse_valid_selection():
    text = (
        '{"scope": "in", "selected": ['
        '{"idx": 0, "why": "외부 인터뷰 사례금"}, {"idx": 1, "why": "징계"}]}'
    )
    r = _parse_router_response(text, DOCS)
    assert r is not None
    assert r["scope"] == "in"
    assert r["doc_ids"] == ["d0", "d1"]
    assert r["titles"][0] == "(CSR) 대외출강 운영 지침"


def test_parse_rejects_out_of_range_and_dedups_and_caps():
    text = (
        '{"scope": "in", "selected": ['
        '{"idx": 99, "why": "환각"}, {"idx": -1, "why": "환각"},'
        '{"idx": "0", "why": "타입오류"},'
        '{"idx": 0, "why": "a"}, {"idx": 0, "why": "dup"},'
        '{"idx": 1, "why": "b"}, {"idx": 2, "why": "c"}, {"idx": 3, "why": "d"}]}'
    )
    r = _parse_router_response(text, DOCS)
    assert r is not None
    assert r["doc_ids"] == ["d0", "d1", "d2"]  # 범위 밖·중복 제거 + cap 3


def test_parse_out_scope_with_empty_selection():
    r = _parse_router_response('{"scope": "out", "selected": []}', DOCS)
    assert r is not None
    assert r["scope"] == "out"
    assert r["doc_ids"] == []


def test_parse_fail_open_cases():
    assert _parse_router_response("", DOCS) is None
    assert _parse_router_response("not json", DOCS) is None
    assert _parse_router_response('{"scope": "maybe", "selected": []}', DOCS) is None
    assert _parse_router_response('["scope", "in"]', DOCS) is None
    # 코드펜스 감싸짐은 허용 (첫 JSON object 추출)
    fenced = '```json\n{"scope": "in", "selected": []}\n```'
    assert _parse_router_response(fenced, DOCS) is not None


class _BoomSupabase:
    """모든 접근에서 폭발하는 stub — route_docs 의 no-raise 계약 검증."""

    def table(self, *_a, **_k):
        raise RuntimeError("boom")


def test_route_docs_never_raises():
    r = route_docs(_BoomSupabase(), "중국 리서치 업체 인터뷰 사례 문의")
    assert r["ok"] is False
    assert r["scope"] == "in"          # fail-open = 기존 파이프라인 유지
    assert r["doc_ids"] == []
    r2 = route_docs(_BoomSupabase(), "")
    assert r2["ok"] is False
