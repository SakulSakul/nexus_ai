# NEXUS AI

사내 컴플라이언스 어시스턴트 — 사규·윤리강령·사례집·징계규정 기반 RAG 챗봇.

> **현재 단계: 베타 테스트 (개인 인프라).**
> 정식 OPEN 시 Supabase 프로젝트와 Gemini API 청구 모두 회사 계정으로 전환 예정.
> 개인 Gemini API 키는 **유료 티어(학습 비활성)** 로 운영합니다.

---

## 스택

- 프론트엔드: Streamlit
- LLM (chat): **Gemini 2.5 Pro (primary) + Claude Opus 4.7 (fallback)** — Gemini 가 503/429 시 Claude 로 자동 전환
- LLM (embedding): Google `gemini-embedding-001`
- 벡터/메타 저장소: Supabase (PostgreSQL + pgvector)
- 검색: Hybrid (vector cosine + pg_trgm) + Reciprocal Rank Fusion

---

## 베타 단계 운영 원칙

1. **참가자 한정** — 5~10명 내외 임직원에게만 URL 공유, 무차별 공개 금지.
2. **본 환경 명시** — 메인 화면 상단 "BETA · 개인 인프라" 배너 상시 노출 (`NEXUS_ENV=beta-personal`).
3. **참가자 사전 동의 필수** — 첫 진입 시 `beta_consents` 테이블에 성명·사번·동의서 버전 기록.
   회사-Google DPA 미수립 / 처리방침 미게시 상태에서의 베타임을 명시적으로 고지하고 동의받음.
   동의서 문구 변경 시 `NEXUS_CONSENT_VERSION` 만 올리면 전 참가자 재동의 자동 강제.
4. **비용 가드** — 1세션당 일일 100회 한도 (`NEXUS_DAILY_QUERY_LIMIT`).
5. **답변 품질이 1차 KPI** — 사용자 👍/👎 피드백을 `query_logs.feedback` 에 누적, Admin → 레이더 탭에서 비율 모니터링.
6. **Phase 3.5 검수 회차** — 도메인 샘플 50~100건을 등록하고 주 1회 회차 실행, 통과율 80% 이상 유지.

---

## 환경 변수 / Secrets

| 키 | 필수 | 기본값 | 설명 |
|---|---|---|---|
| `SUPABASE_URL` | ✅ | — | |
| `SUPABASE_KEY` | ✅ | — | anon 키 |
| `SUPABASE_SERVICE_ROLE_KEY` | ✅ | — | 관리자 영역 전용 |
| `GEMINI_API_KEY` | ✅ | — | 유료 티어(학습 비활성) 권장. 임베딩 + chat primary |
| `ANTHROPIC_API_KEY` | | — | 설정 시 chat fallback 으로 자동 활성. 미설정이면 Gemini 단독 |
| `ADMIN_PASSWORD` | ✅ | — | 관리자 게이트 |
| `NEXUS_ENV` | | `beta-personal` | `beta-personal` / `beta-corp` / `prod` |
| `NEXUS_SHOW_THINKING` | | `true` | **항상 ON 권장** — 임직원이 "왜 이 답이 나왔는지" 검증할 수 있어야 신뢰가 생김. expander 로 접혀 있어 첫 화면 노이즈 없음. 운영 토큰 비용이 실제 이슈가 될 때만 `false`. |
| `NEXUS_DAILY_QUERY_LIMIT` | | `100` | 세션당 일일 한도 |
| `NEXUS_CONSENT_VERSION` | | `v1` | 베타 동의서 버전. 문구 변경 시 올리면 자동 재동의 강제 |
| `NEXUS_CHAT_PROVIDER` | | `gemini` | 1차 챗봇. `gemini` / `claude` |
| `NEXUS_CHAT_FALLBACK` | | `claude` | 1차가 503/429 transient 실패 시 자동 전환. `''` 면 fallback 비활성 |
| `NEXUS_CLAUDE_MODEL` | | `claude-opus-4-7` | Claude 모델 ID. 비용 우선이면 `claude-sonnet-4-6` |
| `NEXUS_CLAUDE_EFFORT` | | `medium` | Claude `output_config.effort`. `low`/`medium`/`high`/`xhigh`/`max` |
| `NEXUS_CHAT_MODEL` | | `gemini-2.5-pro` | |
| `NEXUS_EMBED_MODEL` | | `gemini-embedding-001` | |
| `NEXUS_EMBED_DIM` | | `768` | 스키마 `vector(768)` 와 일치 |
| `NEXUS_TOP_K` | | `3` | |
| `NEXUS_TEMPERATURE` | | `0` | |
| `NEXUS_TOP_P` | | `0.1` | |

---

## DB 마이그레이션 순서

```
db/01_schema.sql          # 기본 스키마 + 키워드/핫라인 시드
db/02_hybrid_search.sql   # nexus_hybrid_search RPC (구버전)
db/03_review.sql          # Phase 3.5 검수 테이블
db/04_beta_hooks.sql      # 베타 hook 컬럼 + 감사 로그 + effective_date 필터
                          # ⚠ 04 는 02 의 함수를 CREATE OR REPLACE 로 덮어씀
                          # (시그니처에 as_of_date / 반환에 owning_department 추가)
db/05_beta_consents.sql   # 베타 참가자 동의 기록 테이블
db/06_chat_provider.sql   # query_logs 에 chat_provider / chat_model_version 컬럼
```

`db/04_beta_hooks.sql` 가 추가하는 항목:
- `nexus_documents.owning_department`, `source_storage_path`
- `nexus_chunks.embed_model_version`
- `query_logs.env`, `user_id_hash`, `access_level`, `feedback`, `feedback_comment`, `embed_model_version`
- `admin_audit_logs` 테이블
- `nexus_hybrid_search` 시행일(effective_date) 필터 + `as_of_date` 인자

---

## Supabase Storage 버킷

원본 DOCX 보관용 버킷을 **수동 생성**해야 합니다 (없으면 silently skip — 적재는 계속 성공).

- 버킷명: `nexus-docs-original`
- 공개 여부: **Private** (service_role 만 read/write)
- 적재 경로: `{document_id}/{filename}.docx`

---

## Phase 3.5 검수 샘플 적재 가이드

1. `samples/review_samples_seed.csv` 를 시작점으로 사용.
2. **목표 50~100건** — 카테고리(공통/CSR/공정거래/정보보안/안전/재무/영업/총무/환경) × 심각 트리거(safety/harassment/normal) 조합으로 균형 있게.
3. Admin → 검수 (Phase 3.5) → CSV 일괄 탭에서 업로드.
4. 회차 실행 후 통과율 80% 미만이면 프롬프트/키워드/마스킹 보강.

**CSV 컬럼**: `domain, category, question, expected_keywords, expected_citation, expected_critical, expected_critical_kind, notes`
- `expected_keywords` 는 `;` 구분
- `expected_critical` 은 `true/false`

---

## 베타 → 회사 계정 이관 체크리스트

이관 시점에 **데이터/인증/비용 책임 주체**가 모두 회사로 넘어가야 합니다.

### A. 인프라 신설 (회사 계정)
- [ ] 회사 Supabase 프로젝트 신규 생성 (region 동일)
- [ ] 회사 Google Cloud 프로젝트 + Gemini API 결제 연결 (학습 비활성 옵션 확인)
- [ ] 회사 Streamlit 호스팅 또는 사내 K8s/Cloud Run 인스턴스 결정
- [ ] `nexus-docs-original` 버킷 신규 생성 (private)

### B. 스키마 + 코드 마이그레이션
- [ ] `db/01_schema.sql` → `db/04_beta_hooks.sql` 순서대로 신 DB 에 실행
- [ ] `idx_nexus_chunks_embedding` 를 ivfflat → HNSW 로 교체 검토
- [ ] `tsvector` 토크나이저 `simple` → `mecab-ko` 또는 `pg_bigm` 로 교체 검토

### C. 데이터 이관
- [ ] **사규/사례 원본 DOCX** 를 새 버킷에 재업로드 → admin UI 로 재적재 (재임베딩 발생, Gemini 비용 정산)
- [ ] **`query_logs`(베타) 는 이관하지 않고 폐기** — 정보주체(베타 참가자) 동의 범위가 다름
- [ ] **`beta_consents`(베타 동의 기록) 도 함께 폐기** — 정식 운영의 처리방침 고지로 대체됨
- [ ] **`hotline_config`** 회사 실제 URL/번호로 재입력 (`example.invalid` placeholder 100% 교체)
- [ ] **`critical_keywords`** 도메인 전문가 검수본으로 교체
- [ ] **`review_samples`** 베타에서 다듬은 골든셋 export → 회사 DB import

### D. 비밀번호/키 전면 재발급
- [ ] `SUPABASE_*` 키 회사 프로젝트 키로 교체
- [ ] `GEMINI_API_KEY` 회사 GCP 키로 교체
- [ ] `ADMIN_PASSWORD` 신규 발급 (개인 비번 100% 폐기)
- [ ] `NEXUS_ENV` 를 `beta-corp` → 검증 후 `prod` 로 승격
- [ ] `NEXUS_SHOW_THINKING` 은 **`true` 유지** 권장 (답변 신뢰성·투명성). 운영 토큰 비용이 실측상 이슈가 될 때만 `false` 검토.

### E. 거버넌스 (회사 IT/법무 협업)
- [ ] SSO(SAML/OIDC) 통합 설계 → `query_logs.user_id_hash` / `access_level` 채우기 시작
- [ ] 개인정보처리방침 게시
- [ ] Gemini DPA(데이터 처리 계약) 확인
- [ ] 감사 로그(`admin_audit_logs`) 보존 정책(예: 1년) 명문화
- [ ] `query_logs` 보존 정책(예: 90일 후 익명 집계만) cron 작성

### F. 검증
- [ ] Phase 3.5 검수 회차 1회 통과 (pass_rate ≥ 0.80)
- [ ] PII 마스킹 테스트 통과
- [ ] 핫라인 URL 실제 클릭 검증
- [ ] 베타 참가자 대상 마이그레이션 안내 발송

---

## 개발

```bash
pip install -r requirements.txt
streamlit run app.py
```

`pages/admin.py` 는 자동으로 별도 페이지로 노출되며 `ADMIN_PASSWORD` 게이트 뒤에 있습니다.
