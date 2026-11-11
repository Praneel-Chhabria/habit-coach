import asyncio
import os
from contextlib import asynccontextmanager

import asyncpg
from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI

import scheduler
import telegram_bot
import timetable
from api_routes import router


@asynccontextmanager
async def lifespan(app):
    app.state.db = await asyncpg.create_pool(os.environ["DATABASE_URL"])
    loaded = await timetable.seed_if_empty(app.state.db)
    if loaded:
        print("Loaded %d habits from data/timetable.md" % loaded)
    tasks = [asyncio.create_task(scheduler.run_forever(app.state.db))]
    if telegram_bot.polling_enabled():
        tasks.append(asyncio.create_task(telegram_bot.poll_forever(app.state.db)))
    yield
    for t in tasks:
        t.cancel()
    await app.state.db.close()


app = FastAPI(title="Habit Coach", lifespan=lifespan)
app.include_router(router)
