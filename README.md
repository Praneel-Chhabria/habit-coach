# Habit Coach

A personal habit app. It reads your timetable, messages you on Telegram when each habit starts, checks in
5 minutes later, and shows everything on a Streamlit dashboard. It is built the same way as the Elderly Care
app: FastAPI backend, PostgreSQL, a background scheduler and a Telegram bot.

```
Telegram  <->  backend (FastAPI, port 8001)  <->  PostgreSQL
                        ^
                        |  REST
                  dashboard (Streamlit, port 8501)
```

## What happens each day

1. The scheduler builds today's tasks from your timetable.
2. When a habit starts you get its steps and the friction reducer tip. A Skip button is on the message.
3. 5 minutes later: "Did you do it?" with Done, Partly and Not done buttons.
4. No answer 15 minutes after that: one nudge.
5. No answer 45 minutes after that: marked missed, with a reminder not to write the day off.

Telegram commands: /today, /pause, /resume. The timings are editable in the dashboard under Settings.

## Setup

**1. Database**

    createdb habit_coach
    psql -d habit_coach -f backend/schema.sql

**2. A new Telegram bot.** Open Telegram, message @BotFather, send /newbot and copy the token.

**3. Backend**

    cd backend
    python3 -m venv venv && source venv/bin/activate
    pip install -r requirements.txt
    cp .env.example .env

Fill in `.env`: your database user, `TELEGRAM_BOT_TOKEN`, and an `API_KEY` made with
`python3 -c "import secrets; print(secrets.token_hex(24))"`. Leave `TELEGRAM_OWNER_CHAT_ID` empty for now, then:

    uvicorn main:app --port 8001

On first start it loads `data/timetable.md` into the database. Now send /start to your bot. It replies with your
chat ID. Put that in `.env` as `TELEGRAM_OWNER_CHAT_ID` and restart the backend. The bot answers only that chat.

No ngrok is needed. The bot uses long polling, so it works on your laptop as it is.

**4. Dashboard** (a second terminal)

    cd dashboard
    python3 -m venv venv && source venv/bin/activate
    pip install -r requirements.txt
    cp .env.example .env      # use the same API_KEY as the backend
    streamlit run app.py

**5. Check it.** Dashboard, Settings, Send a test message. To try everything without Telegram, set `DRY_RUN=1`
in `backend/.env` and the messages print in the backend terminal.

## Changing the timetable

Dashboard, Timetable tab: edit the table, add rows, untick Active to pause a habit, then Save. You can also
upload a markdown file with the same table layout as `backend/data/timetable.md`, or reset to the original.

## Notes

- The dashboard has an optional password (`APP_PASSWORD` in `dashboard/.env`).
- The API refuses calls without the `API_KEY`.
- A day counts toward your streak at 70% or more. Partly done counts as half. Skipped habits are ignored.
- If the backend was off when a habit was due, that habit is skipped, not counted against you.
