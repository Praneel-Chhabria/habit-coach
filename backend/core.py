"""Shared database helpers used by the scheduler, the Telegram bot and the API."""

from datetime import date, timedelta
from typing import Dict, List, Optional

ACTIONS = {"done": "done", "partial": "partial", "skip": "skipped", "missed": "missed"}

TODAY_TASKS = """
SELECT t.id, t.block_id, b.title, b.category, b.activities, b.tip,
       to_char(b.start_time, 'HH24:MI') AS start_time, to_char(b.end_time, 'HH24:MI') AS end_time,
       t.scheduled_for, t.status::text AS status, t.prompted_at, t.checked_at, t.responded_at
FROM task_log t
JOIN routine_blocks b ON b.id = t.block_id
CROSS JOIN settings s
WHERE (t.scheduled_for AT TIME ZONE s.timezone)::date = (now() AT TIME ZONE s.timezone)::date
ORDER BY t.scheduled_for
"""


async def get_settings(db) -> dict:
    return dict(await db.fetchrow("SELECT * FROM settings WHERE id = 1"))


async def log_message(db, direction: str, body: str, status: str = "ok") -> None:
    await db.execute("INSERT INTO message_log (direction, body, status) VALUES ($1, $2, $3)", direction, body[:2000], status)


async def set_status(db, task_id: int, action: str) -> Optional[dict]:
    """Records an answer. Used by the Telegram buttons and the dashboard buttons alike."""
    status = ACTIONS.get(action)
    if status is None:
        return None
    row = await db.fetchrow(
        "UPDATE task_log t SET status = $2::task_status, responded_at = now() FROM routine_blocks b "
        "WHERE t.id = $1 AND b.id = t.block_id RETURNING t.id, b.title, t.status::text AS status",
        task_id, status,
    )
    return dict(row) if row else None


async def current_block_title(db) -> Optional[str]:
    return await db.fetchval(
        "SELECT b.title FROM routine_blocks b CROSS JOIN settings s "
        "WHERE b.active AND (now() AT TIME ZONE s.timezone)::time >= b.start_time "
        "AND (now() AT TIME ZONE s.timezone)::time < b.end_time "
        "AND EXTRACT(ISODOW FROM (now() AT TIME ZONE s.timezone))::smallint = ANY (b.days_of_week) LIMIT 1"
    )


async def next_block_title(db) -> Optional[str]:
    return await db.fetchval(
        "SELECT b.title FROM task_log t JOIN routine_blocks b ON b.id = t.block_id "
        "WHERE t.status = 'pending' AND t.scheduled_for > now() ORDER BY t.scheduled_for LIMIT 1"
    )


def day_score(done: int, partial: int, missed: int) -> Optional[float]:
    """Share of the habits that were resolved today that you did. Partly done counts as half.
    Skipped and still waiting habits are left out, and a day with nothing resolved has no score."""
    resolved = done + partial + missed
    return None if resolved == 0 else (done + 0.5 * partial) / resolved


def compute_streaks(scores: Dict[date, Optional[float]], today: date, pct: int) -> dict:
    ok = lambda d: scores.get(d) is not None and scores[d] * 100 >= pct
    d = today if ok(today) else today - timedelta(days=1)  # today is not a failure until it is over
    current = 0
    while ok(d):
        current += 1
        d -= timedelta(days=1)
    best = run = 0
    if scores:
        d = min(scores)
        while d <= today:
            run = run + 1 if ok(d) else 0
            best = max(best, run)
            d += timedelta(days=1)
    return {"current": current, "best": best}


async def streak_info(db, days: int = 120) -> dict:
    s = await get_settings(db)
    rows = await db.fetch(
        """
        SELECT (t.scheduled_for AT TIME ZONE $1)::date AS day,
               COUNT(*) FILTER (WHERE t.status = 'done')    AS done,
               COUNT(*) FILTER (WHERE t.status = 'partial') AS partial,
               COUNT(*) FILTER (WHERE t.status = 'missed')  AS missed
        FROM task_log t
        WHERE t.scheduled_for >= now() - make_interval(days => $2) AND t.scheduled_for <= now()
        GROUP BY 1
        """, s["timezone"], days)
    scores = {r["day"]: day_score(r["done"], r["partial"], r["missed"]) for r in rows}
    today = await db.fetchval("SELECT (now() AT TIME ZONE $1)::date", s["timezone"])
    return {**compute_streaks(scores, today, s["streak_pct"]), "threshold": s["streak_pct"]}
