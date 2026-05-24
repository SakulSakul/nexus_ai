"""DF COMPASS · personality / fun 묶음 (PR-Fun1).

empty-state 인사·Daily Tip·답변 후 격려 멘트의 random pool 과 fallback
hardcoded 인사를 한 곳에 모은다. UI 호출은 app.py 가 random.choice 또는
LLM 호출 (cache_data 데코) 로.

가드레일:
- core/ 식별자 무수정 (본 모듈은 신규 — 기존 식별자 영향 X).
- LLM 호출 비용 최소화 — empty-state 인사 1시간, Daily Tip 1일 cache.
- critical 답변 시 critical_pool 만 사용 (호출자가 ans.is_critical 분기).
- LLM 호출 실패 시 시간대·요일 반영 hardcoded fallback.
"""

from __future__ import annotations

import random
import re
from datetime import datetime
from typing import Any

try:
    from zoneinfo import ZoneInfo
    _KST = ZoneInfo("Asia/Seoul")
except Exception:
    _KST = None


# ── 답변 후 격려 멘트 random pool ──────────────────────────
NORMAL_CLOSING_POOL: tuple[str, ...] = (
    "수고 많으셨어요. 더 궁금한 점 있으시면 물어봐 주세요.",
    "오늘도 좋은 하루 되세요. 추가 질문 환영입니다.",
    "이 답변이 도움 됐길 바라요.",
    "더 알아보고 싶은 점 있으면 언제든 물어봐 주세요.",
    "도움 되셨길 바라요. 다른 질문도 환영합니다.",
    "차근히 잘 정리됐길 바라요.",
    "필요한 정보 더 있으면 편하게 물어보세요.",
)

CRITICAL_CLOSING_POOL: tuple[str, ...] = (
    "혼자 감당하지 마세요. CSR팀에 언제든 연락 주세요.",
    "도움이 필요하시면 핫라인에 문의 바랍니다.",
    "회사는 늘 곁에 있습니다. 필요할 때 핫라인을 이용해 주세요.",
)


def closing_remark(*, is_critical: bool) -> str:
    """답변 후 화면 caption 으로 표시할 격려 멘트 1개 random pick."""
    pool = CRITICAL_CLOSING_POOL if is_critical else NORMAL_CLOSING_POOL
    return random.choice(pool)


# ── empty-state 인사 fallback (LLM 다운 시) ─────────────────
# 시간대·요일 반영 rotation pool. LLM 호출 실패해도 personality 살림.
# PR #111: 각 bucket 별 3+ 문장 random rotation (반복 노출 시 다양성).
_GREETINGS: dict = {
    "weekend": [
        "주말에도 수고 많으십니다. 무엇을 도와드릴까요?",
        "주말 출근하신 분들, 컴플라이언스 질문 편하게 주세요.",
        "주말이라도 사규는 같이 봅니다. 무엇을 도와드릴까요?",
    ],
    "friday_pm": [
        "주말 앞두고 잘 정리하세요. 사규 관련 질문은 언제든 환영입니다.",
        "금요일 오후, 한 주 마무리 잘 하세요. 도와드릴 일 있으면 알려주세요.",
        "주말 들어가시기 전에 정리할 사규 있으면 같이 보겠습니다.",
    ],
    "monday_am": [
        "한 주 시작 좋습니다. 사규·윤리 관련 궁금한 점 편하게 물어보세요.",
        "월요일 아침, 좋은 한 주 되세요. 컴플라이언스 도움 필요하면 알려주세요.",
        "이번 주도 시작합니다. 사규 관련 궁금증 풀어드릴게요.",
    ],
    "morning": [
        "안녕하세요. DF COMPASS 입니다. 좋은 아침입니다.",
        "좋은 아침입니다. 오늘도 함께 사규를 확인해보겠습니다.",
        "안녕하세요. 오늘 하루도 컴플라이언스로 든든하게 시작해요.",
    ],
    "noon": [
        "점심 시간 수고 많으십니다. 답변이 필요하면 편하게 질문해 주세요.",
        "점심 잘 드셨나요? 사규 질문도 식후로 부담 없이 던져 주세요.",
        "한낮의 컴플라이언스 시간입니다. 무엇을 도와드릴까요?",
    ],
    "afternoon": [
        "수고 많으십니다. 무엇을 도와드릴까요?",
        "오후 업무 도중 사규 확인이 필요하면 바로 물어봐 주세요.",
        "한창 바쁘실 시간이지만, 사규 질문은 빠르게 답해드립니다.",
    ],
    "evening": [
        "오늘 하루도 고생 많으셨습니다. 마무리 전에 답변이 필요하면 도와드릴게요.",
        "퇴근 전 마지막 정리하실 사규 있으면 같이 봅니다.",
        "오늘 하루 마무리 잘 하시고, 사규 관련 궁금증 정리하고 가세요.",
    ],
    "night": [
        "야간에도 수고 많으십니다. 사규 관련 질문은 언제든 환영입니다.",
        "늦게까지 수고하시네요. 도움이 필요하면 편하게 물어봐 주세요.",
        "야간 근무 중에도 컴플라이언스 함께 확인합니다.",
    ],
}


def fallback_greeting(now: datetime | None = None) -> str:
    """Bucket 선택 후 해당 풀에서 랜덤 1문장. KST 기준 (호출자가 KST datetime 전달 권장)."""
    n = now or (datetime.now(_KST) if _KST is not None else datetime.now())
    weekday = n.weekday()        # 0=Mon ... 6=Sun
    hour = n.hour

    is_friday = (weekday == 4)
    is_monday = (weekday == 0)
    is_weekend = (weekday >= 5)

    if is_weekend:
        bucket = "weekend"
    elif is_friday and hour >= 14:
        bucket = "friday_pm"
    elif is_monday and hour < 12:
        bucket = "monday_am"
    elif 5 <= hour < 12:
        bucket = "morning"
    elif 12 <= hour < 14:
        bucket = "noon"
    elif 14 <= hour < 18:
        bucket = "afternoon"
    elif 18 <= hour < 22:
        bucket = "evening"
    else:
        bucket = "night"
    greeting = random.choice(_GREETINGS[bucket])
    # 진단용 임시 stderr 로그 (PR-Fix-Timezone-Greeting — 다음 PR 에서 제거 예정).
    import sys as _tz_sys
    print(
        f"[hero_greeting:tz] hour_kst={hour} weekday={weekday} "
        f"bucket={bucket} greeting={greeting!r}",
        file=_tz_sys.stderr, flush=True,
    )
    return greeting


# ── 동적 인사 LLM prompt builder ────────────────────────────
GREETING_SYSTEM_PROMPT = (
    "당신은 신세계디에프 사내 윤리·컴플라이언스 챗봇 'DF COMPASS' 의 인사말 "
    "생성기입니다. 임직원이 페이지에 처음 들어왔을 때 보여줄 1~2문장 인사말을 "
    "생성합니다.\n\n"
    "규칙:\n"
    "- 합니다체 기본. 진중하되 따뜻하게.\n"
    "- 매번 동일한 인사 금지. 시간대·요일 분위기를 자연스럽게 반영.\n"
    "- 1~2문장, 70자 이내.\n"
    "- 느낌표 자제. 과도한 친근함·이모지 금지.\n"
    "- '안녕하세요'로 시작 가능하지만 매번 같은 형식 금지.\n"
    "- 챗봇 사용 안내 (예시 질문 등) 는 포함하지 마세요. 인사말만 출력.\n"
    "- 출력은 인사말 본문만. 따옴표·접두사·메타 코멘트 없이."
)


def build_greeting_user_prompt(now: datetime | None = None) -> str:
    n = now or (datetime.now(_KST) if _KST is not None else datetime.now())
    weekday_kr = ("월", "화", "수", "목", "금", "토", "일")[n.weekday()]
    hour = n.hour
    if 5 <= hour < 12:    period = "오전"
    elif 12 <= hour < 14: period = "점심"
    elif 14 <= hour < 18: period = "오후"
    elif 18 <= hour < 22: period = "저녁"
    else:                 period = "야간"
    return (
        f"현재 한국 시간: {weekday_kr}요일 {period} ({hour}시 무렵).\n"
        "이 분위기에 맞는 인사말 1~2문장을 생성해 주세요."
    )


# ── Daily Tip ────────────────────────────────────────────────
TIP_SYSTEM_PROMPT = (
    "당신은 신세계디에프 사내 윤리·컴플라이언스 챗봇의 '오늘의 사규 한 입' "
    "코너입니다. 임직원이 부담 없이 한 줄 사규 fun fact 로 흥미를 갖게 합니다.\n\n"
    "규칙:\n"
    "- 합니다체 기본. 가볍지만 정확하게.\n"
    "- 1문장, 80자 이내.\n"
    "- 사규 제목은 그대로 인용하되, 본문은 직역하지 말고 풀어서 친근하게.\n"
    "- 농담·과장·창작 금지. 사실 기반.\n"
    "- 출력은 한 줄 본문만. 따옴표·접두사·이모지 없이."
)


def build_tip_user_prompt(doc_title: str) -> str:
    return (
        f"오늘 소개할 사규: 「{doc_title}」.\n"
        "이 사규의 가장 핵심적이고 임직원 일상 업무에 도움 되는 한 줄을 "
        "흥미롭게 풀어 주세요."
    )


def pick_random_doc_title(supabase: Any) -> str | None:
    """nexus_documents 에서 active 문서 random 1개의 doc_title 반환.

    실패·결과 없음 시 None — 호출자는 Tip 섹션 자체를 숨기면 됨.
    SELECT 권한 anon 가정 (db/01 의 nexus_documents 는 현재 anon SELECT
    허용 상태). RLS 적용된 query_logs 와는 별개 테이블.
    """
    try:
        res = (
            supabase.table("nexus_documents")
            .select("title")
            .eq("status", "active")
            .limit(200)  # over-fetch 후 client-side random — RPC 추가 비용 회피
            .execute()
        )
        rows = res.data or []
        if not rows:
            return None
        titles = [str(r.get("title") or "").strip() for r in rows]
        titles = [t for t in titles if t]
        if not titles:
            return None
        return random.choice(titles)
    except Exception:
        return None


# ── 빠른 액션 카드 (PR-Fun1 작업 2) ─────────────────────────
# Empty state 에 노출. 클릭 시 session_state.chat_input 자동 채움.
QUICK_ACTIONS: tuple[tuple[str, str, str], ...] = (
    ("🛫", "출장비",     "출장비 정산 한도 알려줘"),
    ("💳", "법인카드",   "법인카드 사용 가능한 경우"),
    ("📝", "신고 절차",  "신고는 어디로 어떻게 하나요?"),
    ("🤝", "동호회",     "사내 동호회 활동 지원"),
)


# ── 카테고리별 색·아이콘 (PR-Fun1 작업 4) ───────────────────
# 답변 본문은 무수정. UI 단의 작은 chip 만 카테고리별 동적 변경.
# 가독성 우선 — 본문 색·배경은 손대지 않음.
CATEGORY_VISUAL: dict[str, tuple[str, str]] = {
    # category_name: (icon, hex_color)
    "재무":     ("💳", "#1d4ed8"),  # blue
    "인사":     ("👥", "#15803d"),  # green
    "CSR":      ("🤝", "#a16207"),  # yellow-brown (가독성)
    "안전":     ("⚠️", "#c2410c"),  # orange
    "공통":     ("📋", "#475569"),  # slate
    "정보보안": ("🔒", "#7e22ce"),  # purple
    "영업":     ("🛒", "#1e3a8a"),  # navy
    "공정거래": ("⚖️", "#0f766e"),  # teal
    "총무":     ("📦", "#475569"),  # slate
    "환경":     ("🌱", "#15803d"),  # green
}
_CATEGORY_DEFAULT = ("📋", "#475569")


# PR-Fix-Category-Citation-Based: 답변 본문 「📎 ((xxx) doc_title)」 인용
# prefix regex — '📎' + optional '**' bold + '((' + 카테고리 prefix.
# bold 유무 양쪽 매칭 (canonical: '📎 **((공통) ...)**', structured SOP:
# '📎 ((공통) ...)').
_CITATION_CATEGORY_RE = re.compile(r"📎\s*\*{0,2}\s*\(\(\s*([^)\s][^)]*?)\s*\)")


def _extract_categories_from_answer(answer_text: str) -> list[str]:
    """답변 본문 안 「📎 ((xxx) doc_title)」 인용 prefix 카테고리 추출 (등장 순).

    chunks.categories 빈도 기반 결정 (sloppy retrieval 영향) 보다 답변에
    실제 인용된 doc title prefix 가 LLM 의 의도와 정확히 일치 — 카테고리
    chip 정확도 향상.
    """
    if not answer_text:
        return []
    return [m.group(1).strip() for m in _CITATION_CATEGORY_RE.finditer(answer_text)]


def category_visual(
    contexts: list[dict],
    answer_text: str | None = None,
) -> tuple[str, str, str]:
    """카테고리 우선순위: 고신호 force-include doc prefix > answer_text 인용
    prefix > contexts.categories 빈도.

    1순위 (PR-Category-Force-Include-Priority): query 의도와 직접 매칭된
    고신호 force-include doc (force_source ∈ rpc/direct_table/title_direct/
    hardcoded) 의 prefix. LLM 의 답변 본문 인용 여부와 무관하게 정답 도메인
    보장. L2.5 auto_keyword 확장은 노이즈이므로 신호에서 제외 (force_source
    == "auto_keyword"). 진단: 법인카드 query 가 (재무) 법인카드 2 chunks
    진입했어도 auto_keyword 노이즈 다수 chunks 가 다수결을 오염시켜 '안전'
    오분류되던 회귀 fix.
    2순위: answer_text 「📎 ((xxx) doc_title)」 인용 prefix 빈도.
    3순위: contexts.categories 빈도. '공통' 1위면 2위 사용 (cross-cutting
    fallback 의미 → 실 도메인 우선).
    """
    from collections import Counter

    # 1. PR-Category-Force-Include-Priority: 고신호 force-include doc prefix.
    # PR-Fix-Category-Doc-Majority (#236): chunk → doc 단위 dedupe.
    # PR-Phase-4-Fix-L: doc count → max node_match_score per prefix.
    # 운영 검증(2026-05-24 Q2/Q3) 에서 Phase 3 광범위 nodes 매핑 부작용으로
    # (재무) 17 doc·(영업) AEO 3 doc 가 윤리/정보 query 와 노이즈 매칭 → doc
    # count majority 부정 회귀. node_match_score(user_nodes ∩ doc_nodes 크기)
    # 의 prefix 별 max 가 더 정확 — 광범위 매핑 doc 회피, 핵심 도메인 doc 우대.
    # 예: Q2 윤리 query → (인사) 직장 내 괴롭힘 max=3 > (재무) 자산 실사 max=2
    #     → 인사 카테고리 정상 결정.
    if contexts:
        force_prefix_max_match: dict[str, int] = {}
        force_prefix_doc_count: dict[str, set] = {}  # tiebreaker
        for c in contexts:
            if not c.get("force_included_by_intent"):
                continue
            if c.get("force_source") == "auto_keyword":
                continue
            t = str(c.get("doc_title") or "")
            doc_id = c.get("document_id") or t
            m = re.match(r"^\(\s*([^)\s][^)]*?)\s*\)", t)
            if not m:
                continue
            prefix = m.group(1).strip()
            # node_match_score — chunk 의 matched_incident_nodes 활용
            # (retriever 가 RPC 매칭 시 set 한 값). 부재 시 1로 fallback.
            matched = c.get("matched_incident_nodes") or []
            score = len(matched) if isinstance(matched, list) else 1
            # per-prefix max — 광범위 매핑 doc 의 낮은 score 회피, 정확 doc 우선
            if score > force_prefix_max_match.get(prefix, 0):
                force_prefix_max_match[prefix] = score
            force_prefix_doc_count.setdefault(prefix, set()).add(doc_id)
        if force_prefix_max_match:
            # 1순위 sort key: max_match 내림차순
            # 2순위 sort key (tiebreaker): doc count 내림차순 (기존 #236 정합)
            sorted_prefixes = sorted(
                force_prefix_max_match.items(),
                key=lambda kv: (-kv[1], -len(force_prefix_doc_count.get(kv[0], set())))
            )
            for cat, _score in sorted_prefixes:
                if cat != "공통" and cat in CATEGORY_VISUAL:
                    icon, color = CATEGORY_VISUAL.get(cat, _CATEGORY_DEFAULT)
                    return (icon, color, cat)

    # 2. PR-Fix-Category-Citation-Based: 답변 본문 인용 prefix 우선.
    if answer_text:
        cited = _extract_categories_from_answer(answer_text)
        if cited:
            counts = Counter(cited)
            primary = None
            for cat, _n in counts.most_common():
                if cat != "공통":
                    primary = cat
                    break
            if primary is None:
                # ★ PR-Category-Classifier-Fallback-Enhance:
                # 답변 인용 모두 "공통" 일 때 contexts.categories 의 도메인
                # 카테고리 활용. (공통) cross-cutting 사규 (사건사고 보고지침
                # 등) 가 자주 인용되어 실 도메인 사규 (예: (정보보안)
                # 개인정보보호) 보다 우선 분류되는 BUG fix.
                # 진단: "개인정보 보호" query → (공통) 사건사고 多 인용 +
                # (정보보안) 0건 → "공통" 분류 (잘못, 정답: "정보보안").
                if contexts:
                    ctx_categories: list[str] = []
                    for c in contexts:
                        cats = c.get("categories") or []
                        if isinstance(cats, list):
                            ctx_categories.extend(
                                str(x) for x in cats if x
                            )
                        # doc_title prefix 도 확인 (categories 부재 fallback)
                        t = str(c.get("doc_title") or "")
                        m = re.match(
                            r"^\(\s*([^)\s][^)]*?)\s*\)", t
                        )
                        if m:
                            ctx_categories.append(m.group(1).strip())
                    if ctx_categories:
                        ctx_counts = Counter(ctx_categories)
                        for cat, _n in ctx_counts.most_common():
                            if cat != "공통" and cat in CATEGORY_VISUAL:
                                primary = cat
                                break
            if primary is None:
                primary = "공통"
            icon, color = CATEGORY_VISUAL.get(primary, _CATEGORY_DEFAULT)
            return (icon, color, primary)

    # 3. Fallback — 기존 contexts.categories 빈도 (backwards-compatible).
    if not contexts:
        return (*_CATEGORY_DEFAULT, "")
    flat: list[str] = []
    for c in contexts:
        cats = c.get("categories") or []
        if isinstance(cats, list):
            flat.extend(str(x) for x in cats if x)
    if not flat:
        # categories 컬럼 부재 (db/09 미적용) — doc_title prefix 로 fallback
        for c in contexts:
            t = str(c.get("doc_title") or "")
            m = re.match(r"^\(\s*([^)\s][^)]*?)\s*\)", t)
            if m:
                flat.append(m.group(1).strip())
                break
    if not flat:
        return (*_CATEGORY_DEFAULT, "")
    counts = Counter(flat)
    # 공통 외 1위 우선
    primary = None
    for cat, _n in counts.most_common():
        if cat != "공통":
            primary = cat
            break
    if primary is None:
        primary = "공통"
    icon, color = CATEGORY_VISUAL.get(primary, _CATEGORY_DEFAULT)
    return (icon, color, primary)
