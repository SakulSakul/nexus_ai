"""StructuredAnswer → markdown 렌더링."""

from __future__ import annotations

from core.synthesis.structured_schema import StructuredAnswer


def render_structured_to_markdown(answer: StructuredAnswer) -> str:
    lines: list = []
    if not answer.sections:
        lines.append("죄송합니다. 사규에서 관련 답변을 찾을 수 없습니다.")
        if answer.unsupported_topics:
            lines.append("")
            lines.append("**검색 안 됨:**")
            for t in answer.unsupported_topics:
                lines.append(f"- {t}")
        return "\n".join(lines)

    for section in answer.sections:
        if not section.claims:
            continue
        lines.append(f"## {section.title}")
        lines.append("")
        for claim in section.claims:
            lines.append(f"- {claim.text}")
            cite_parts = [p for p in (claim.doc_title, claim.clause) if p]
            if cite_parts:
                lines.append(f"  📎 *{' '.join(cite_parts)}*")
        lines.append("")

    if answer.unsupported_topics:
        lines.append("---")
        lines.append("**ℹ️ 사규에서 직접 확인 안 된 항목:**")
        for t in answer.unsupported_topics:
            lines.append(f"- {t}")
        lines.append("")
    if answer.data_gaps:
        lines.append("---")
        lines.append("**⚠️ 필수 문서 검색 누락:**")
        for g in answer.data_gaps:
            lines.append(f"- {g}")
    return "\n".join(lines).strip()
