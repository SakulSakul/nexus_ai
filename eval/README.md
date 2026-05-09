# DF COMPASS · Retrieval Eval (PR-Q1)

Silent regression 방지를 위한 retrieval-only eval 인프라. LLM 호출은 안
하므로 비용 거의 없음 (embed 호출만).

## 실행

```bash
python eval/run.py
# 옵션
python eval/run.py --fixtures eval/fixtures.yaml --top-k 3
python eval/run.py --no-write   # 결과 JSON 미생성 (CI dry-run)
```

필요 환경변수:
- `SUPABASE_URL`, `SUPABASE_KEY` — anon 키
- `GEMINI_API_KEY` — `embed_one` 호출용

(streamlit secrets 도 자동 fallback — `core/config.py:get_secret` 경유.)

## 출력

콘솔:
```
id    category       P     R    best   hit  pass
q01   general     1.00  1.00  0.0312    3   ✅
q09   negative    1.00  1.00  0.0000    0   ✅
...
Avg precision: 0.85  Avg recall: 0.78
best_score range: min 0.0000  max 0.0328  avg 0.0214
```

`best_score` 는 RRF score (`1/(60 + r_vec) + 1/(60 + r_kw)`). 절대값
범위 0~0.0328 (둘 다 1위면 max). cosine 0-1 아님.

JSON: `eval/results/<timestamp>.json` — 전체 metric + per-fixture detail.

## fixture 추가/정정

`eval/fixtures.yaml` 편집:

```yaml
- id: q11
  question: "..."
  expected_sources:
    - "(분류) 사규명 부분 문자열"
  category: general | critical | multi-domain | negative
```

`expected_sources` 는 **substring 매치**. `doc_title` 에 해당 문자열이
포함되면 hit 인정. `negative` 카테고리는 빈 list 두면 hit 0건이 정답.

## Pass/Fail 기준 (starter)

- general/critical/multi-domain: `recall >= 0.5` (expected 중 절반 이상 hit)
- negative: `hit_count == 0`

운영 안정화 후 임계값 조정.

## confidence threshold 튜닝 baseline

`best_score` 분포가 `NEXUS_CONFIDENCE_HIGH` / `NEXUS_CONFIDENCE_MEDIUM`
환경변수 튜닝 데이터로 사용됨 (PR-C1). 첫 추정값:
- HIGH: 0.025 (vec·kw 모두 상위권)
- MEDIUM: 0.015 (한쪽만 잡혔거나 mid-rank)

라이브 분포 확인 후 조정.

## 주의

- core/ 식별자 변경 0 — `hybrid_search` 그대로 import.
- LLM 미호출 — 답변 quality 는 본 eval 로 측정 안 됨. retrieval recall/
  precision 만 baseline. 답변 quality 회귀는 별도 LLM-as-judge 또는
  사용자 피드백(`query_logs.feedback_*`) 으로 측정.
- `expected_sources` 매핑은 사쿨 도메인 지식 영역. PR 머지 후 정정.
