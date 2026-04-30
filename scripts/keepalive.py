"""Supabase keep-alive ping (테스트 단계 한정).

GitHub Actions 에서 주기적으로 호출. 가벼운 SELECT 1 쿼리로 sleep 진입을 방지한다.
운영 배포 형태(Phase 5) 결정 후 본 스크립트는 제거 또는 운영 모니터링으로 대체.
"""

from __future__ import annotations

import os
import sys


def main() -> int:
    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_KEY", "")
    if not url or not key:
        print("SUPABASE_URL / SUPABASE_KEY missing — skip", file=sys.stderr)
        return 0
    from supabase import create_client
    sb = create_client(url, key)
    # anon 키 기반 keepalive 는 hotline_config_public view 로 ping 한다.
    # 원본 hotline_config 테이블은 RLS 가 anon SELECT 를 차단하므로 직접
    # 조회하면 빈 결과가 떨어져 keepalive 의의가 없어진다.
    rows = sb.table("hotline_config_public").select("key").limit(1).execute().data
    print(f"keepalive ok: {len(rows or [])} row(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
