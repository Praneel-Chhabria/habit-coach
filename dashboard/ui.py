"""Look and feel of the dashboard. It matches the Elderly Care app: same colours, fonts and cards."""

import html
import math
import re
from datetime import date, datetime
from typing import Dict, List, Optional

import streamlit as st

CSS = """
@import url('https://fonts.googleapis.com/css2?family=Atkinson+Hyperlegible:wght@400;700&family=Fraunces:opsz,wght@9..144,500;9..144,600&display=swap');
:root{--mist:#e8f0ed;--paper:#ffffff;--ink:#0d2b2e;--muted:#587072;--line:#d6e3df;--brand:#0f6b6e;--brand-soft:#d4ede9;
--taken:#1c7a52;--taken-bg:#d8f0e3;--due:#8f5d0a;--due-bg:#fbeac6;--missed:#b3261e;--missed-bg:#fadbd8;}
.stApp{background-color:#eef4f1;background-image:radial-gradient(900px 480px at 8% -8%,#cfeee6 0%,transparent 62%),radial-gradient(800px 420px at 100% 0%,#f6e8cf 0%,transparent 58%);background-attachment:fixed;color:var(--ink);}
.stApp,.stApp p,.stApp label,.stApp li,.stApp button,.stApp input,.stApp textarea{font-family:'Atkinson Hyperlegible',system-ui,sans-serif;}
header[data-testid="stHeader"],footer,#MainMenu{display:none;}
.block-container{max-width:880px;padding-top:2rem;padding-bottom:4rem;}
h1,h2,h3{font-family:'Fraunces',Georgia,serif!important;font-weight:600!important;letter-spacing:-0.01em;color:var(--ink);}
.card{background:var(--paper);border:1px solid var(--line);border-radius:24px;box-shadow:0 1px 2px rgb(13 43 46/6%),0 18px 40px -22px rgb(13 43 46/28%);padding:1.2rem 1.4rem;}
.eyebrow{font-size:.8rem;font-weight:700;letter-spacing:.14em;text-transform:uppercase;color:var(--brand);}
.title{font-family:'Fraunces',Georgia,serif;font-size:3rem;font-weight:600;line-height:1.1;margin:0;}
.sub{color:var(--muted);}
.head{display:flex;justify-content:space-between;align-items:flex-end;gap:1rem;flex-wrap:wrap;margin-bottom:.5rem;}
.live{display:inline-flex;gap:.5rem;align-items:center;background:#fff;border-radius:999px;padding:.2rem .8rem;font-weight:700;color:var(--taken);box-shadow:0 1px 2px rgb(0 0 0/6%);font-size:.9rem;}
.live.off{color:var(--due);background:var(--due-bg);}
.dot{width:.6rem;height:.6rem;border-radius:50%;background:var(--taken);animation:pulse 1.8s ease-out infinite;}
@keyframes pulse{0%{box-shadow:0 0 0 0 rgb(28 122 82/.5)}100%{box-shadow:0 0 0 8px rgb(28 122 82/0)}}
.tiles{display:grid;grid-template-columns:repeat(3,1fr);gap:1rem;margin:1.2rem 0 1.4rem;}
@media(max-width:700px){.tiles{grid-template-columns:1fr;}}
.tile{display:flex;align-items:center;gap:1rem;}
.tile-label{font-size:.76rem;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);}
.tile-value{font-family:'Fraunces',Georgia,serif;font-size:1.9rem;font-weight:600;line-height:1.15;}
.tile-note{color:var(--muted);font-size:.9rem;}
.task{background:#fff;border:1px solid var(--line);border-radius:18px;padding:.85rem 1.1rem;margin:.6rem 0 .3rem;}
.task-top{display:flex;justify-content:space-between;align-items:center;gap:.6rem;}
.task-time{font-family:'Fraunces',Georgia,serif;font-size:1.15rem;font-weight:600;}
.task-title{font-size:1.1rem;font-weight:700;margin-top:.15rem;}
.task-sub{color:var(--muted);font-size:.95rem;}
.pill{display:inline-flex;gap:.3rem;align-items:center;border-radius:999px;padding:.15rem .7rem;font-size:.85rem;font-weight:700;white-space:nowrap;}
details{margin-top:.35rem;} summary{cursor:pointer;font-weight:700;color:var(--brand);}
.row{display:flex;align-items:center;gap:1rem;margin:.5rem 0;}
.row-name{width:11rem;font-weight:700;font-size:.95rem;flex-shrink:0;}
.row-val{width:6.5rem;text-align:right;color:var(--muted);font-size:.9rem;flex-shrink:0;}
.bar{height:.9rem;border-radius:999px;background:var(--mist);flex:1;}
.bar>span{display:block;height:100%;border-radius:999px;}
.hm{border-collapse:separate;border-spacing:4px;width:100%;}
.hm-name{font-weight:700;font-size:.88rem;white-space:nowrap;padding-right:.6rem;text-align:left;}
.hm-day{font-size:.72rem;color:var(--muted);font-weight:700;text-align:center;line-height:1.15;}
.hm-cell{display:block;width:100%;min-width:14px;height:20px;border-radius:6px;}
.legend{display:flex;gap:1rem;flex-wrap:wrap;margin-top:.7rem;font-size:.85rem;color:var(--muted);}
.legend i{display:inline-block;width:.8rem;height:.8rem;border-radius:4px;margin-right:.3rem;vertical-align:-1px;}
.stButton>button,.stFormSubmitButton>button{border-radius:12px;font-weight:700;border:1px solid var(--line);}
.stTabs [data-baseweb="tab"]{font-weight:700;font-size:1.02rem;}
"""

STATUS = {
    "done": ("Done", "✓", "var(--taken-bg)", "var(--taken)"),
    "partial": ("Partly", "◐", "var(--due-bg)", "var(--due)"),
    "skipped": ("Skipped", "–", "var(--mist)", "var(--muted)"),
    "missed": ("Missed", "!", "var(--missed-bg)", "var(--missed)"),
    "prompted": ("Do it now", "▶", "var(--brand-soft)", "var(--brand)"),
    "checked": ("Waiting for you", "?", "var(--due-bg)", "var(--due)"),
    "pending": ("Upcoming", "○", "var(--mist)", "var(--muted)"),
}
MARK = {  # timeline marker: background, border, text
    "done": ("var(--taken)", "var(--taken)", "#fff", "✓"), "partial": ("var(--due)", "var(--due)", "#fff", "◐"),
    "missed": ("var(--missed)", "var(--missed)", "#fff", "!"), "skipped": ("var(--mist)", "var(--line)", "var(--muted)", "–"),
    "prompted": ("var(--brand)", "var(--brand)", "#fff", "▶"), "checked": ("var(--due)", "var(--due)", "#fff", "?"),
    "pending": ("#fff", "var(--brand)", "var(--brand)", ""),
}
CAT_ICON = {"wake": "☕", "movement": "🏃", "hygiene": "🪥", "meal": "🍳", "study": "📚", "break": "🌿",
            "wind_down": "🌙", "sleep": "😴", "other": "•"}
HEAT = {"done": "var(--taken)", "partial": "var(--due)", "missed": "var(--missed)", "skipped": "var(--line)",
        "pending": "#e3ebe8", "prompted": "#e3ebe8", "checked": "#e3ebe8"}


def h(s: str) -> str:
    """One line, so markdown never turns indented HTML into a code block."""
    return re.sub(r"\s*\n\s*", "", s.strip())


def inject_css() -> None:
    st.markdown("<style>%s</style>" % CSS, unsafe_allow_html=True)


def render(s: str) -> None:
    st.markdown(h(s), unsafe_allow_html=True)


def parse_dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _mins(hhmm: str) -> int:
    hh, mm = hhmm.split(":")[:2]
    return int(hh) * 60 + int(mm)


def _hour(hr: int) -> str:
    return "%d %s" % ((hr % 12) or 12, "am" if hr < 12 else "pm")


def header(eyebrow: str, title: str, subtitle: str, live: Optional[bool] = None, live_text: str = "") -> None:
    pill = ""
    if live is True:
        pill = '<span class="live"><span class="dot"></span>Live</span>'
    elif live is False:
        pill = '<span class="live off">%s</span>' % html.escape(live_text)
    render('<div class="head"><div><div class="eyebrow">%s</div><div class="title">%s</div><div class="sub">%s</div></div>%s</div>'
           % (html.escape(eyebrow), html.escape(title), html.escape(subtitle), pill))


def ring(done: int, total: int, missed: int = 0, size: int = 72) -> str:
    stroke = 8
    r = (size - stroke) / 2
    c = 2 * math.pi * r
    frac = 0 if total == 0 else min(1, done / total)
    color = "var(--missed)" if missed else ("var(--taken)" if total and done == total else "var(--brand)")
    label = "–" if total == 0 else "%d/%d" % (done, total)
    return h(f"""<div style="position:relative;width:{size}px;height:{size}px;flex-shrink:0">
    <svg width="{size}" height="{size}" style="transform:rotate(-90deg)">
    <circle cx="{size / 2}" cy="{size / 2}" r="{r}" fill="none" stroke="var(--mist)" stroke-width="{stroke}"/>
    <circle cx="{size / 2}" cy="{size / 2}" r="{r}" fill="none" stroke="{color}" stroke-width="{stroke}" stroke-linecap="round" stroke-dasharray="{c}" stroke-dashoffset="{c * (1 - frac)}"/>
    </svg><span style="position:absolute;inset:0;display:grid;place-items:center;font-weight:700;font-size:.85rem">{label}</span></div>""")


def tiles(done: int, total: int, missed: int, streak: dict, focus_label: str, focus_title: str, focus_note: str) -> None:
    best = "Best: %d day%s" % (streak["best"], "" if streak["best"] == 1 else "s")
    render(f"""<div class="tiles">
    <div class="card tile">{ring(done, total, missed)}<div><div class="tile-label">Habits today</div><div class="tile-value">{done}<span class="sub">/{total}</span></div></div></div>
    <div class="card"><div class="tile-label">Streak</div><div class="tile-value">{"🔥 " if streak["current"] else ""}{streak["current"]} day{"" if streak["current"] == 1 else "s"}</div><div class="tile-note">{best}, counts at {streak["threshold"]}%</div></div>
    <div class="card"><div class="tile-label">{html.escape(focus_label)}</div><div class="tile-value" style="font-size:1.3rem">{html.escape(focus_title)}</div><div class="tile-note">{html.escape(focus_note)}</div></div>
    </div>""")


def timeline(tasks: List[dict], now_local: Optional[datetime]) -> str:
    if not tasks:
        return ""
    mins = [_mins(t["start_time"]) for t in tasks]
    start = min(6 * 60, min(m // 60 * 60 for m in mins))
    end = max(22 * 60, max((m + 60) // 60 * 60 for m in mins))
    pos = lambda m: min(100.0, max(0.0, (m - start) / (end - start) * 100))
    last: List[float] = []
    placed = []
    for t in sorted(tasks, key=lambda t: _mins(t["start_time"])):
        p = pos(_mins(t["start_time"]))
        lane = next((i for i, lp in enumerate(last) if p - lp >= 5), None)
        if lane is None:
            lane = len(last)
            last.append(p)
        else:
            last[lane] = p
        placed.append((t, p, lane))
    track = max(1, len(last)) * 38
    parts = []
    for hr in range(start // 60, end // 60 + 1, 3):
        x = pos(hr * 60)
        parts.append(f'<div style="position:absolute;left:{x}%;top:0;height:{track}px;border-left:1px dashed var(--line)"></div>'
                     f'<span style="position:absolute;left:{x}%;bottom:0;transform:translateX(-50%);font-size:.8rem;color:var(--muted)">{_hour(hr)}</span>')
    if now_local is not None:
        nm = now_local.hour * 60 + now_local.minute
        if start <= nm <= end:
            parts.append(f'<div style="position:absolute;left:{pos(nm)}%;top:0;height:{track}px;width:2px;background:var(--brand)">'
                         f'<span style="position:absolute;top:-2px;left:4px;background:var(--brand);color:#fff;font-size:.7rem;font-weight:700;border-radius:999px;padding:0 .5rem">Now</span></div>')
    for t, p, lane in placed:
        bg, border, fg, glyph = MARK[t["status"]]
        parts.append(f'<div title="{html.escape(t["start_time"] + " " + t["title"])}" style="position:absolute;left:{p}%;top:{lane * 38 + 2}px;width:32px;height:32px;margin-left:-16px;'
                     f'border-radius:50%;border:2px solid {border};background:{bg};color:{fg};display:grid;place-items:center;font-weight:700;font-size:.85rem">{glyph}</div>')
    return h(f'<div class="card" style="padding:.9rem 0 .6rem;background:rgb(255 255 255/70%)"><div style="margin:0 1.4rem;position:relative;height:{track + 30}px">{"".join(parts)}</div></div>')


def task_card(t: dict) -> str:
    label, glyph, bg, fg = STATUS[t["status"]]
    steps = "".join("<li>%s</li>" % html.escape(s) for s in t["activities"].splitlines() if s.strip())
    tip = '<div class="task-sub">💡 %s</div>' % html.escape(t["tip"]) if t["tip"] else ""
    detail = '<details><summary>Steps</summary><ul style="margin:.3rem 0 .3rem 1.1rem">%s</ul>%s</details>' % (steps, tip) if steps or tip else ""
    border = {"missed": "var(--missed)", "checked": "var(--due)", "prompted": "var(--brand)"}.get(t["status"], "var(--line)")
    return h(f"""<div class="task" style="border-color:{border}"><div class="task-top">
    <span class="task-time">{t["start_time"]}<span class="sub"> to {t["end_time"]}</span></span>
    <span class="pill" style="background:{bg};color:{fg}">{glyph} {label}</span></div>
    <div class="task-title">{CAT_ICON.get(t["category"], "•")} {html.escape(t["title"])}</div>{detail}</div>""")


def _bar(pct: float, color: str) -> str:
    return '<div class="bar"><span style="width:%.0f%%;background:%s"></span></div>' % (max(0, min(100, pct)), color)


def _rate_color(rate: float, threshold: int) -> str:
    return "var(--taken)" if rate * 100 >= threshold else ("var(--due)" if rate >= 0.4 else "var(--missed)")


def daily_bars(daily: List[dict], threshold: int) -> str:
    rows = []
    for d in daily:
        day = date.fromisoformat(d["day"])
        if d["score"] is None:
            bar, note = _bar(0, "var(--line)"), "no answers"
        else:
            bar, note = _bar(d["score"] * 100, _rate_color(d["score"], threshold)), "%d%%" % round(d["score"] * 100)
        rows.append(f'<div class="row"><div class="row-name" style="width:6rem">{day:%a %d %b}</div>{bar}<div class="row-val">{note}</div></div>')
    return h('<div class="card">%s</div>' % "".join(rows)) if rows else ""


def habit_bars(by_block: List[dict], threshold: int) -> str:
    rows = []
    for b in sorted(by_block, key=lambda b: (b["rate"] is None, b["rate"] or 0)):
        if b["rate"] is None:
            continue
        rows.append(f'<div class="row"><div class="row-name">{CAT_ICON.get(b["category"], "•")} {html.escape(b["title"])}</div>'
                    f'{_bar(b["rate"] * 100, _rate_color(b["rate"], threshold))}<div class="row-val">{round(b["rate"] * 100)}% of {b["done"] + b["partial"] + b["missed"]}</div></div>')
    return h('<div class="card">%s</div>' % "".join(rows)) if rows else ""


def heatmap(by_block: List[dict], cells: List[dict]) -> str:
    days = sorted({c["day"] for c in cells})
    if not days:
        return ""
    status = {(c["day"], c["block_id"]): c["status"] for c in cells}
    head = "".join('<th class="hm-day">%s<br>%s</th>' % (date.fromisoformat(d).strftime("%a"), date.fromisoformat(d).strftime("%d")) for d in days)
    body = []
    for b in by_block:
        tds = []
        for d in days:
            s = status.get((d, b["block_id"]))
            tds.append('<td><span class="hm-cell" title="%s" style="background:%s"></span></td>' % (s, HEAT[s]) if s else "<td></td>")
        body.append('<tr><td class="hm-name">%s %s</td>%s</tr>' % (CAT_ICON.get(b["category"], "•"), html.escape(b["title"]), "".join(tds)))
    legend = "".join('<span><i style="background:%s"></i>%s</span>' % (c, n) for c, n in
                     [("var(--taken)", "Done"), ("var(--due)", "Partly"), ("var(--missed)", "Missed"), ("var(--line)", "Skipped")])
    return h('<div class="card" style="overflow-x:auto"><table class="hm"><tr><th></th>%s</tr>%s</table><div class="legend">%s</div></div>' % (head, "".join(body), legend))
