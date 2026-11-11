"""Habit Coach dashboard. Run with:  streamlit run app.py"""

import hmac
import html
import os
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

import ui
from client import Api, ApiError

st.set_page_config(page_title="Habit Coach", page_icon="🌿", layout="centered")
ui.inject_css()
api = Api()

CATEGORIES = ["wake", "movement", "hygiene", "meal", "study", "break", "wind_down", "sleep", "other"]
STEPS = "Steps (separate with |)"
COLUMNS = ["id", "Active", "Start", "End", "Habit", "Type", STEPS, "Tip"]


def gate() -> None:
    password = os.environ.get("APP_PASSWORD", "")
    if not password or st.session_state.get("authed"):
        return
    ui.header("Habit coach", "Welcome back", "Enter your password to continue")
    entered = st.text_input("Password", type="password")
    if st.button("Sign in", type="primary"):
        if hmac.compare_digest(entered, password):
            st.session_state["authed"] = True
            st.rerun()
        st.error("Wrong password")
    st.stop()


def live(seconds: int):
    """Refreshes a section on its own. Falls back to a plain section on older Streamlit versions."""
    frag = getattr(st, "fragment", None)
    return (lambda fn: frag(run_every=seconds)(fn)) if frag else (lambda fn: fn)


def refresh() -> None:
    try:
        st.rerun(scope="fragment")  # redraw just the live section
    except Exception:  # older Streamlit, or not inside a fragment: redraw the whole page
        st.rerun()


def stat_cards(items) -> None:
    cards = "".join('<div class="card"><div class="tile-label">%s</div><div class="tile-value">%s</div><div class="tile-note">%s</div></div>'
                    % (html.escape(l), v, html.escape(n)) for l, v, n in items)
    ui.render('<div class="tiles">%s</div>' % cards)


# ------------------------------------------------------------------ Today

@live(15)
def today_view() -> None:
    try:
        data = api.today()
    except ApiError as exc:
        st.error(str(exc))
        return
    tz = ZoneInfo(data["timezone"])
    now = ui.parse_dt(data["now"]).astimezone(tz)
    tasks, counts = data["tasks"], data["counts"]
    total = len(tasks) - counts.get("skipped", 0)
    ui.header("Habit coach", "Today", "%s" % now.strftime("%A, %d %B"),
              live=data["reminders_on"] or False, live_text="Messages paused")

    waiting = [t for t in tasks if t["status"] in ("checked", "prompted")]
    upcoming = [t for t in tasks if t["status"] == "pending"]
    if waiting:
        t = waiting[0]
        focus = ("On now", t["title"], "Waiting for your answer" if t["status"] == "checked" else "Do it now, then answer in Telegram")
    elif upcoming:
        focus = ("Up next", upcoming[0]["title"], "At %s" % upcoming[0]["start_time"])
    else:
        focus = ("Up next", "Nothing left today", "Rest well")
    ui.tiles(counts.get("done", 0), total, counts.get("missed", 0), data["streak"], *focus)

    if not tasks:
        st.info("Nothing is scheduled today. Add habits in the Timetable tab.")
        return
    ui.render(ui.timeline(tasks, now))
    st.markdown("### Today's habits")
    for t in tasks:
        ui.render(ui.task_card(t))
        if t["status"] not in ("pending", "done"):
            cols = st.columns([1, 1, 1, 3])
            for col, (label, action) in zip(cols, (("✅ Done", "done"), ("🟡 Partly", "partial"), ("⏭ Skip", "skip"))):
                if col.button(label, key="%d-%s" % (t["id"], action)):
                    try:
                        api.reply(t["id"], action)
                    except ApiError as exc:
                        st.error(str(exc))
                    else:
                        refresh()


# ------------------------------------------------------------------ Insights

def insights_view() -> None:
    days = st.radio("Show the last", [7, 14, 30], index=1, horizontal=True, format_func=lambda d: "%d days" % d)
    try:
        data = api.insights(days)
    except ApiError as exc:
        st.error(str(exc))
        return
    streak, daily, by_block = data["streak"], data["daily"], data["by_block"]
    scores = [d["score"] for d in daily if d["score"] is not None]
    average = "%d%%" % round(sum(scores) / len(scores) * 100) if scores else "–"
    stat_cards([("Average day", average, "Across the days with answers"),
                ("Current streak", "%d day%s" % (streak["current"], "" if streak["current"] == 1 else "s"), "A good day is %d%% or more" % streak["threshold"]),
                ("Best streak", "%d day%s" % (streak["best"], "" if streak["best"] == 1 else "s"), "Longest run so far")])
    if not daily:
        st.info("Nothing to show yet. Answer a few habits and this fills in.")
        return
    rated = [b for b in by_block if b["rate"] is not None and (b["done"] + b["partial"] + b["missed"]) >= 3]
    if rated:
        hardest, easiest = min(rated, key=lambda b: b["rate"]), max(rated, key=lambda b: b["rate"])
        st.markdown("**Hardest habit:** %s, done %d%% of the time. **Easiest:** %s, %d%%." %
                    (hardest["title"], round(hardest["rate"] * 100), easiest["title"], round(easiest["rate"] * 100)))
    st.markdown("### Each day")
    ui.render(ui.daily_bars(daily, streak["threshold"]))
    st.markdown("### Habit by habit")
    st.caption("Hardest first. These are the ones to fix.")
    ui.render(ui.habit_bars(by_block, streak["threshold"]))
    st.markdown("### Every habit, every day")
    ui.render(ui.heatmap(by_block, data["cells"]))


# ------------------------------------------------------------------ Timetable

def _blank(value) -> str:
    return "" if value is None or (isinstance(value, float) and pd.isna(value)) else str(value).strip()


def _blocks_frame(blocks: list) -> pd.DataFrame:
    parse = lambda s: datetime.strptime(s, "%H:%M").time()
    return pd.DataFrame([{
        "id": b["id"], "Active": b["active"], "Start": parse(b["start_time"]), "End": parse(b["end_time"]),
        "Habit": b["title"], "Type": b["category"], STEPS: " | ".join(b["activities"].splitlines()), "Tip": b["tip"],
    } for b in blocks], columns=COLUMNS)


def _rows_from(df: pd.DataFrame) -> list:
    rows = []
    for _, r in df.iterrows():
        title = _blank(r["Habit"])
        if not title:
            continue
        if pd.isna(r["Start"]) or pd.isna(r["End"]):
            raise ValueError("%s needs a start and an end time" % title)
        rows.append({
            "id": None if pd.isna(r["id"]) else int(r["id"]),
            "active": bool(r["Active"]) if not pd.isna(r["Active"]) else True,
            "start_time": r["Start"].strftime("%H:%M"), "end_time": r["End"].strftime("%H:%M"),
            "title": title, "category": _blank(r["Type"]) or "other",
            "activities": "\n".join(s.strip() for s in _blank(r[STEPS]).split("|") if s.strip()), "tip": _blank(r["Tip"]),
        })
    return rows


def timetable_view() -> None:
    st.markdown("### Your timetable")
    st.caption("Each habit gets a message when it starts, then a check a few minutes later. Edit any cell, add a row at the bottom, "
               "untick Active to pause a habit, then save. Changes apply today.")
    try:
        blocks = api.blocks()
    except ApiError as exc:
        st.error(str(exc))
        return
    config = {
        "id": None,
        "Active": st.column_config.CheckboxColumn("Active", default=True),
        "Start": st.column_config.TimeColumn("Start", format="HH:mm", step=60),
        "End": st.column_config.TimeColumn("End", format="HH:mm", step=60),
        "Habit": st.column_config.TextColumn("Habit", required=True),
        "Type": st.column_config.SelectboxColumn("Type", options=CATEGORIES, default="other"),
        STEPS: st.column_config.TextColumn(STEPS, width="large"),
        "Tip": st.column_config.TextColumn("Friction reducer tip", width="large"),
    }
    frame = _blocks_frame(blocks)
    try:  # newer Streamlit versions use width, older ones use_container_width
        edited = st.data_editor(frame, column_config=config, num_rows="dynamic", hide_index=True, width="stretch", key="blocks_editor")
    except Exception:
        edited = st.data_editor(frame, column_config=config, num_rows="dynamic", hide_index=True, use_container_width=True, key="blocks_editor")
    if st.button("Save timetable", type="primary"):
        try:
            result = api.save_blocks(_rows_from(edited))
        except (ValueError, ApiError) as exc:
            st.error(str(exc))
        else:
            st.session_state.pop("blocks_editor", None)
            st.success("Saved. %d added, %d updated, %d paused." % (result["added"], result["updated"], result["removed"]))
            st.rerun()

    st.markdown("### Import or reset")
    upload = st.file_uploader("Import a timetable from a markdown file", type=["md", "txt"],
                              help="A table with columns: time window, block, activities, tip. Habits with the same name are updated.")
    if upload is not None and st.button("Replace the timetable with this file"):
        try:
            result = api.import_markdown(upload.getvalue().decode("utf-8"))
        except (UnicodeDecodeError, ApiError) as exc:
            st.error(str(exc))
        else:
            st.success("Imported. %d added, %d updated, %d paused." % (result["added"], result["updated"], result["removed"]))
            st.rerun()
    sure = st.checkbox("I want to go back to the original timetable")
    if sure and st.button("Reset the timetable"):
        try:
            api.reset_blocks()
        except ApiError as exc:
            st.error(str(exc))
        else:
            st.success("Back to the original timetable.")
            st.rerun()


# ------------------------------------------------------------------ Settings

def settings_view() -> None:
    try:
        s = api.settings()
    except ApiError as exc:
        st.error(str(exc))
        return
    st.markdown("### Telegram")
    if s["telegram_problem"]:
        st.warning("Messages are not being sent: %s." % s["telegram_problem"])
    elif s["dry_run"]:
        st.info("Dry run mode: messages are printed in the backend terminal, not sent.")
    else:
        st.success("Telegram is connected.")
    if st.button("Send a test message"):
        try:
            api.test_message()
        except ApiError as exc:
            st.error(str(exc))
        else:
            st.success("Sent. Check Telegram.")

    st.markdown("### Timing")
    with st.form("settings"):
        on = st.toggle("Send messages", value=s["reminders_on"])
        c1, c2, c3 = st.columns(3)
        check = c1.number_input("Check in after (minutes)", 1, 120, int(s["check_after_min"]))
        nudge = c2.number_input("Nudge after the check", 1, 240, int(s["nudge_after_min"]))
        miss = c3.number_input("Mark missed after the check", 1, 480, int(s["miss_after_min"]))
        c4, c5 = st.columns(2)
        pct = c4.number_input("A day counts toward the streak at (%)", 1, 100, int(s["streak_pct"]))
        tz = c5.text_input("Time zone", s["timezone"])
        if st.form_submit_button("Save settings", type="primary"):
            try:
                api.save_settings({"reminders_on": on, "check_after_min": int(check), "nudge_after_min": int(nudge),
                                   "miss_after_min": int(miss), "streak_pct": int(pct), "timezone": tz.strip()})
            except ApiError as exc:
                st.error(str(exc))
            else:
                st.success("Saved.")

    st.markdown("### Recent messages")
    try:
        messages = api.messages(15)
    except ApiError:
        messages = []
    zone = ZoneInfo(s["timezone"])
    rows = "".join('<div class="row"><div class="row-val" style="width:5rem;text-align:left">%s</div><div style="flex:1">%s %s</div></div>' % (
        ui.parse_dt(m["created_at"]).astimezone(zone).strftime("%d %b %H:%M"),
        "↑" if m["direction"] == "outbound" else "↓", html.escape((m["body"] or "").replace("\n", " ")[:110])) for m in messages)
    ui.render('<div class="card">%s</div>' % (rows or '<span class="sub">Nothing yet.</span>'))


gate()
tab_today, tab_insights, tab_timetable, tab_settings = st.tabs(["Today", "Insights", "Timetable", "Settings"])
with tab_today:
    today_view()
with tab_insights:
    insights_view()
with tab_timetable:
    timetable_view()
with tab_settings:
    settings_view()
