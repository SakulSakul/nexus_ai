"""DF COMPASS 답변/판정 카드 HTML 빌더 — app.py 에서 분리(동작 무변경).

입력=dict, 출력=HTML 문자열인 순수 함수군. _ENABLE_VERDICT_* 플래그 포함.
"""

from core.config import get_secret


def _slim_structured(sa) -> dict | None:
    """StructuredAnswer → 카드 렌더용 슬림 dict (raw_json 제외 → session_state 경량). 없으면 None."""
    if sa is None:
        return None
    try:
        d = sa.to_dict() if hasattr(sa, "to_dict") else dict(sa)
    except Exception:
        return None
    secs = []
    for s in (d.get("sections") or []):
        claims = []
        for c in (s.get("claims") or []):
            claims.append({
                "text": c.get("text", ""),
                "verbatim_quote": c.get("verbatim_quote", ""),
                "doc_title": c.get("doc_title", ""),
                "clause": c.get("clause", ""),
            })
        secs.append({"title": s.get("title", ""), "claims": claims})
    if not secs:
        return None
    return {
        "sections": secs,
        "unsupported_topics": d.get("unsupported_topics") or [],
        "data_gaps": d.get("data_gaps") or [],
    }


def _build_structured_card_html(d) -> str:
    """슬림 structured dict → 목업형 답변 카드 HTML. 없으면 빈 문자열(→ 호출측 markdown fallback).

    데이터에 verdict(금지/허용) 필드가 없으므로 거짓 pill 미생성 — 중립 헤더.
    CSS 는 자체 <style> 동봉(정적 _CSS 무수정).
    """
    if not d or not isinstance(d, dict):
        return ""
    import html as _h
    secs = d.get("sections") or []
    if not secs:
        return ""
    css = (
        "<style>"
        ".nx-vc{font-family:var(--font);}"
        ".nx-vc-head{display:flex;align-items:center;gap:9px;padding-bottom:12px;margin-bottom:4px;border-bottom:1px solid var(--c-border);}"
        ".nx-vc-head .nx-compass{width:22px;height:22px;flex:0 0 22px;}"
        ".nx-vc-head b{font-size:14px;font-weight:700;color:var(--c-primary);}"
        ".nx-vc-sec{margin-top:16px;}"
        ".nx-vc-sectitle{font-size:10.5px;font-weight:700;letter-spacing:.12em;text-transform:uppercase;color:#A8654E;margin-bottom:8px;}"
        ".nx-vc-claim{font-size:14px;line-height:1.7;color:var(--c-text);margin:0 0 8px;}"
        ".nx-vc-quote{border-left:3px solid var(--c-accent);padding:2px 0 2px 13px;margin:4px 0 10px;}"
        ".nx-vc-quote p{font-family:'SDDOES Myeongjo','Nanum Myeongjo',serif;font-size:13.5px;line-height:1.7;color:#2C2B28;margin:0;}"
        ".nx-vc-cite{display:inline-block;font-size:11px;color:#5F5E5A;background:var(--c-surface);border-radius:6px;padding:3px 9px;margin-top:6px;}"
        ".nx-vc-note{font-size:12.5px;color:var(--c-caption);border-top:1px solid var(--c-border);margin-top:14px;padding-top:10px;}"
        "</style>"
    )
    parts = [css, '<div class="nx-vc">',
             '<div class="nx-vc-head"><span class="nx-compass"></span><b>DF COMPASS 답변</b></div>']
    for s in secs:
        claims = s.get("claims") or []
        if not claims:
            continue
        title = _h.escape(str(s.get("title") or ""))
        parts.append('<div class="nx-vc-sec">')
        if title:
            parts.append('<p class="nx-vc-sectitle">' + title + '</p>')
        for c in claims:
            txt = _h.escape(str(c.get("text") or ""))
            if txt:
                parts.append('<p class="nx-vc-claim">' + txt + '</p>')
            q = _h.escape(str(c.get("verbatim_quote") or ""))
            if q:
                parts.append('<div class="nx-vc-quote"><p>' + q + '</p></div>')
                cite_raw = " ".join(p for p in (str(c.get("doc_title") or ""), str(c.get("clause") or "")) if p)
                if cite_raw:
                    parts.append('<span class="nx-vc-cite">📎 ' + _h.escape(cite_raw) + '</span>')
        parts.append('</div>')
    for t in (d.get("unsupported_topics") or []):
        parts.append('<p class="nx-vc-note">ℹ️ 사규에서 직접 확인 안 됨 — ' + _h.escape(str(t)) + '</p>')
    for g in (d.get("data_gaps") or []):
        parts.append('<p class="nx-vc-note">⚠️ 필수 문서 누락 — ' + _h.escape(str(g)) + '</p>')
    parts.append('</div>')
    return "".join(parts)


_ENABLE_VERDICT_SHADOW = get_secret("ENABLE_VERDICT_SHADOW", "false").lower() == "true"
_ENABLE_VERDICT_CARD = get_secret("ENABLE_VERDICT_CARD", "false").lower() == "true"


def _build_verdict_card_html(d) -> str:
    """Verdict dict → 목업형 판정 카드(stance pill·grounded 세리프 인용·출처·신뢰도).
    데이터/stance 없으면 기존 브랜드 헤더로 fallback. 색상은 안전쪽(금지·신고대상=레드).
    """
    if not d or not isinstance(d, dict):
        return _answer_card_header_html()
    import html as _h
    stance = str(d.get("stance") or "").strip()
    if not stance:
        return _answer_card_header_html()
    tone = {
        "금지": ("#C8102E", "#FCEEF0"),
        "신고대상": ("#C8102E", "#FCEEF0"),
        "조건부": ("#B7791F", "#FBF3E2"),
        "허용": ("#2F7A4D", "#EAF5EE"),
        "확인필요": ("#6B6A66", "#F0EFEC"),
    }.get(stance, ("#6B6A66", "#F0EFEC"))
    color, bg = tone
    label = _h.escape(str(d.get("label") or stance)[:40])
    badge = _h.escape(str(d.get("badge") or "")[:24])
    quote = _h.escape(str(d.get("quote") or ""))
    cite = _h.escape(" ".join(p for p in (str(d.get("doc_title") or ""), str(d.get("clause") or "")) if p))
    conf = str(d.get("confidence") or "")
    conf_label = {"high": "높은 신뢰도", "medium": "보통 신뢰도", "low": "낮은 신뢰도"}.get(conf, "")
    css = (
        "<style>"
        ".nx-vd{margin:2px 0 14px;}"
        ".nx-vd-pill{display:inline-flex;align-items:center;gap:8px;padding:7px 13px;border-radius:11px;border:1px solid " + color + ";background:" + bg + ";}"
        ".nx-vd-pill .ico{width:8px;height:8px;border-radius:50%;background:" + color + ";flex:0 0 8px;}"
        ".nx-vd-pill b{font-size:13.5px;font-weight:700;color:" + color + ";}"
        ".nx-vd-badge{font-size:11px;font-weight:700;color:" + color + ";background:rgba(255,255,255,0.62);border-radius:6px;padding:2px 8px;}"
        ".nx-vd-quote{border-left:3px solid " + color + ";padding:5px 0 5px 16px;margin:14px 0 10px;}"
        ".nx-vd-quote p{font-family:'SDDOES Myeongjo','Nanum Myeongjo',serif;font-size:15.5px;font-weight:600;line-height:1.85;letter-spacing:-0.1px;color:#1F1D1A;margin:0;}"
        ".nx-vd-cite{display:inline-block;font-size:11px;color:#5F5E5A;background:var(--c-surface,#F4F1EB);border-radius:6px;padding:3px 9px;margin-top:7px;}"
        ".nx-vd-foot{display:flex;align-items:center;gap:7px;margin-top:11px;font-size:11.5px;color:var(--c-caption,#7A766E);}"
        ".nx-vd-foot .dot{width:7px;height:7px;border-radius:50%;background:" + color + ";flex:0 0 7px;}"
        '[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarCustom"]){border-left:3px solid var(--c-accent,#C8102E) !important;}'
        "</style>"
    )
    parts = [css, '<div class="nx-vd">',
             '<span class="nx-vd-pill"><span class="ico"></span><b>' + label + '</b>'
             + ('<span class="nx-vd-badge">' + badge + '</span>' if badge else '') + '</span>']
    if quote:
        parts.append('<div class="nx-vd-quote"><p>' + quote + '</p></div>')
        if cite:
            parts.append('<span class="nx-vd-cite">📕 ' + cite + '</span>')
    if conf_label:
        parts.append('<div class="nx-vd-foot"><span class="dot"></span>' + conf_label + '</div>')
    parts.append('</div>')
    return "".join(parts)


def _answer_card_header_html() -> str:
    """답변 카드 상단 브랜드 헤더(레드 점 + 라벨 + 헤어라인) + 답변 카드 좌측 레드 액센트.
    답변 본문과 독립적으로 prepend 되는 HTML — 내용/색상/리스트 구조에 영향 없음.
    """
    return (
        "<style>"
        ".nx-ach{display:flex;align-items:center;gap:8px;margin:2px 0 14px;}"
        ".nx-ach .dot{width:7px;height:7px;border-radius:50%;background:var(--c-accent,#C8102E);flex:0 0 7px;}"
        ".nx-ach b{font-size:11.5px;font-weight:700;letter-spacing:.07em;color:var(--c-primary,#1F1E1D);white-space:nowrap;}"
        ".nx-ach .rule{flex:1;height:1px;background:var(--c-border,#E7E3DC);}"
        '[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarCustom"]){border-left:3px solid var(--c-accent,#C8102E) !important;}'
        "</style>"
        '<div class="nx-ach"><span class="dot"></span><b>DF COMPASS 답변</b><span class="rule"></span></div>'
    )


def _build_oos_card_html(d) -> str:
    """OOS 라우팅 안내 카드. core.oos_router.oos_routing_rows() dict 소비.
    헤더리스(_answer_card_header_html 와 중복 방지). HR 행은 url 있으면
    '인사 챗봇으로 이동' 버튼, 없으면 team(인사교육팀) pill. data 없으면 빈 문자열."""
    if not d or not isinstance(d, dict):
        return ""
    import html as _h
    rows = d.get("rows") or []
    if not rows:
        return ""
    note = str(d.get("critical_note") or "")
    css = (
        "<style>"
        ".nx-oos{font-family:var(--font);margin:2px 0 12px;}"
        ".nx-oos-intro{font-size:13.5px;line-height:1.6;color:var(--c-caption,#7A766E);margin:0 0 10px;}"
        ".nx-oos-row{display:flex;align-items:center;gap:12px;padding:10px 0;border-top:1px solid var(--c-border,#E7E3DC);}"
        ".nx-oos-row:last-of-type{border-bottom:1px solid var(--c-border,#E7E3DC);}"
        ".nx-oos-main{flex:1;min-width:0;}"
        ".nx-oos-label{font-size:14px;font-weight:700;color:var(--c-primary,#1F1E1D);}"
        ".nx-oos-ex{font-size:12px;color:var(--c-caption,#7A766E);margin-top:2px;}"
        ".nx-oos-team{font-size:12.5px;font-weight:700;color:#5F5E5A;background:var(--c-surface,#F4F1EB);border-radius:6px;padding:4px 10px;white-space:nowrap;}"
        ".nx-oos-btn{display:inline-block;font-size:12.5px;font-weight:700;color:#FFFFFF;background:var(--c-accent,#C8102E);border-radius:7px;padding:6px 12px;text-decoration:none;white-space:nowrap;}"
        ".nx-oos-crit{display:flex;gap:8px;margin-top:14px;padding:10px 12px;background:#FCEEF0;border:1px solid var(--c-accent,#C8102E);border-radius:8px;font-size:12px;line-height:1.55;color:#8A1020;}"
        "</style>"
    )
    parts = [css, '<div class="nx-oos">',
             '<p class="nx-oos-intro">요청하신 내용은 사규 챗봇의 범위를 벗어납니다. 아래 담당 창구로 안내드립니다.</p>']
    for r in rows:
        label = _h.escape(str(r.get("label") or ""))
        ex = _h.escape(str(r.get("examples") or ""))
        url = str(r.get("url") or "").strip()
        team = _h.escape(str(r.get("team") or ""))
        parts.append('<div class="nx-oos-row"><div class="nx-oos-main">'
                     '<div class="nx-oos-label">' + label + '</div>'
                     '<div class="nx-oos-ex">' + ex + '</div></div>')
        if url:
            parts.append('<a class="nx-oos-btn" href="' + _h.escape(url) + '" target="_blank" rel="noopener">인사 챗봇으로 이동 ↗</a>')
        elif team:
            parts.append('<span class="nx-oos-team">' + team + '</span>')
        parts.append('</div>')
    if note:
        parts.append('<div class="nx-oos-crit"><span>⚠️</span><span>' + _h.escape(note) + '</span></div>')
    parts.append('</div>')
    return "".join(parts)
