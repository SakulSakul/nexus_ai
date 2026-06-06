"""PR-A: 결정적 백스톱 SSOT.

게이트 ① (입력 공백) 과 게이트 ② (출력 공백, PR-B 에서 사용) 의 공유
상수·예외·헬퍼를 한 곳에 둔다. LLM 프롬프트 준수에 의존하지 않는
코드 레벨 방파제.
"""

# 게이트 ① — contexts==[] 시 결정적 거절 메시지 (prompts.py 톤 정합).
SAFE_NO_CONTEXT = (
    "관련 사규에서 확인되지 않습니다. 질문을 더 구체적으로 다시 시도해 주세요.\n\n"
    "[참조: 검색 결과 없음]"
)

# 게이트 ② (PR-B) — 빈 완료 fallback 소진 후 백스톱 메시지.
SAFE_EMPTY_COMPLETION = (
    "현재 답변을 생성하지 못했습니다. 잠시 후 다시 시도해 주세요.\n\n"
    "[참조: 검색 결과 없음]"
)


class EmptyCompletionError(RuntimeError):
    """LLM 이 예외 없이 빈 본문을 반환한 경우 (PR-B 에서 raise)."""


def is_empty_body(text: str, question: str) -> bool:
    """질문 에코·[참조] 스캐폴딩 제거 후 실질 본문이 임계 미만이면 True (결정적).

    PR-B 에서 사용. PR-A 에서는 정의만 두고 호출하지 않는다.
    """
    import re
    body = text or ""
    body = re.sub(r"^질문하신 내용: '.*?'\s*", "", body, flags=re.S)
    body = re.sub(r"\[참조:.*?\]", "", body, flags=re.S)
    return len(body.strip()) < 10
