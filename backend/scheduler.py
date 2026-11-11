"""Runs every 20 seconds inside the backend: builds today's tasks, sends the prompt when a habit
starts, checks in a few minutes later, nudges once, and finally marks it missed."""

import asyncio
import traceback

import core
import telegram_bot as bot

TICK_SECONDS = 20
GRACE_MIN = 30  # a habit that is more than this late when the app was off is skipped, not prompted
_warned = False

GENERATE = """
INSERT INTO task_log (block_id, scheduled_for)
SELECT b.id, (ld.d + b.start_time) AT TIME ZONE s.timezone
FROM routine_blocks b
CROSS JOIN settings s
CROSS JOIN LATERAL (SELECT (now() AT TIME ZONE s.timezone)::date AS d) ld
WHERE b.active AND EXTRACT(ISODOW FROM ld.d)::smallint = ANY (b.days_of_week)
ON CONFLICT (block_id, scheduled_for) DO NOTHING
"""

PROMPTS = """
SELECT t.id, b.title, b.activities, b.tip, to_char(b.start_time, 'HH24:MI') AS start_time
FROM task_log t JOIN routine_blocks b ON b.id = t.block_id
WHERE t.status = 'pending' AND t.scheduled_for <= now()
  AND t.scheduled_for > now() - make_interval(mins => $1)
ORDER BY t.scheduled_for
"""

CHECKS = """
SELECT t.id, b.title FROM task_log t JOIN routine_blocks b ON b.id = t.block_id CROSS JOIN settings s
WHERE t.status = 'prompted' AND t.prompted_at <= now() - make_interval(mins => s.check_after_min)
ORDER BY t.scheduled_for
"""

NUDGES = """
SELECT t.id, b.title FROM task_log t JOIN routine_blocks b ON b.id = t.block_id CROSS JOIN settings s
WHERE t.status = 'checked' AND t.nudged_at IS NULL AND t.checked_at <= now() - make_interval(mins => s.nudge_after_min)
ORDER BY t.scheduled_for
"""

MISSES = """
SELECT t.id, b.title FROM task_log t JOIN routine_blocks b ON b.id = t.block_id CROSS JOIN settings s
WHERE t.status = 'checked' AND t.checked_at <= now() - make_interval(mins => s.miss_after_min)
ORDER BY t.scheduled_for
"""


async def generate(db) -> None:
    await db.execute(GENERATE)


async def _ready(db) -> bool:
    global _warned
    if not (await core.get_settings(db))["reminders_on"]:
        return False
    problem = bot.send_problem()
    if problem:
        if not _warned:
            print("Not sending messages: %s" % problem)
            _warned = True
        return False
    return True


async def send_prompts(db) -> None:
    for r in await db.fetch(PROMPTS, GRACE_MIN):
        if await bot.notify(db, bot.prompt_text(dict(r)), bot.prompt_buttons(r["id"])):
            await db.execute("UPDATE task_log SET status = 'prompted', prompted_at = now() WHERE id = $1", r["id"])


async def send_checks(db) -> None:
    for r in await db.fetch(CHECKS):
        if await bot.notify(db, bot.check_text(r["title"]), bot.answer_buttons(r["id"])):
            await db.execute("UPDATE task_log SET status = 'checked', checked_at = now() WHERE id = $1", r["id"])


async def send_nudges(db) -> None:
    for r in await db.fetch(NUDGES):
        if await bot.notify(db, bot.nudge_text(r["title"]), bot.answer_buttons(r["id"])):
            await db.execute("UPDATE task_log SET nudged_at = now() WHERE id = $1", r["id"])


async def mark_missed(db) -> None:
    for r in await db.fetch(MISSES):
        await db.execute("UPDATE task_log SET status = 'missed', responded_at = now() WHERE id = $1", r["id"])
        await bot.notify(db, bot.missed_text(r["title"], await core.current_block_title(db)))


async def tick(db) -> None:
    await generate(db)
    # Habits the app was too late for (it was off, or the timetable changed) are skipped, never prompted late.
    await db.execute("UPDATE task_log SET status = 'skipped' WHERE status = 'pending' "
                     "AND scheduled_for < now() - make_interval(mins => $1)", GRACE_MIN)
    if await _ready(db):
        await send_prompts(db)
        await send_checks(db)
        await send_nudges(db)
        await mark_missed(db)


async def run_forever(db) -> None:
    print("Scheduler started")
    while True:
        try:
            await tick(db)
        except asyncio.CancelledError:
            raise
        except Exception:
            traceback.print_exc()
        await asyncio.sleep(TICK_SECONDS)
