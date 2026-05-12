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
