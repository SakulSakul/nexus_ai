# DF COMPASS 코딩 정책

`chunk_incident_nodes` silent-fail 사고(17+시간 진단, 9 PR 무력화)에서 도출한
재발 방지 정책. PR 작업 전후로 참고할 것.

## 1. DB Schema 변경 시 체크리스트

### 새 컬럼을 `.select()` 에 추가할 때
- [ ] Supabase Studio 에서 컬럼 실재 확인:
  ```sql
  SELECT column_name FROM information_schema.columns
  WHERE table_name = 'nexus_chunks';
  ```
- [ ] `app.py` 의 `_validate_db_schema()` checks 목록에 컬럼 반영
- [ ] smoke test 5 query 회귀 검증 (`python test_smoke.py`)

> RPC(stored procedure)가 반환하는 계산 필드와 물리 컬럼을 혼동하지 말 것.
> RPC 결과 dict 에 키가 있어도 테이블 `.select()`/`.contains()` 는 실패할 수 있다.
> (실제 사례: `chunk_incident_nodes` 는 RPC 반환 필드이지만 물리 컬럼 부재)

### 사례 (PR #221, #228)
- PR #221: `chunk_incident_nodes` 를 L2.0/L2.5 `.select()` 에 추가 (DB 컬럼 부재)
- 결과: `APIError 42703` → try/except silent → force-include 전체 무력화
- PR #228: select 에서 제거하여 fix

## 2. try/except 정책

### ❌ 금지
```python
except Exception:
    pass
```

### ✅ 권장
```python
except Exception as e:
    print(f"[component] FAILED: {type(e).__name__}: {e}",
          file=sys.stderr, flush=True)
    # critical path → UI signal
    _signal_critical_error("component", e)
```

### Critical path (silent fail 절대 금지)
- 모든 retrieval (hybrid_search, force-include L1/L2.0/L2.5/L3)
- LLM call (Gemini, Claude)
- Supabase write (query_logs 등)

## 3. PR 머지 전 체크리스트
- [ ] AST 검증 통과 (`python -c "import ast; ast.parse(open('FILE').read())"`)
- [ ] import 검증 통과
- [ ] 변경 위치는 line number 가 아닌 **context** 로 확인 (line 은 drift 함)
- [ ] 로그에서 `FAILED|ERROR|Exception` grep
- [ ] smoke test 5 query 통과

### Smoke test query (`test_smoke.py`)
| 질문 | 기대 키워드 |
|---|---|
| 출장비 어떻게 처리? | 출장비 |
| 법인카드 관리지침 | 법인카드 |
| 위험성평가는? | 위험성평가 |
| 개인정보 보호 어떻게? | 개인정보 |
| 성희롱 예방 | 성희롱 |

## 4. 진단 순서

1. 로그에서 실패 신호부터 (가장 **먼저** 나온 FAILED 가 root cause):
   ```bash
   grep -E "FAILED|ERROR|Exception|SCHEMA_CHECK" log.txt
   ```
2. force-include / top_k 흐름 확인:
   ```bash
   grep -E "force_include|guaranteed_in_top_k|matched_docs" log.txt
   ```

### 해석
- `force_include ... FAILED` + `guaranteed_in_top_k=0` → DB/스키마 오류 (fetch 단계)
- `guaranteed_in_top_k=N` 인데 답변 fail → LLM prompt / 합성 단계

## 5. 운영 caveat — Streamlit Cloud
- reboot 직후 처음 ~수 query 는 module hot-reload 로 stale 가능
- 안정성: deploy logs 의 "App started" 확인 또는 수십 초 대기 후 query
- startup `_validate_db_schema()` 결과(`STARTUP_SCHEMA_CHECK`)를 로그에서 확인
