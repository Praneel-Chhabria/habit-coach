"""Reads a timetable written as a markdown table and keeps the routine_blocks table in sync."""

import re
from datetime import time
from pathlib import Path
from typing import List

DEFAULT_FILE = Path(__file__).parent / "data" / "timetable.md"

CATEGORIES = ["wake", "movement", "hygiene", "meal", "study", "break", "wind_down", "sleep", "other"]

# First match wins, so the more specific words come first.
CATEGORY_RULES = [
    ("study", "study"), ("movement", "movement"), ("run", "movement"), ("hygiene", "hygiene"),
    ("skincare", "hygiene"), ("wake", "wake"), ("coffee", "wake"), ("dopamine", "break"),
    ("wind", "wind_down"), ("bedtime", "sleep"), ("sleep", "sleep"), ("breakfast", "meal"),
    ("lunch", "meal"), ("dinner", "meal"),
]


def guess_category(title: str) -> str:
    t = title.lower()
    for word, cat in CATEGORY_RULES:
        if word in t:
            return cat
    return "other"


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("**", "").replace("`", "")).strip()


def parse_markdown(text: str) -> List[dict]:
    """Reads the first table: Time window | Block | Activities | Tip. Other tables are ignored."""
    rows, started = [], False
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            if started:
                break
            continue
        started = True
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 3 or set("".join(cells)) <= set(":- "):
            continue
        times = re.findall(r"(\d{1,2}):(\d{2})", cells[0])
        if len(times) < 2:
            continue  # the header row
        title = _clean(cells[1])
        steps = [_clean(re.sub(r"^[\u2022*\-\s]+", "", s)) for s in re.split(r"<br\s*/?>", cells[2])]
        rows.append({
            "title": title,
            "category": guess_category(title),
            "start_time": "%02d:%s" % (int(times[0][0]), times[0][1]),
            "end_time": "%02d:%s" % (int(times[1][0]), times[1][1]),
            "activities": "\n".join(s for s in steps if s),
            "tip": _clean(cells[3]) if len(cells) > 3 else "",
            "active": True,
        })
    return rows


def _t(value: str) -> time:
    return time.fromisoformat(value if len(value) > 5 else value + ":00")


async def sync_blocks(conn, rows: List[dict], match_by_title: bool = False) -> dict:
    """Makes routine_blocks match rows. A row with an id updates that block, a row without one
    is added, and blocks no longer listed are switched off (their history stays)."""
    existing = {r["id"]: r for r in await conn.fetch(
        "SELECT id, lower(title) AS title, to_char(start_time, 'HH24:MI') AS start FROM routine_blocks")}
    by_title = {r["title"]: i for i, r in existing.items()}
    keep, off, retimed = set(), set(), set()
    added = updated = 0
    for pos, r in enumerate(sorted(rows, key=lambda r: r["start_time"])):
        bid = r.get("id") if r.get("id") in existing else None
        if bid is None and match_by_title:
            bid = by_title.get(r["title"].strip().lower())
        cat = r.get("category") if r.get("category") in CATEGORIES else "other"
        vals = (pos, r["title"].strip(), cat, _t(r["start_time"]), _t(r["end_time"]),
                (r.get("activities") or "").strip(), (r.get("tip") or "").strip(), bool(r.get("active", True)))
        if bid:
            await conn.execute(
                "UPDATE routine_blocks SET position=$2, title=$3, category=$4, start_time=$5, end_time=$6, "
                "activities=$7, tip=$8, active=$9 WHERE id=$1", bid, *vals)
            if existing[bid]["start"] != r["start_time"][:5]:
                retimed.add(bid)
            updated += 1
        else:
            bid = await conn.fetchval(
                "INSERT INTO routine_blocks (position, title, category, start_time, end_time, activities, tip, active) "
                "VALUES ($1,$2,$3,$4,$5,$6,$7,$8) RETURNING id", *vals)
            added += 1
        (keep if vals[7] else off).add(bid)
    gone = [i for i in existing if i not in keep and i not in off]
    if gone:
        await conn.execute("UPDATE routine_blocks SET active = false WHERE id = ANY($1)", gone)
    # Open tasks of switched off or re-timed blocks are dropped. Tasks still waiting to start are
    # rebuilt by the scheduler at the new times.
    await conn.execute(
        "DELETE FROM task_log WHERE block_id = ANY($1) AND status IN ('pending','prompted','checked')",
        list(off | set(gone) | retimed))
    await conn.execute("DELETE FROM task_log WHERE status = 'pending'")
    return {"added": added, "updated": updated, "removed": len(gone)}


async def seed_if_empty(pool) -> int:
    """First start: load the bundled timetable so the app works straight away."""
    async with pool.acquire() as conn:
        if await conn.fetchval("SELECT COUNT(*) FROM routine_blocks"):
            return 0
        rows = parse_markdown(DEFAULT_FILE.read_text(encoding="utf-8"))
        async with conn.transaction():
            await sync_blocks(conn, rows)
        return len(rows)
