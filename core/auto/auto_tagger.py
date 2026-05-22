"""Auto-tagger — Claude Opus 가 모든 active doc 의 incident_nodes + doc_kind 추론."""

from __future__ import annotations

import json
import re
import sys

from .cache import _get_sb
from .auto_classifier import AVAILABLE_INCIDENT_NODES


TAGGER_SYSTEM_PROMPT = """\
사규 doc 태깅 전문가. doc 내용 보고 incident_nodes 와 doc_kind 결정.

doc_kind 후보:
- "rule": 절차/지침
- "penalty": 처분/징계 기준
- "case": 사건 사례
- "policy": 정책/방침

사용 가능 incident_nodes: {nodes}

strict JSON:
{{"incident_nodes": ["..."], "doc_kind": "rule|penalty|case|policy", "rationale": "한 줄"}}
"""


def tag_single_doc(doc_id: str, title: str, text_sample: str) -> dict:
    try:
        import anthropic
        from core.config import settings
    except Exception as e:
        return {
            "incident_nodes": [], "doc_kind": "rule",
            "rationale": f"SDK import error: {e}",
        }
    s = settings()
    if not s.anthropic_api_key:
        return {
            "incident_nodes": [], "doc_kind": "rule",
            "rationale": "ANTHROPIC_API_KEY 미설정",
        }
    client = anthropic.Anthropic(api_key=s.anthropic_api_key)
    system = TAGGER_SYSTEM_PROMPT.format(nodes=", ".join(AVAILABLE_INCIDENT_NODES))
    user_msg = (
        f"title: {title}\n\n"
        f"content (앞 2000자):\n{(text_sample or '')[:2000]}\n\n"
        f"strict JSON."
    )
    try:
        response = client.messages.create(
            model="claude-opus-4-7",
            max_tokens=800,
            system=system,
            messages=[{"role": "user", "content": user_msg}],
        )
        raw = response.content[0].text if response.content else "{}"
        if "```" in raw:
            m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
            if m:
                raw = m.group(1)
        result = json.loads(raw)
        result["incident_nodes"] = [
            n for n in result.get("incident_nodes", []) or []
            if n in AVAILABLE_INCIDENT_NODES
        ]
        result.setdefault("doc_kind", "rule")
        result.setdefault("rationale", "")
        return result
    except Exception as e:
        return {
            "incident_nodes": [], "doc_kind": "rule",
            "rationale": f"error: {type(e).__name__}: {e}",
        }


def auto_tag_all_docs(*, dry_run: bool = True, progress_callback=None) -> dict:
    """active doc 전체 재태깅. dry_run=True 면 제안만, False 면 실제 UPDATE."""
    sb = _get_sb()
    if not sb:
        return {"error": "supabase unavailable", "dry_run": dry_run, "total": 0, "results": []}
    try:
        docs_resp = (
            sb.table("nexus_documents")
            .select("id,title,doc_kind,meta")
            .eq("status", "active")
            .is_("superseded_by", "null")
            .execute()
        )
    except Exception as e:
        return {"error": f"docs fetch failed: {e}", "dry_run": dry_run, "total": 0, "results": []}

    docs = docs_resp.data or []
    results: list = []
    total = len(docs)

    for i, doc in enumerate(docs):
        doc_id = doc.get("id")
        title = doc.get("title") or ""
        # nexus_chunks 의 컬럼은 document_id (doc_id 아님).
        try:
            chunks_resp = (
                sb.table("nexus_chunks")
                .select("text")
                .eq("document_id", doc_id)
                .limit(3)
                .execute()
            )
            sample = "\n".join(
                (c.get("text") or "") for c in (chunks_resp.data or [])
            )
        except Exception:
            sample = ""

        tagged = tag_single_doc(doc_id, title, sample)
        existing = (doc.get("meta") or {}).get("incident_nodes") or []
        merged = sorted(set(existing + (tagged.get("incident_nodes") or [])))

        row = {
            "doc_id": doc_id,
            "title": title,
            "existing_nodes": existing,
            "claude_proposed": tagged.get("incident_nodes") or [],
            "merged": merged,
            "doc_kind_current": doc.get("doc_kind"),
            "doc_kind_proposed": tagged.get("doc_kind"),
            "rationale": tagged.get("rationale", ""),
        }

        if not dry_run:
            try:
                new_meta = {**(doc.get("meta") or {}), "incident_nodes": merged}
                update_payload: dict = {"meta": new_meta}
                if (
                    tagged.get("doc_kind")
                    and doc.get("doc_kind") != tagged.get("doc_kind")
                ):
                    update_payload["doc_kind"] = tagged["doc_kind"]
                sb.table("nexus_documents").update(update_payload).eq("id", doc_id).execute()
                row["applied"] = True
            except Exception as e:
                row["applied"] = False
                row["apply_error"] = str(e)

        results.append(row)
        if progress_callback:
            try:
                progress_callback(i + 1, total, title)
            except Exception:
                pass

    return {"dry_run": dry_run, "total": len(results), "results": results}


# ============================================================
# PR-Stage-A-1: Full Meta Extraction
# ============================================================

FULL_META_SYSTEM_PROMPT = """\
사규 doc 메타데이터 추출 전문가. doc title + content 보고 strict JSON 으로 반환.

사용 가능 incident_nodes: {nodes}

추출 5종:
1. incident_nodes: 사용 가능 노드 중 선택 (정확하지 않으면 빈 배열)
2. doc_kind: "rule" | "penalty" | "case" | "policy"
3. auto_keywords: doc title + content 의 핵심 명사 5~10개 배열. 띄어쓰기 포함 가능. 사용자가 자연어로 물어볼 때 매칭될 단어 위주.

   ★ 다음 5개 카테고리를 우선적으로 포함 (이전 누락 패턴 보강):
   - 절차·제도 이름 (예: "클린신고", "자진 신고", "녹색 구매", "지인 거래", "이중취업")
   - 시스템·메뉴·채널 이름 (예: "SHRS", "SRMS", "윤리경영", "윤리실천등록", "클린신고신청서", "대외강의출강신청서", "신세계면세점 핫라인")
   - 부서명 (예: "CSR팀", "인사교육팀", "리스크관리부서", "총무팀", "경영관리팀")
   - 시간 기한 (예: "3일 이내", "24시간 이내", "7일 이내", "10일 이내")
   - 도메인 용어 (예: "이해관계자", "향응 수수", "클린뱅크", "녹색제품", "사건사고")
4. auto_summary: doc 의 한 줄 요약 (50자 이내, 명사형 평어체)
5. auto_query_examples: 이 사규로 답변 가능한 예상 사용자 query 정확히 5개

strict JSON 만:
{{"incident_nodes": ["..."], "doc_kind": "rule|penalty|case|policy", "auto_keywords": ["..."], "auto_summary": "...", "auto_query_examples": ["...", "...", "...", "...", "..."], "rationale": "한 줄"}}
"""


def extract_doc_full_meta(doc_id: str, title: str, text_sample: str) -> dict:
    """Stage A-1: doc 1개에서 5종 메타 일괄 추출 (1회 LLM 호출).

    Returns dict:
      - incident_nodes: list[str]
      - doc_kind: str (rule/penalty/case/policy)
      - auto_keywords: list[str]
      - auto_summary: str
      - auto_query_examples: list[str] (정확히 5개, 실패 시 빈 list)
      - rationale: str

    실패 시 안전 fallback (빈 list, doc_kind=rule).
    """
    try:
        import anthropic
        from core.config import settings
    except Exception as e:
        return {
            "incident_nodes": [], "doc_kind": "rule",
            "auto_keywords": [], "auto_summary": "",
            "auto_query_examples": [],
            "rationale": f"SDK import error: {e}",
        }
    s = settings()
    if not s.anthropic_api_key:
        return {
            "incident_nodes": [], "doc_kind": "rule",
            "auto_keywords": [], "auto_summary": "",
            "auto_query_examples": [],
            "rationale": "ANTHROPIC_API_KEY 미설정",
        }
    client = anthropic.Anthropic(api_key=s.anthropic_api_key)
    system = FULL_META_SYSTEM_PROMPT.format(
        nodes=", ".join(AVAILABLE_INCIDENT_NODES)
    )
    user_msg = (
        f"title: {title}\n\n"
        f"content (앞 3000자):\n{(text_sample or '')[:3000]}\n\n"
        f"strict JSON."
    )
    try:
        response = client.messages.create(
            model="claude-opus-4-7",
            max_tokens=1500,
            system=system,
            messages=[{"role": "user", "content": user_msg}],
        )
        raw = response.content[0].text if response.content else "{}"
        if "```" in raw:
            m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
            if m:
                raw = m.group(1)
        result = json.loads(raw)
        # 안전 정제
        result["incident_nodes"] = [
            n for n in result.get("incident_nodes", []) or []
            if n in AVAILABLE_INCIDENT_NODES
        ]
        result.setdefault("doc_kind", "rule")
        result.setdefault("auto_keywords", [])
        result.setdefault("auto_summary", "")
        # auto_keywords: list[str] 보장, 빈 string 제거
        result["auto_keywords"] = [
            k.strip() for k in (result.get("auto_keywords") or [])
            if isinstance(k, str) and k.strip()
        ]
        # auto_query_examples: 정확히 5개 우선 (부족하면 그대로, 초과면 5개로 cut)
        examples = [
            q.strip() for q in (result.get("auto_query_examples") or [])
            if isinstance(q, str) and q.strip()
        ]
        result["auto_query_examples"] = examples[:5]
        result.setdefault("rationale", "")
        return result
    except Exception as e:
        return {
            "incident_nodes": [], "doc_kind": "rule",
            "auto_keywords": [], "auto_summary": "",
            "auto_query_examples": [],
            "rationale": f"error: {type(e).__name__}: {e}",
        }


# ============================================================
# PR-Stage-A-1-Chunk: chunk 단위 keyword 추출
# ============================================================

CHUNK_KEYWORDS_SYSTEM_PROMPT = """\
사규 chunk 메타데이터 추출 전문가. chunk 본문의 specific 내용에서 핵심 keyword 5~10개 JSON 으로 반환.

부모 사규: {doc_title}
사규 도메인: {doc_categories}

조건:
- chunk 본문의 specific 단어 위주 (parent doc 의 일반 chapter 제목과 차별)
- 5 카테고리 우선 포함:
  - 절차·제도 이름 (예: "지인거래 신고", "신세계페이", "클린신고", "녹색구매")
  - 시스템·메뉴·채널 이름 (예: "SHRS", "윤리경영", "윤리실천등록", "클린신고신청서", "SRMS", "신세계면세점 핫라인")
  - 부서명 (예: "CSR팀", "인사교육팀", "리스크관리부서", "총무팀")
  - 시간 기한 (예: "3일 이내", "24시간 이내", "7일 이내")
  - 도메인 용어 (예: "협력회사 식사", "각자 부담", "친인척", "이중취업", "향응 수수")

- 다음 stop-word 제외 (너무 일반적):
  - 이해관계자, CSR, 관리, 경영, 환경, 안전관리, 리스크관리

- 2글자 이상의 명사 위주
- 띄어쓰기 포함 가능

strict JSON 만, 다른 설명 X:
{{"auto_keywords": ["...", "...", ...]}}
"""


def extract_chunk_keywords(
    chunk_text: str,
    doc_title: str,
    doc_categories: list[str] | None = None,
) -> list[str]:
    """Stage A-1-Chunk: chunk 1개에서 keyword 5~10개 추출.

    부모 doc context (title + categories) 활용해 더 정확한 specific keyword.
    Returns: list of keywords (실패 시 빈 list).
    """
    try:
        import anthropic
        from core.config import settings
    except Exception as e:
        print(f"[chunk_tagger] SDK import error: {e}", file=sys.stderr, flush=True)
        return []
    s = settings()
    if not s.anthropic_api_key:
        return []

    client = anthropic.Anthropic(api_key=s.anthropic_api_key)

    categories_str = ", ".join(doc_categories or []) if doc_categories else "(없음)"
    system = CHUNK_KEYWORDS_SYSTEM_PROMPT.format(
        doc_title=doc_title or "(미상)",
        doc_categories=categories_str,
    )
    user_msg = f"chunk 본문:\n{(chunk_text or '')[:3000]}\n\nstrict JSON."

    try:
        response = client.messages.create(
            model="claude-opus-4-7",
            max_tokens=600,
            system=system,
            messages=[{"role": "user", "content": user_msg}],
        )
        raw = response.content[0].text if response.content else "{}"
        if "```" in raw:
            m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
            if m:
                raw = m.group(1)
        result = json.loads(raw)
        keywords = result.get("auto_keywords") or []
        # 안전 정제: str + 2글자 이상 + strip
        clean = [
            k.strip() for k in keywords
            if isinstance(k, str) and len(k.strip()) >= 2
        ]
        return clean[:10]  # 최대 10개
    except Exception as e:
        print(f"[chunk_tagger] error: {type(e).__name__}: {e}", file=sys.stderr, flush=True)
        return []
