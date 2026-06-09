# 🧭 DF COMPASS

> **신세계디에프 사내 컴플라이언스 어시스턴트** — 윤리강령, 안전, 환경, 재무 등 사내의 모든 규정을 자연어로 묻고 가장 정확한 답을 즉시 제공하는 AI 챗봇입니다.

🌱 **현재 상태:** 베타 테스트 진행 중 (개인 인프라)

📅 **정식 OPEN:** 회사 인프라 전환 예정

🔐 **보안:** 모든 API 는 데이터 학습이 비활성화된 유료 티어로 안전하게 운영됩니다.

---

## 🤔 DF COMPASS 가 뭐예요? (AI 를 모르는 분들을 위해)

회사 사규는 정말 많습니다. 300개가 넘는 PDF 문서가 있고, 누가 뭘 물어봐도 답을 찾으려면 한참을 헤매야 하죠. **DF COMPASS 는 24시간 대기 중인 "사내 사규 전문 사서" 입니다.**

> 👤 **임직원:** "출장비 정산은 어떻게 해요?"
>
> 🧭 **DF COMPASS:**
> 1. "출장비" 관련 사규를 도서관에서 빠르게 찾고 (검색)
> 2. 관련 내용을 정확히 읽고 이해한 뒤 (이해)
> 3. 친절하고 명확한 답변으로 정리해서 보여줍니다 (생성)
>
> 📋 **답변:** "국내출장비는 교통비/일당/숙박료로 구성됩니다. 숙박료는 100,000원 이내 실비... *(+ 사규 원문 자동 인용)*"

**📚 도서관 사서 비유**

- **일반 검색 (구글/인트라넷):** "출장비" 검색 → 관련된 수십 개의 문서 리스트만 보여줌 → 본인이 직접 문서를 열어 읽고 정리해야 함.
- **DF COMPASS (AI):** "출장비" 질문 → **관련 사규를 AI 가 찾아 읽고 + 요약 정리된 답변을 주며 + 증거(출처)까지 달아줌!**

---

## 🎯 주요 기능 (사용자가 체감하는 혁신)

### 1️⃣ 압도적으로 빠른 답변 ⚡

- **일반 질문:** 10 ~ 30초
- **단순 행정 안내:** 0.6초
- **자주 묻는 질문 (Fast Path):** **0.8초** ⭐

> 병원의 '하이패스' 처럼, "클린뱅크 등록" 같이 뻔하고 자주 들어오는 질문은 AI 가 분석할 필요 없이 **0.8초 만에 즉시 답변** 을 쏩니다.

### 2️⃣ 팩트 기반의 사규 인용 ⭐

답변 하단에 항상 정확한 출처가 명시됩니다. AI 가 거짓말을 지어내는 현상(Hallucination)을 원천 차단했습니다.

- 예: `📎 (재무) 국내출장비 관리 지침`
- 예: `📎 (공통) 임직원 징계기준`

### 3️⃣ 철통같은 안전 및 응급 처리 🚨

폭행, 성희롱, 중대재해 같은 긴급/민감 사안은 더 정교하게 다룹니다.

- **일반 진료:** 일반 AI (Gemini) 1명이 진단
- **응급 진료:** **최고 지능 AI (Claude Opus) 3명이 동시에 진단하고 다수결(3중 2표 이상)로 판정** 하여 핫라인 (담당 부서) 을 자동 안내합니다.

> 운영 환경 30일 테스트 결과: 오분류 0건 ⭐

### 4️⃣ 범위 외 질문(OOS) 친절 안내 🗺️

사규와 무관한 "회의실 예약 어떻게 해?", "오늘 점심 메뉴 뭐야?" 같은 질문에 AI 가 억지로 답을 지어내지 않습니다.

- 0.6초 만에 "해당 문의는 담당 부서로 문의해 주세요" 라며 정확한 부서로 길을 안내합니다.

---

## 🤖 어떻게 작동하는가? (Architecture)

### Modular RAG (질문 종류별 지능형 라우팅)

모든 질문을 똑같이 무겁게 처리하면 느리고 비쌉니다. DF COMPASS 는 **질문의 난이도를 스스로 판단하여 최적의 경로로 보냅니다.** (병원의 환자 분류(Triage) 시스템과 동일)

| 질문 종류 | 예시 | 처리 방식 (경로) | 응답 시간 |
| --- | --- | --- | --- |
| **자주 묻는 질문** | "자진 신고" | 캐시 메모리에서 즉시 반환 (Fast Path) | **0.8초** ⭐ |
| **범위 외 질문** | "회의실 예약" | 담당 부서 즉시 안내 (OOS Routing) | **0.6초** ⭐ |
| **일반 질문** | "출장비 정산" | 사규 하이브리드 검색 + 요약 생성 | 10~30초 |
| **복잡 질문** | "계약 시 주의사항" | 다중 검색 + 종합 분석 추론 | 30~60초 |
| **긴급 사안** | "폭행 사건 발생" | **Claude Opus × 3 다수결 (안전 최우선)** | 30~60초 |

### Hybrid Search & Safety Guard

- **하이브리드 검색:** 단어의 의미를 이해하는 검색 (Vector) 과 정확한 키워드를 찾는 검색 (BM25) 을 결합하여, 사내 은어나 줄임말을 써도 찰떡같이 문서를 찾아냅니다.
- **동의어 양방향 매칭:** 약칭(예: "외감규정")과 정식명("외부감사 및 회계 등에 관한 규정")을 양방향으로 연결해, 어느 쪽으로 물어도 동일 문서를 찾아냅니다.
- **다층 안전망:** 질문 분류기 → 금지어 프롬프트 → AI 3중 교차검증(Self-Consistency) → 최종 답변 재검증(Verdict)을 통해 위험 사안 오안내율 0%를 유지합니다.
- **PII 보호:** 입력 단계에서 개인정보/부서 식별자를 마스킹하되, 일반명사(회의실·교육실 등)는 allowlist 로 보존해 검색 품질을 지킵니다.

---

## 📊 운영 성과 (2026-06 베타 기준)

- **🚀 응답 속도 최적화:** 30초 → **0.8초** (Fast Path 도입으로 약 40배 개선)
- **💰 비용 효율성:** 캐시 및 라우팅을 통해 불필요한 AI 호출을 방어
- **🛡️ 안전성:** Hallucination(환각) **0건**, Critical FP(긴급 사안 오분류) **0건** ⭐
- **✅ 코드 안정성:** PR #367 까지 머지, **GitHub Actions (Keyless CI) 자동 검증 시스템** + 골든 회귀 테스트 가동 중

---

## ⚙️ 기술 스택 (Tech Stack)

- **Frontend:** Streamlit (Python 기반 실시간 Streaming UI & Admin Dashboard)
- **AI / LLM:**
  - 메인 합성: `Gemini 3.5 Flash` (운영 기본 · `NEXUS_CHAT_MODEL` 로 override)
  - 긴급 모드: `Claude Opus 4.7` (Self-Consistency 3-sample 다수결)
  - 라우터/분류(OOS): `Claude Haiku 4.5`
  - 리랭커/질의 재작성: `Gemini 3.1 Flash-Lite`
  - 동의어 추출/자동 태깅: `Claude Opus 4.7`
  - 임베딩: `gemini-embedding-001` (768차원)
- **Database:** PostgreSQL (Supabase), `pgvector` (시맨틱 검색), `PgRoonga` + `Mecab` (한국어 형태소 분석), `pg_trgm`
- **CI/CD:** GitHub Actions — AST 문법 검증, Keyless Import 검증, SIM·피처플래그 Spot-check, Verdict 골든 회귀 가드

---

## 🚀 개발자 가이드 (Developer Guide)

### 실행 (Streamlit)

```bash
pip install -r requirements.txt
streamlit run app.py          # 임직원용 프론트엔드
# 어드민 대시보드: pages/admin.py (ADMIN_PASSWORD 게이트)
```

### 환경 변수 (Secrets)

| 키 (Key) | 필수 | 기본값 | 설명 |
| --- | --- | --- | --- |
| `SUPABASE_URL` / `KEY` | ✅ | — | DB 연결 정보 (Anon / Service Role) |
| `GEMINI_API_KEY` | ✅ | — | 구글 AI 유료 티어 (학습 비활성화) |
| `ANTHROPIC_API_KEY` | ✅ | — | 긴급 모드 / 분류기 / Fallback 용도 |
| `ADMIN_PASSWORD` | ✅ | — | 어드민 대시보드 진입 게이트 |
| `NEXUS_CHAT_MODEL` |  | `gemini-3.5-flash` | 메인 합성 모델 오버라이드 |
| `NEXUS_EMBED_MODEL` |  | `gemini-embedding-001` | 임베딩 모델 |
| `NEXUS_EMBED_DIM` |  | `768` | 임베딩 차원 (256/768/1536/3072) |
| `NEXUS_CLAUDE_MODEL` |  | `claude-opus-4-7` | 긴급 모드 / 동의어 추출용 Claude 모델 |
| `QUERY_CLASSIFIER_MODEL` |  | `claude-haiku-4-5` | OOS 라우팅 분류기 |
| `NEXUS_RERANK_MODEL` |  | `gemini-3.1-flash-lite` | 리랭커 모델 |
| `ENABLE_FAST_PATH` |  | `false` | 0.8초 캐시 응답 활성화 토글 |
| `ENABLE_OOS_ROUTING` |  | `false` | 범위 외 질문 조기 차단 활성화 토글 |
| `NEXUS_HYBRID_SEARCH_VARIANT` |  | `v2` | 검색 경로 (`v3_pgroonga` = PgRoonga+Mecab, 미설정 시 `v2` = to_tsvector+pg_trgm) |

### DB 마이그레이션

베이스 스키마는 `db/01_schema.sql` ~ 번호순으로 적용하며, RPC·피처별 마이그레이션은 `db/migrations/` 에 날짜순으로 정리되어 있습니다.

```sql
db/01_schema.sql          -- 기본 스키마 세팅 및 시드 데이터
db/02_hybrid_search.sql   -- Hybrid Search RPC (v2)
db/03_review.sql          -- 검수 테이블
db/04_beta_hooks.sql      -- 베타 모니터링 hook 및 감사 로그
...                       -- (db/05 ~ db/28 순차 적용)

-- 주요 migrations (db/migrations/, 날짜순):
db/migrations/20260513_nexus_hybrid_search_v3_pgroonga.sql  -- PgRoonga+Mecab Hybrid Search RPC (v3)
db/migrations/20260527_phase18_faq_cache.sql                -- FAQ Fast Path 캐시
db/migrations/20260530_phase18_5_2_oos_routing.sql          -- OOS Routing
db/migrations/20260530_phase19_2_synonym_dictionary.sql     -- 동의어 사전
```

*(원본 사규 DOCX 파일은 Supabase Storage `nexus-docs-original` Private 버킷에 수동 적재 필요)*

### 테스트

```bash
python -m pytest tests/                # 골든 회귀 테스트
#   tests/test_verdict_golden.py       — 인용/판정 회귀 가드
#   tests/test_pii_dept_allowlist.py   — PII 부서 allowlist 회귀
#   tests/test_gen_empty_completion.py — 빈 LLM 응답 backstop
python test_smoke.py                   # import / 응답경로 smoke
```

### 프로젝트 구조

```
app.py            # 임직원용 Streamlit 진입점
pages/admin.py    # 어드민 대시보드 (콘텐츠·품질·자동화·모니터링)
core/             # RAG 파이프라인 (retriever / chatbot / 라우팅 / 검증 / PII 등)
db/               # SQL 스키마 및 migrations
parser/           # DOCX 파서 및 ingest 파이프라인
eval/             # 평가 하네스 (fixtures + runner)
tests/            # 골든 회귀 테스트
ui/               # 렌더링 컴포넌트 (cards / feedback / render / styles)
```

---

## 🌱 로드맵 (Roadmap)

- **단기 (1~2주):** pytest 골든 게이트의 CI 필수 승격, 코드 품질 자동 검증 — 진정한 CI/CD 완성
- **중기 (1~3개월):** DB 기반 동의어 사전 Admin 패널(어휘 불일치 구조적 해소), Self-Learning FAQ (유저 로그 기반 자동 큐레이션), 사내 인프라 이전 및 **정식 OPEN**
- **장기 (3~6개월):** 인사 규정 분리 및 라우팅 고도화, 사규 Knowledge Graph 시각화 도입

---

## 📜 베타 테스트 운영 원칙

1. **제한적 접근:** 참가자 소수 대상 URL 한정 공유
2. **투명성:** "BETA · 개인 인프라" 배너 상시 노출
3. **사전 동의:** 최초 접속 시 참가자 사전 동의 필수 기록
4. **비용 보호:** 세션당 일일 질문 한도 적용

---

👨‍💻 **Author:** 신세계디에프 — *1인 개발 및 컴플라이언스 도메인 설계*

💡 **피드백 및 버그 리포트:** [GitHub Issues](https://github.com/sakulsakul/nexus_ai/issues)

🧭 **DF COMPASS — 사규의 나침반, 임직원의 컴플라이언스 안내자**
