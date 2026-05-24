"""DF COMPASS smoke test — PR 머지 전 핵심 retrieval 회귀 검증.

force-include 가 silent fail(예: chunk_incident_nodes 부재 컬럼 select)로
무력화되는 사고를 빠르게 잡기 위한 최소 회귀 세트.

사용:
    python test_smoke.py

종료 코드: 통과 0 / 실패 1. 환경(Supabase secrets) 미설정 시 2.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# (질문, 답변 본문에 포함되어야 할 키워드)
SMOKE_QUERIES = [
    ("출장비 어떻게 처리?", "출장비"),
    ("법인카드 관리지침", "법인카드"),
    ("위험성평가는?", "위험성평가"),
    ("개인정보 보호 어떻게?", "개인정보"),
    ("성희롱 예방", "성희롱"),
]


def _client():
    from core.config import settings
    from supabase import create_client
    s = settings()
    if not s.supabase_url:
        return None
    key = getattr(s, "supabase_service_role_key", None) or s.supabase_key
    if not key:
        return None
    return create_client(s.supabase_url, key)


def run_smoke_test() -> int:
    from core.chatbot import ask

    sb = _client()
    if sb is None:
        print("⚠️ Supabase secrets 미설정 — smoke test skip")
        return 2

    failures: list[tuple] = []
    for query, expected in SMOKE_QUERIES:
        try:
            ans = ask(sb, question=query, category=None)
            answer_text = getattr(ans, "text", "") or ""
            if expected in answer_text:
                print(f"✅ {query}")
            else:
                failures.append((query, expected, answer_text[:200]))
                print(f"❌ {query} — '{expected}' not in answer")
        except Exception as e:
            failures.append((query, "Exception", str(e)))
            print(f"💥 {query} — {type(e).__name__}: {e}")

    if failures:
        print(f"\n{len(failures)}/{len(SMOKE_QUERIES)} failed")
        return 1
    print(f"\n✅ All {len(SMOKE_QUERIES)} smoke tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(run_smoke_test())
