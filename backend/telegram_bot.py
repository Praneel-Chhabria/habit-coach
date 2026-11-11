"""Telegram side of Habit Coach: sends the prompts and checks and reads your button taps.
It uses long polling, so no public address or ngrok is needed. Only the owner's chat is answered."""

import asyncio
import html
import json
import os
import traceback
import urllib.error
import urllib.request
from typing import List, Optional, Tuple

import core

Buttons = List[List[Tuple[str, str]]]
ICON = {"done": "✅", "partial": "🟡", "skipped": "⏭", "missed": "❌", "prompted": "▶️", "checked": "❓", "pending": "⚪"}


def _token() -> str:
    return os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()


def owner_chat_id() -> Optional[str]:
    return os.environ.get("TELEGRAM_OWNER_CHAT_ID", "").strip() or None


def dry_run() -> bool:
    return os.environ.get("DRY_RUN", "").lower() in ("1", "true", "yes")


def polling_enabled() -> bool:
    return bool(_token()) and not dry_run()


def send_problem() -> Optional[str]:
    """Why messages cannot be sent right now, or None when they can."""
    if dry_run():
        return None
    if not _token():
        return "TELEGRAM_BOT_TOKEN is not set in backend/.env"
    if not owner_chat_id():
        return "TELEGRAM_OWNER_CHAT_ID is not set. Send /start to your bot to get it"
    return None


def _call_sync(method: str, payload: dict, timeout: int = 15) -> dict:
    req = urllib.request.Request(
        "https://api.telegram.org/bot%s/%s" % (_token(), method),
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        raise RuntimeError("Telegram %s failed with %s: %s" % (method, exc.code, exc.read().decode()))


async def _call(method: str, payload: dict, timeout: int = 15) -> dict:
    return await asyncio.to_thread(_call_sync, method, payload, timeout)


async def send_message(chat_id: str, text: str, buttons: Optional[Buttons] = None) -> str:
    if dry_run():
        print("[dry run] to %s: %s%s" % (chat_id, text.replace("\n", " | ")[:160], "  " + str(buttons) if buttons else ""))
        return "dry-run"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    if buttons:
        payload["reply_markup"] = {"inline_keyboard": [[{"text": t, "callback_data": d} for t, d in row] for row in buttons]}
    result = await _call("sendMessage", payload)
    return str(result.get("result", {}).get("message_id", "sent"))


async def notify(db, text: str, buttons: Optional[Buttons] = None) -> bool:
    """Sends a message to you and logs it. Returns False when it could not be sent."""
    if send_problem():
        return False
    try:
        await send_message(owner_chat_id() or "dry-run", text, buttons)
    except Exception as exc:
        print("Telegram send failed: %s" % exc)
        await core.log_message(db, "outbound", text, "failed")
        return False
    await core.log_message(db, "outbound", text, "sent")
    return True


# ---------------------------------------------------------------------------
# Message texts
# ---------------------------------------------------------------------------

def prompt_text(b: dict) -> str:
    steps = "\n".join("• " + html.escape(s) for s in b["activities"].splitlines() if s.strip())
    tip = "\n\n💡 <i>%s</i>" % html.escape(b["tip"]) if b["tip"] else ""
    return "⏰ <b>%s · %s</b>\n\n%s%s" % (b["start_time"], html.escape(b["title"]), steps, tip)


def prompt_buttons(task_id: int) -> Buttons:
    return [[("⏭ Skip this one", "t:%d:skip" % task_id)]]


def answer_buttons(task_id: int) -> Buttons:
    return [[("✅ Done", "t:%d:done" % task_id), ("🟡 Partly", "t:%d:partial" % task_id)],
            [("❌ Not done", "t:%d:missed" % task_id)]]


def check_text(title: str) -> str:
    return "👀 Quick check: did you do <b>%s</b>?" % html.escape(title)


def nudge_text(title: str) -> str:
    return "🔔 Still waiting to hear about <b>%s</b>. Done, partly, or not done?" % html.escape(title)


def missed_text(title: str, current: Optional[str]) -> str:
    go = "\n\nDon't write the day off. Jump straight into what is on now: <b>%s</b>." % html.escape(current) if current else \
        "\n\nDon't write the day off. Pick up with the next block."
    return "⏳ No answer for <b>%s</b>, so I marked it missed.%s" % (html.escape(title), go)


async def _reply_text(db, row: dict, action: str) -> str:
    title = html.escape(row["title"])
    if action == "done":
        info = await core.streak_info(db)
        streak = " 🔥 %d day streak." % info["current"] if info["current"] >= 2 else ""
        return "✅ Logged: <b>%s</b>.%s" % (title, streak)
    if action == "partial":
        return "🟡 <b>%s</b> partly done. That still counts. A little beats nothing." % title
    if action == "skip":
        return "⏭ Skipped <b>%s</b>." % title
    current = await core.current_block_title(db)
    return "❌ Noted: <b>%s</b>. No guilt spiral. %s" % (
        title, "Jump into what is on now: <b>%s</b>." % html.escape(current) if current else "Pick up with the next block.")


# ---------------------------------------------------------------------------
# Reading what you send
# ---------------------------------------------------------------------------

async def handle_callback(db, cb: dict) -> None:
    msg = cb.get("message") or {}
    chat_id, msg_id = str(msg.get("chat", {}).get("id", "")), msg.get("message_id")
    parts = (cb.get("data") or "").split(":")
    toast = "Got it"
    if len(parts) == 3 and parts[0] == "t" and parts[1].isdigit():
        row = await core.set_status(db, int(parts[1]), parts[2])
        if row:
            await core.log_message(db, "inbound", "%s: %s" % (row["title"], parts[2]))
            await _call("answerCallbackQuery", {"callback_query_id": cb["id"], "text": toast})
            if msg_id:  # buttons disappear once one is tapped
                await _call("editMessageReplyMarkup", {"chat_id": chat_id, "message_id": msg_id, "reply_markup": {"inline_keyboard": []}})
            await send_message(chat_id, await _reply_text(db, row, parts[2]))
            return
    await _call("answerCallbackQuery", {"callback_query_id": cb["id"], "text": "That one is no longer available"})


async def _today_text(db) -> str:
    rows = await db.fetch(core.TODAY_TASKS)
    if not rows:
        return "Nothing is scheduled today."
    lines = ["%s %s %s" % (ICON.get(r["status"], "•"), r["start_time"], html.escape(r["title"])) for r in rows]
    info = await core.streak_info(db)
    return "<b>Today</b>\n" + "\n".join(lines) + ("\n\n🔥 %d day streak" % info["current"] if info["current"] else "")


async def handle_message(db, text: str, chat_id: str) -> None:
    cmd = text.strip().lower().split("@")[0]
    if cmd in ("/start", "/help"):
        await send_message(chat_id, "Hi! I send each habit from your timetable when it is time, then check in a few minutes later.\n\n"
                                    "/today shows how today is going\n/pause stops messages\n/resume starts them again")
    elif cmd == "/today":
        await send_message(chat_id, await _today_text(db))
    elif cmd in ("/pause", "/resume"):
        await db.execute("UPDATE settings SET reminders_on = $1 WHERE id = 1", cmd == "/resume")
        await send_message(chat_id, "▶️ Messages are back on." if cmd == "/resume" else "⏸ Messages paused. Send /resume when you want them back.")
    else:
        await send_message(chat_id, "Tap the buttons on my messages, or send /today.")


async def handle_update(db, update: dict) -> None:
    cb = update.get("callback_query")
    msg = update.get("message") or {}
    chat_id = str((cb.get("message") or {}).get("chat", {}).get("id", "") if cb else msg.get("chat", {}).get("id", ""))
    owner = owner_chat_id()
    if owner is None:  # not set up yet: only help the owner find their chat id
        if not cb and (msg.get("text") or "").startswith("/start") and chat_id:
            await send_message(chat_id, "Your chat ID is <code>%s</code>.\nPut it in backend/.env as TELEGRAM_OWNER_CHAT_ID=%s and restart the backend." % (chat_id, chat_id))
        return
    if chat_id != owner:  # this bot answers only you
        return
    if cb:
        await handle_callback(db, cb)
    elif msg.get("text"):
        await core.log_message(db, "inbound", msg["text"])
        await handle_message(db, msg["text"], chat_id)


async def poll_forever(db) -> None:
    try:
        await _call("deleteWebhook", {})
    except Exception as exc:
        print("deleteWebhook failed: %s" % exc)
    print("Telegram polling started")
    offset = None
    while True:
        try:
            payload = {"timeout": 8, "allowed_updates": ["message", "callback_query"]}
            if offset:
                payload["offset"] = offset
            result = await _call("getUpdates", payload, timeout=20)
            for update in result.get("result", []):
                offset = update["update_id"] + 1
                try:
                    await handle_update(db, update)
                except Exception:
                    traceback.print_exc()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            print("Telegram polling error: %s" % exc)
            await asyncio.sleep(5)
