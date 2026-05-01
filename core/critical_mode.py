"""심각 사안 응답 모드 (Critical Response Mode).

- DB 의 critical_keywords 사전을 기준으로 트리거 감지.
- 4단 응답 구조를 후처리에서 강제 삽입한다 (2·4번 항목 누락 시 필수 보강).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .config import hr_routing_line


@dataclass
class CriticalDetection:
    triggered: bool
    kind: str | None        # 'safety' | 'harassment' | None
    matched: list[str]


def load_keywords(supabase: Any) -> dict[str, list[str]]:
    """{'safety': [...], 'harassment': [...]} 반환. 실패 시 빈 dict."""
    try:
        rows = (
            supabase.table("critical_keywords")
                    .select("kind,keyword,is_active")
                    .eq("is_active", True)
                    .execute()
                    .data or []
        )
    except Exception:
        return {"safety": [], "harassment": []}
    out: dict[str, list[str]] = {"safety": [], "harassment": []}
    for r in rows:
        out.setdefault(r["kind"], []).append(r["keyword"])
    return out


# 키워드가 매치돼도 "사규/규정 안내 질문"으로 보이는 컨텍스트면 critical
# 트리거를 보류한다. 예: "사망사고 신고 절차가 어떻게 되나요?" 는 일반
# 정보 요청이지 응급 사안이 아님. 이걸 critical 로 잡으면 4단 답변 구조
# 강제로 UX 가 어색해지고 통계도 왜곡됨.
_STOP_PHRASES = (
    "절차가 어떻게", "어떻게 되나요", "어떻게 진행", "방법이 어떻게",
    "기준이 어떻게", "처분이 어떻게",
    "관련 사규", "관련 규정", "사규에서", "규정에서",
    "예방 교육", "예방교육", "이론적", "정의가 무엇",
)

# 실제 사건/제보 신호 — 이 표현이 같이 나오면 stop-context 무시하고 critical 트리거.
# 예: "괴롭힘 사건이 발생했고 사규에서 어떻게 처리되나요?" — '사규에서' (stop) 가
# 있어도 '발생했' 가 있으면 진짜 신고로 판단.
# 시간 부사(어제/오늘/지금/방금) 는 정보 요청 컨텍스트에도 흔히 등장해서 false-
# positive 발생 → 강한 사건 동사만 남김.
_INCIDENT_SIGNALS = (
    "발생했", "당했", "당하고", "겪었", "겪고", "목격했", "목격하",
    "신고하고 싶", "제보하고 싶",
    "도와주세요", "도와줘", "어떡해", "구해주",
)


def _is_benign_query(text: str) -> bool:
    """질문 형식이 사규/규정 정보 요청이고, 실제 사건 신호가 없으면 True.
    실제 사건 신호(_INCIDENT_SIGNALS)가 등장하면 stop 표현이 있어도 false."""
    has_stop = any(p in text for p in _STOP_PHRASES)
    if not has_stop:
        return False
    has_incident = any(p in text for p in _INCIDENT_SIGNALS)
    # stop 만 있으면 정보 요청 / stop + incident 면 진짜 신고
    return not has_incident


def detect(text: str, keywords: dict[str, list[str]]) -> CriticalDetection:
    if not text:
        return CriticalDetection(False, None, [])
    benign = _is_benign_query(text)
    # 우선순위: harassment > safety (인사 라우팅 안내 필요)
    for kind in ("harassment", "safety"):
        hits = [k for k in keywords.get(kind, []) if k and k in text]
        if hits:
            if benign:
                # 정보 요청 컨텍스트(+ 사건 신호 없음) → 일반 응답.
                return CriticalDetection(False, None, hits)
            return CriticalDetection(True, kind, hits)
    return CriticalDetection(False, None, [])


def _scope_line(kind: str) -> str:
    if kind == "harassment":
        # 괴롭힘·성희롱은 신고·조사 case → CSR / 핫라인 라우팅
        return ("본 답변은 사규 해석 관점입니다. "
                "신고·조사 사항은 CSR팀 또는 신세계면세점 핫라인으로 접수해 주시기 바랍니다.")
    return ("본 답변은 사규/안전관리 기준 관점이며, "
            "실제 응급상황 시 아래 핫라인을 즉시 이용하시기 바랍니다.")


def _hotline_box(kind: str, hotlines: dict[str, str]) -> str:
    lines: list[str] = ["📞 **핫라인 안내**"]
    lines.append(f"- 사내 익명 제보채널: {hotlines.get('internal_report_url','')}")
    lines.append(f"- 외부 상담채널: {hotlines.get('external_hotline','')}")
    if kind == "harassment":
        # 괴롭힘·성희롱은 신고·조사 → CSR팀 라우팅 (인사팀 X)
        lines.append("- 신고·조사 접수: CSR팀 또는 신세계면세점 핫라인")
    return "\n".join(lines)


def enforce_structure(
    *,
    base_answer: str,
    kind: str,
    action_items: list[str] | None,
    hotlines: dict[str, str],
) -> str:
    """4단 구조를 강제 보장하고, 누락 항목은 후처리 삽입."""
    parts: list[str] = []

    # 1) 사규 기반 답변
    parts.append("### 1. 사규 기반 답변")
    parts.append(base_answer.strip() or "관련 사규에서 확인되지 않습니다.")

    # 2) 범위 안내 (강제)
    parts.append("### 2. 답변 범위 안내")
    parts.append(_scope_line(kind))

    # 3) Action Item — 모델이 만든 항목이 있으면 우선 사용, 없으면 안전 기본값
    parts.append("### 3. 즉시 실행 가능한 행동 가이드")
    items = [a for a in (action_items or []) if a and a.strip()]
    if not items:
        if kind == "safety":
            items = [
                "현장 안전 확보 및 2차 피해 방지 (작업 중지/대피 우선)",
                "관리감독자·안전보건 담당자에게 즉시 보고",
                "필요한 경우 119 신고 및 사내 핫라인 이용",
            ]
        else:
            items = [
                "발생 일시·장소·관련자·구체적 행위를 시간순으로 메모",
                "가능한 증거(메시지·이메일·녹취 등)를 안전한 위치에 보관",
                "아래 핫라인 또는 인사팀에 익명/실명으로 상담 요청",
            ]
    for i, a in enumerate(items[:3], start=1):
        parts.append(f"{i}. {a}")

    # 4) 핫라인 안내 박스 (강제)
    parts.append("---")
    parts.append(_hotline_box(kind, hotlines))

    return "\n\n".join(parts)
