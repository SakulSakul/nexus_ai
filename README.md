# DESIGN SYSTEM — "Warm Editorial"

> DF COMPASS 코드(`/.streamlit/config.toml`, `ui/styles.py`, `ui/render.py`, `app.py`)에서 추출한
> 실제 디자인 시스템. 다른 앱에 이식 가능하도록 **브랜드 고유값**과 **구조(이식 대상)**를 구분 표기.
> 🔁 = 앱마다 교체하는 브랜드 값 · 🔒 = 그대로 유지하는 시스템 규칙.

---

## 1. 철학

**Warm Editorial.** 차가운 순수 white/gray 대신 **웜 크림(parchment) 뉴트럴**을 바탕으로,
액센트는 **브랜드 시그니처 컬러 한 가지만** 절제해서 쓴다. 정보 밀도가 높은 업무용 툴이지만
"읽는 문서"처럼 느껴지게 하는 게 목표 — 그래서 본문 line-height·letter-spacing·한글 줄바꿈을
세심하게 잡는다.

원칙 세 가지 🔒
1. **액센트는 액센트로만.** 시그니처 컬러는 강조·인터랙션(링크 hover, 탭 인디케이터, 4px 톱바)에만.
   넓은 면(배경·본문)에 칠하지 않는다.
2. **웜 뉴트럴.** 모든 회색은 황갈 언더톤을 가진 웜 톤. 순수 #000/#fff/#888 회피.
3. **크롬 최소화.** Streamlit 기본 메뉴·푸터·툴바·decoration 숨김. 화면은 콘텐츠가 전부.

---

## 2. 색상 토큰

`ui/styles.py`의 `:root`가 **권위 있는 팔레트**다 (CSS `!important`로 Streamlit 테마를 덮어씀).

```css
:root {
  --c-primary:    #1F1E1D;  /* 웜 near-black — 구조/제목 */
  --c-accent:     #C8102E;  /* 🔁 시그니처 레드 — 액센트 전용 */
  --c-accent-dark:#9A0C24;  /* 🔁 액센트 hover */
  --c-accent-bg:  #FCEBEE;  /* 🔁 액센트 하이라이트 배경 */
  --c-text:       #3D3C38;  /* 웜 그레이 본문 */
  --c-caption:    #87867F;  /* 웜 그레이 캡션/메타 */
  --c-muted:      #B5B3A9;  /* 웜 뉴트럴 (비활성) */
  --c-border:     #E8E6DC;  /* 크림 보더 */
  --c-surface:    #FAF9F5;  /* 카드/표면 — 옅은 크림 */
  --c-bg:         #F5F4ED;  /* Parchment — 배경 (editorial 핵심) */
}
```

| 토큰 | 값 | 역할 | 이식 |
|---|---|---|---|
| `--c-bg` | `#F5F4ED` | 전체 배경(parchment) | 🔒 웜 크림 유지 |
| `--c-surface` | `#FAF9F5` | 카드/사이드바 표면 | 🔒 |
| `--c-border` | `#E8E6DC` | 1px 보더 | 🔒 |
| `--c-primary` | `#1F1E1D` | 구조·제목 | 🔒 웜 near-black |
| `--c-text` | `#3D3C38` | 본문 | 🔒 |
| `--c-caption` | `#87867F` | 캡션/메타 | 🔒 |
| `--c-muted` | `#B5B3A9` | 비활성 | 🔒 |
| `--c-accent` | `#C8102E` | 시그니처(액센트 전용) | 🔁 **앱 브랜드 컬러로 교체** |
| `--c-accent-dark` | `#9A0C24` | hover | 🔁 accent의 ~15% 어둡게 |
| `--c-accent-bg` | `#FCEBEE` | 하이라이트 배경 | 🔁 accent의 ~8% 틴트 |

**시맨틱 컬러(상태)** — `ui/render.py`
| 의미 | 색 | 용례 |
|---|---|---|
| 성공/높음 | `#1F7A3A` 🟢 | 높은 신뢰도 |
| 주의/보통 | `#A07020` 🟡 | 보조 참고 |
| 위험/낮음·critical | `#A93226` 🔴 | hit 부족 / 중대 항목 |
| 메타/인용 | `#475569` | 출처·근거 캡션 |

> ⚠️ 정합성 노트: `.streamlit/config.toml`은 아직 cool 팔레트(`#FFFFFF`/`#F4F6F8`/`#1A1A1A`)다.
> 실제 화면은 CSS가 덮어써서 warm으로 뜨지만, **config.toml도 위 warm 값으로 맞추는 걸 권장**
> (Streamlit이 CSS 로드 전 잠깐 cool로 깜빡이는 FOUC 방지).

---

## 3. 타이포그래피

```css
--font: 'Pretendard', -apple-system, 'Apple SD Gothic Neo', 'Noto Sans KR', sans-serif;
```

| 용도 | 폰트 | 이식 |
|---|---|---|
| UI/본문 | **Pretendard** → 시스템 한글 폰트 폴백 | 🔒 |
| 디스플레이/제목(선택) | `SDDOES Myeongjo` (브랜드 명조) | 🔁 앱 브랜드 명조 또는 생략 |

**한글 렌더링 규칙 🔒** (`app.py` visual-polish 블록 — 한글 가독성의 핵심)
```css
line-height: 1.75;
letter-spacing: -0.005em;
word-break: keep-all;      /* 한글 어절 단위 줄바꿈 */
overflow-wrap: anywhere;   /* 영문/숫자 긴 토큰은 break */
-webkit-font-smoothing: antialiased;
text-rendering: optimizeLegibility;
```

---

## 4. 레이아웃 & 크롬

| 요소 | 규칙 | 이식 |
|---|---|---|
| 페이지 | `layout="wide"`, `page_icon="🧭"` | 🔁 아이콘은 앱 정체성 이모지 |
| 톱 프레임 | 상단 고정 **4px 바, 액센트 컬러** (`.nx-topbar`, z-index 9999) | 🔒 (액센트만 교체) |
| 보더 | 1px `--c-border` | 🔒 |
| 사이드바 | `--c-surface` 배경 + 1px 우측 보더 | 🔒 |
| 숨김 | `#MainMenu`, `footer`, `stToolbar`, `stDecoration`, `stHeader` 투명 | 🔒 크롬 최소화 |
| 버튼 | 흰 배경 · 1.5px near-black 보더 · hover 시 **near-black 채움 + 흰 글자**(모노크롬 토글) | 🔒 |

---

## 5. 컴포넌트 패턴

**신뢰도 칩 (Confidence chip)** 🔒 — RAG/검색 결과의 신뢰도를 한 줄로
- 🟢 `높은 신뢰도` (`#1F7A3A`)
- 🟡 `보조 참고 — 정확한 사항은 {담당부서} 확인` (`#A07020`)
- 🔴 `검색 hit 부족 — {담당부서} 확인 권장` (`#A93226`)
- 폰트 12px, 라운드 칩, **부서명을 동적으로 주입**해 "어디 물어보라"를 명시.

**경과 시간 칩** 🔒 — `⏱️ N초 경과`, 배경 `#FAF6F1`, 보더 `#EDE6DC`, 숫자에 액센트 컬러.

**Thinking 인디케이터** 🔒 — 44px 원, 배경 `rgba(accent, 0.08)`, 서브텍스트 `#9A968D`.

**베타/고지 배너** 🔒 — `🛡️` + 회색 배경(`#f4f4f4`)·12px, 프라이버시 안내. prod 환경에선 숨김.

**탭/링크** 🔒 — 활성 탭 인디케이터·링크 hover underline = 액센트 컬러.

---

## 6. 콘텐츠(답변) 디자인 시스템 ★

> 컴플라이언스/RAG 툴의 진짜 차별점. 시각 토큰보다 **이게 더 이식 가치가 크다.**

**섹션 구조** 🔒 — 답변은 고정 섹션, 이모지 헤더로 스캔성 확보
```
📋 사규 기준      ← 원칙·근거 (rule)
⚖️ 징계 기준      ← 처벌·관리책임 (penalty)
권장 행동         ← 다음 액션 (3단계 이내)
```
- 섹션은 항상 같은 순서. 내용 없으면 "해당 유형 문서가 검색되지 않았습니다" 한 줄(섹션 누락 금지).
- (도메인에 따라 섹션 추가/교체 — 예: 사례 섹션 `📂`은 데이터 있을 때만.)

**인용 규칙** 🔒
- 근거는 컨텍스트 헤더 태그(`[사규]`/`[징계기준]` 등)를 정확히 따라 구분.
- 인용 메타는 작은 회색 캡션(`#475569`, 12px), 중대 항목은 italic + `#A93226`.
- 출처 없는 내용 생성 금지.

**부서 라우팅 언어** 🔒
- 관리부서가 명시된 사규: "자세한 사항은 **○○팀**에 문의" 처럼 **실제 부서로 직접 안내**.
- 미명시: "관할 담당 부서" 같은 일반 문구 (부서명 임의 생성 금지).

**평결 이모지** 🔒 — `✅ pass / ⚠️ warn / (fail)`.

---

## 7. 보이스 & 톤 🔒

- 격식 있는 한국어 컴플라이언스 레지스터. 단정·간결.
- 거부(전체 차단) 대신 **부분 안내 + 담당부서 연결**.
- 추정 금지 — 근거 없는 단정·부서명 창작 안 함.
- 프라이버시/베타 고지를 화면에 명시.

---

## 8. 새 앱에 적용 체크리스트

1. **토큰 복사** — §2 `:root` 블록을 새 앱 CSS에 그대로. `--c-accent`(+dark/bg) 3개만
   새 브랜드 컬러로 교체. 웜 뉴트럴 6개는 유지.
2. **config.toml 정합** — `primaryColor`=새 accent, `backgroundColor`=`#F5F4ED`,
   `secondaryBackgroundColor`=`#FAF9F5`, `textColor`=`#3D3C38`, `base="light"`.
3. **타이포** — `--font` 그대로. §3 한글 렌더링 블록 필수 복사.
4. **크롬** — 4px 톱바 + 크롬 숨김 + 모노크롬 버튼 §4 복사. `page_icon`만 교체.
5. **컴포넌트** — 신뢰도 칩·경과 칩·thinking·배너 패턴 §5 재사용(색만 시맨틱 토큰으로).
6. **콘텐츠 시스템** — §6 섹션 구조·인용·부서 라우팅을 도메인에 맞게 헤더/섹션만 바꿔 적용.
7. **톤** — §7 그대로.

**한 줄 요약:** *웜 크림 바탕 + 브랜드 액센트 1색 + Pretendard + 한글 렌더링 디테일 +
이모지 섹션/신뢰도 칩/부서 라우팅* = 이 시스템의 정체성. 액센트 컬러와 page_icon, 섹션 헤더만
앱마다 갈아끼우면 된다.
