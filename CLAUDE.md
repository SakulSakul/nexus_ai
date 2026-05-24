# CLAUDE.md — DF COMPASS

AI(Claude Code)가 이 저장소에서 작업할 때 따르는 원칙.
기반: Andrej Karpathy LLM coding pitfalls 4 principles + DF COMPASS 운영 원칙.

---

## Part 1 — Karpathy 4 Principles

### 1. Think Before Coding
**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them — don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

### 2. Simplicity First
**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

### 3. Surgical Changes
**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it — don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

### 4. Goal-Driven Execution
**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan with steps and verification checkpoints.

---

## Part 2 — DF COMPASS 운영 원칙

이번 17+시간 `chunk_incident_nodes` silent-fail 사고(9 PR 무력화)에서 도출.
4 principles 가 코드를 다스린다면, 이 절은 DF COMPASS 특유의 함정을 막는다.

### A. 근본 구조적 해결
- 증상이 아니라 root cause 를 고친다. cap 하나 고치면 다음 cap 에서 또
  깨지는 whack-a-mole 은 신호다 — 한 단계 위(데이터가 들어오는 지점)를 의심하라.
- "이 가설이 정말 root cause 인가?"를 PR 시작 시 명시한다 (Think Before Coding).

### B. 진단은 log grep first
실패를 시뮬레이션으로 추측하기 전에 **로그부터** 본다:
```bash
grep -E "FAILED|ERROR|Exception|SCHEMA_CHECK" log.txt   # 가장 먼저 나온 FAILED = root cause
grep -E "force_include|guaranteed_in_top_k|matched_docs" log.txt
```
- `force_include ... FAILED` + `guaranteed_in_top_k=0` → fetch/스키마 단계 오류
- `guaranteed_in_top_k=N` 인데 답변 fail → LLM prompt / 합성 단계

### C. DB schema 검증 — RPC 계산 필드 ≠ 물리 컬럼
- 새 컬럼을 `.select()`/`.contains()` 에 넣기 전 실재 확인:
  ```sql
  SELECT column_name FROM information_schema.columns WHERE table_name='nexus_chunks';
  ```
- **RPC(stored procedure)가 반환하는 키**가 dict 에 있다고 해서 테이블에 물리
  컬럼이 있는 건 아니다. 직접 `.select()` 는 `APIError 42703` 으로 실패한다.
  (실제 사례: `chunk_incident_nodes`)
- `app.py _validate_db_schema()` checks 목록에 critical 컬럼을 반영한다.

### D. silent fail 금지
```python
# ❌ 금지
except Exception:
    pass

# ✅ critical path (retrieval / LLM / Supabase write)
except Exception as e:
    print(f"[component] FAILED: {type(e).__name__}: {e}", file=sys.stderr, flush=True)
    _signal_critical_error("component", e)   # UI 가시화
```

### E. smoke test 게이트
PR 머지 전 회귀 검증:
```bash
python test_smoke.py   # 출장비 / 법인카드 / 위험성평가 / 개인정보 / 성희롱
```

### F. 변경 위치는 line number 가 아닌 context 로
라인 번호는 drift 한다. spec 의 line 번호를 맹신하지 말고 실제 코드를
grep/read 로 확인한 뒤 surgical 하게 고친다 (Surgical Changes).

---

## Part 3 — 작업 워크플로 (사용자 표준 지시)

- main 으로 바로 push. 불가하면 PR 생성 후 즉시 squash-merge.
- 작업 시작 시 `작업 시작!`, 완료 시 `작업 완료!` 출력.
- 8-step 워크플로의 각 단계마다 진척 바 + % 표시.
- 커밋/PR 메시지에 모델 식별자를 넣지 않는다.
- 모든 작업/검증은 `/home/user/nexus_ai` 안에서 (git signing).

> 운영자용 상세 체크리스트는 `docs/CODING_POLICY.md` 참조.
> 이 파일(CLAUDE.md)은 AI 행동 원칙, CODING_POLICY.md 는 운영 절차.
