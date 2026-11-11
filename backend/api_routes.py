"""REST routes used by the Streamlit dashboard. If API_KEY is set in .env, every call must send it."""

import hmac
import os
from collections import Counter, defaultdict
from typing import List, Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field

import core
import scheduler
import telegram_bot as bot
import timetable


def check_key(x_api_key: str = Header(default="")) -> None:
    expected = os.environ.get("API_KEY", "")
    if expected and not hmac.compare_digest(x_api_key, expected):
        raise HTTPException(status_code=401, detail="Wrong or missing API key")


router = APIRouter(prefix="/api", dependencies=[Depends(check_key)])


def _dump(model) -> dict:
    return model.model_dump() if hasattr(model, "model_dump") else model.dict()


@router.get("/today")
async def today(request: Request):
    db = request.app.state.db
    tasks = [dict(r) for r in await db.fetch(core.TODAY_TASKS)]
    counts = Counter(t["status"] for t in tasks)
    s = await core.get_settings(db)
    return {
        "now": await db.fetchval("SELECT now()"),
        "timezone": s["timezone"],
        "tasks": tasks,
        "counts": dict(counts),
        "score": core.day_score(counts["done"], counts["partial"], counts["missed"]),
        "streak": await core.streak_info(db),
        "reminders_on": s["reminders_on"],
    }


@router.get("/insights")
async def insights(request: Request, days: int = 14):
    days = max(3, min(days, 90))
    db = request.app.state.db
    s = await core.get_settings(db)
    rows = await db.fetch(
        """
        SELECT t.block_id, b.title, b.category, to_char(b.start_time, 'HH24:MI') AS start_time,
               (t.scheduled_for AT TIME ZONE $1)::date AS day, t.status::text AS status
        FROM task_log t JOIN routine_blocks b ON b.id = t.block_id
        WHERE t.scheduled_for <= now()
          AND t.scheduled_for >= ((date_trunc('day', now() AT TIME ZONE $1) - make_interval(days => $2 - 1)) AT TIME ZONE $1)
        ORDER BY day, b.start_time
        """, s["timezone"], days)
    per_day, per_block, blocks, cells = defaultdict(Counter), defaultdict(Counter), {}, []
    for r in rows:
        per_day[r["day"]][r["status"]] += 1
        per_block[r["block_id"]][r["status"]] += 1
        blocks[r["block_id"]] = {"block_id": r["block_id"], "title": r["title"], "category": r["category"], "start_time": r["start_time"]}
        cells.append({"day": r["day"], "block_id": r["block_id"], "status": r["status"]})
    daily = [{"day": d, "done": c["done"], "partial": c["partial"], "skipped": c["skipped"], "missed": c["missed"],
              "total": sum(c.values()), "score": core.day_score(c["done"], c["partial"], c["missed"])}
             for d, c in sorted(per_day.items())]
    by_block = []
    for bid, b in sorted(blocks.items(), key=lambda kv: kv[1]["start_time"]):
        c = per_block[bid]
        by_block.append({**b, "done": c["done"], "partial": c["partial"], "skipped": c["skipped"], "missed": c["missed"],
                         "total": sum(c.values()), "rate": core.day_score(c["done"], c["partial"], c["missed"])})
    return {"days": days, "daily": daily, "by_block": by_block, "cells": cells, "streak": await core.streak_info(db)}


class Reply(BaseModel):
    action: str  # done, partial, skip or missed


@router.post("/tasks/{task_id}/reply")
async def reply(task_id: int, body: Reply, request: Request):
    row = await core.set_status(request.app.state.db, task_id, body.action)
    if row is None:
        raise HTTPException(status_code=404, detail="Task not found or unknown action")
    return {"ok": True, "status": row["status"]}


# ----------------------------- timetable -----------------------------

class BlockIn(BaseModel):
    id: Optional[int] = None
    title: str
    category: str = "other"
    start_time: str
    end_time: str
    activities: str = ""
    tip: str = ""
    active: bool = True


def _check_blocks(rows: List[dict]) -> None:
    for r in rows:
        if not r["title"].strip():
            raise HTTPException(status_code=400, detail="Every habit needs a title")
        for key in ("start_time", "end_time"):
            try:
                timetable._t(r[key])
            except ValueError:
                raise HTTPException(status_code=400, detail="Times must look like 07:15")


async def _apply(request: Request, rows: List[dict], by_title: bool) -> dict:
    db = request.app.state.db
    _check_blocks(rows)
    async with db.acquire() as conn:
        async with conn.transaction():
            result = await timetable.sync_blocks(conn, rows, match_by_title=by_title)
    await scheduler.generate(db)  # changes take effect today
    return result


@router.get("/blocks")
async def list_blocks(request: Request):
    rows = await request.app.state.db.fetch(
        "SELECT id, title, category, to_char(start_time, 'HH24:MI') AS start_time, to_char(end_time, 'HH24:MI') AS end_time, "
        "activities, tip, active FROM routine_blocks ORDER BY active DESC, start_time")
    return [dict(r) for r in rows]


@router.put("/blocks")
async def save_blocks(rows: List[BlockIn], request: Request):
    return await _apply(request, [_dump(r) for r in rows], by_title=False)


class ImportBody(BaseModel):
    markdown: str


@router.post("/blocks/import")
async def import_blocks(body: ImportBody, request: Request):
    rows = timetable.parse_markdown(body.markdown)
    if not rows:
        raise HTTPException(status_code=400, detail="No timetable table found. It needs columns: time window, block, activities, tip")
    return await _apply(request, rows, by_title=True)


@router.post("/blocks/reset")
async def reset_blocks(request: Request):
    rows = timetable.parse_markdown(timetable.DEFAULT_FILE.read_text(encoding="utf-8"))
    return await _apply(request, rows, by_title=True)


# ----------------------------- settings -----------------------------

class SettingsIn(BaseModel):
    timezone: Optional[str] = None
    check_after_min: Optional[int] = Field(default=None, ge=1, le=120)
    nudge_after_min: Optional[int] = Field(default=None, ge=1, le=240)
    miss_after_min: Optional[int] = Field(default=None, ge=1, le=480)
    streak_pct: Optional[int] = Field(default=None, ge=1, le=100)
    reminders_on: Optional[bool] = None


@router.get("/settings")
async def get_settings(request: Request):
    s = await core.get_settings(request.app.state.db)
    return {**s, "telegram_problem": bot.send_problem(), "dry_run": bot.dry_run()}


@router.put("/settings")
async def put_settings(body: SettingsIn, request: Request):
    if body.timezone:
        try:
            ZoneInfo(body.timezone)
        except Exception:
            raise HTTPException(status_code=400, detail="Unknown time zone, for example Asia/Kolkata")
    await request.app.state.db.execute(
        "UPDATE settings SET timezone = COALESCE($1, timezone), check_after_min = COALESCE($2, check_after_min), "
        "nudge_after_min = COALESCE($3, nudge_after_min), miss_after_min = COALESCE($4, miss_after_min), "
        "streak_pct = COALESCE($5, streak_pct), reminders_on = COALESCE($6, reminders_on) WHERE id = 1",
        body.timezone, body.check_after_min, body.nudge_after_min, body.miss_after_min, body.streak_pct, body.reminders_on)
    return await get_settings(request)


@router.post("/test-message")
async def test_message(request: Request):
    problem = bot.send_problem()
    if problem:
        raise HTTPException(status_code=400, detail=problem)
    if not await bot.notify(request.app.state.db, "✅ Test from Habit Coach. If you can read this, the bot is connected."):
        raise HTTPException(status_code=502, detail="Telegram refused the message. Check the bot token and chat ID")
    return {"ok": True}


@router.get("/messages")
async def messages(request: Request, limit: int = 30):
    rows = await request.app.state.db.fetch(
        "SELECT direction, body, status, created_at FROM message_log ORDER BY id DESC LIMIT $1", max(1, min(limit, 200)))
    return [dict(r) for r in rows]
