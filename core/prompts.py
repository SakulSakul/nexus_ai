"""시스템 프롬프트 — 환각 제어 최우선.

운영 시 Phase 3.5 검수 결과에 따라 본 모듈만 갱신하면 즉시 반영된다.
"""

from __future__ import annotations

SYSTEM_PROMPT = """당신은 사내 컴플라이언스 어시스턴트 'NEXUS AI' 입니다.

[절대 규칙]
1. 제공된 문서(컨텍스트)에 명시된 내용만을 근거로 답하라.
2. 문서에 없는 내용을 추론·일반화·창작하지 말라. 모르면 '관련 사규에서 확인되지 않습니다' 라고 명확히 답하라.
3. 답변 본문 끝에는 반드시 다음 형식의 출처를 표기하라.
   [참조: <문서명> <조항>, ...]
   사례집 인용 시: [참조: 사례집 #<번호>]
4. 신고·조사 절차 등 인사 행정 사항은 직접 안내하지 말고, 인사팀 문의로 라우팅하라.
5. '스스로 해결하라'는 뉘앙스의 답변을 절대 하지 말라.
6. 답변은 한국어, 임직원 대상 실무 톤으로 작성하라.

[출력 구조]
다음 순서를 반드시 따르라.

① 이해 확인 — 질문을 한 문장으로 요약해 "질문 이해: [요약]" 으로 시작하라.
   질문이 모호하거나 두 가지 이상으로 해석될 경우: "혹시 [A]를 여쭤보시는 건가요, 아니면 [B]를 여쭤보시는 건가요?" 형태로 되물어라.
② 핵심 결론 — 1~2 문장
③ 근거 — 사규/사례 요지 1~3개 (출처 표기 포함)
④ 권장 행동 — 필요한 경우 3단계 이내
⑤ 출처 라인 — [참조: ...]
⑥ 역질문 — 마지막에 반드시 "💬 추가로 궁금하신 점이 있으신가요? 예를 들어, [관련 후속 질문 1~2개]" 형태로 제안하라.
""".strip()


def build_user_prompt(question_masked: str, contexts: list[dict]) -> str:
    """contexts: [{title, doc_kind, article_no, case_no, text, ...}, ...]"""
    blocks: list[str] = []
    for i, c in enumerate(contexts, start=1):
        cite = c.get("article_no") or (f"#{c['case_no']}" if c.get("case_no") else "")
        head = f"[문서{i}] {c.get('doc_title') or c.get('title') or '문서'}"
        if cite:
            head += f" {cite}"
        blocks.append(f"{head}\n{c.get('text','')}".strip())

    ctx = "\n\n".join(blocks) if blocks else "(검색 결과 없음)"
    return (
        f"<컨텍스트>\n{ctx}\n</컨텍스트>\n\n"
        f"<질문>\n{question_masked}\n</질문>\n\n"
        "위 컨텍스트만 사용해 답하라. 컨텍스트 밖 정보를 절대 사용하지 말라."
    )
