# ROLLBACK 런북 — 대규모 업그레이드 회귀 대응 (2026-07-21)

업그레이드 중/후 회귀 발생 시 이 문서 하나로 복원한다.
**에스컬레이션 순서: C(플래그) → A(revert) → B(강제 복원).** 아래로 갈수록 강력하고 파괴적.

## 롤백 앵커 (고정값)

| 항목 | 값 |
|---|---|
| 앵커 커밋 | `4f9658d` — doc-router #398 머지 직후 main |
| 원격 백업 브랜치 | `backup/pre-upgrade-20260721` (= 4f9658d, push·검증 완료) |
| 앵커 검증 | `git ls-remote origin backup/pre-upgrade-20260721` → `4f9658d...` |

⚠️ `backup/pre-upgrade-20260721` 브랜치는 **삭제 금지** (업그레이드 안정화 판정 전까지).

## 방법 C — 플래그 킬스위치 (가장 빠름, 코드 롤백 없음, 1차 시도)

업그레이드가 flag 뒤에 있으면 Streamlit Cloud secrets 에서 해당 flag 를 `"false"` 로 → 재기동.
현 시점 flag 전수 (모두 코드 기본값 OFF — secrets 로만 켜짐):

```
ENABLE_DOC_ROUTER            ENABLE_OOS_RELEVANCE_GATE    ENABLE_OOS_ROUTING
ENABLE_NO_CONTEXT_GATE       ENABLE_AMBIGUITY_ASKBACK     ENABLE_FAST_PATH
ENABLE_QUERY_CLASSIFIER_ACTION  ENABLE_QUERY_CLASSIFIER_LOGGING  ENABLE_SYNONYM_EXPANSION
```

secrets 에서 키를 지우는 것도 동일 효과(기본 false). 재기동 후 §검증 수행.

## 방법 A — git revert (권장, 히스토리 보존)

```bash
git fetch origin main
git checkout -b rollback/revert origin/main
# 업그레이드로 들어간 머지커밋들을 최신부터 역순으로:
git revert --no-edit -m 1 <머지커밋해시>        # squash-merge 였으면 -m 1 없이
# 여러 개면 반복. 완료 후:
git push -u origin rollback/revert
# → PR 생성 후 squash-merge
```

## 방법 B — 백업 브랜치 강제 복원 (긴급 최후수단, 업그레이드 이력 삭제)

```bash
git fetch origin backup/pre-upgrade-20260721
git checkout -b rollback/hard origin/backup/pre-upgrade-20260721
git push -u origin rollback/hard
# → PR 로 main 반영이 안 되는 상황(전체 되돌림)이면:
git push origin backup/pre-upgrade-20260721:main --force-with-lease
```

⚠️ force push 는 업그레이드 커밋들을 main 히스토리에서 제거한다. A 가 불가한 경우에만.

## 롤백 후 검증 (어느 방법이든 필수)

1. Streamlit Cloud 가 새 커밋 픽업·재시작 확인 ("App started" 로그 또는 수십 초 대기 — CLAUDE.md 진단표).
2. `python test_smoke.py` (출장비/법인카드/위험성평가/개인정보/성희롱) — live 환경에서.
3. `grep -E "FAILED|ERROR|Exception" log.txt` 로 신규 오류 부재 확인.
4. DB 마이그레이션이 업그레이드에 포함됐던 경우: 코드 롤백만으로 불충분할 수 있음 —
   해당 마이그레이션 파일 상단의 Rollback 절차(예: flag 우회 → row DELETE) 를 따를 것.

## 안정화 판정 후 정리

업그레이드가 안정 판정되면: 본 문서의 앵커 표를 갱신(또는 문서 제거)하고
`backup/pre-upgrade-20260721` 삭제 가능.
