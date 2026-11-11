-- Habit Coach database (PostgreSQL 14+).
-- Create and load:  createdb habit_coach && psql -d habit_coach -f schema.sql

BEGIN;

CREATE TYPE task_status AS ENUM ('pending', 'prompted', 'checked', 'done', 'partial', 'skipped', 'missed');

-- One row only: the settings of the one person using the app.
CREATE TABLE settings (
    id               SMALLINT PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    timezone         TEXT     NOT NULL DEFAULT 'Asia/Kolkata',
    check_after_min  SMALLINT NOT NULL DEFAULT 5  CHECK (check_after_min BETWEEN 1 AND 120),   -- "did you do it?" after the prompt
    nudge_after_min  SMALLINT NOT NULL DEFAULT 15 CHECK (nudge_after_min BETWEEN 1 AND 240),   -- one more nudge after the check
    miss_after_min   SMALLINT NOT NULL DEFAULT 45 CHECK (miss_after_min BETWEEN 1 AND 480),    -- mark as missed after the check
    streak_pct       SMALLINT NOT NULL DEFAULT 70 CHECK (streak_pct BETWEEN 1 AND 100),        -- a day counts toward the streak at this score
    reminders_on     BOOLEAN  NOT NULL DEFAULT true
);
INSERT INTO settings DEFAULT VALUES;

-- The timetable. Each block is one habit with a start time.
CREATE TABLE routine_blocks (
    id            BIGSERIAL PRIMARY KEY,
    position      SMALLINT NOT NULL DEFAULT 0,
    title         TEXT NOT NULL,
    category      TEXT NOT NULL DEFAULT 'other'
                  CHECK (category IN ('wake','movement','hygiene','meal','study','break','wind_down','sleep','other')),
    start_time    TIME NOT NULL,
    end_time      TIME NOT NULL,
    activities    TEXT NOT NULL DEFAULT '',   -- one step per line
    tip           TEXT NOT NULL DEFAULT '',   -- the friction reducer
    days_of_week  SMALLINT[] NOT NULL DEFAULT '{1,2,3,4,5,6,7}',   -- ISO: 1 is Monday
    active        BOOLEAN NOT NULL DEFAULT true,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- One row for each block on each day: what was sent and how you answered.
CREATE TABLE task_log (
    id            BIGSERIAL PRIMARY KEY,
    block_id      BIGINT NOT NULL REFERENCES routine_blocks(id) ON DELETE CASCADE,
    scheduled_for TIMESTAMPTZ NOT NULL,
    status        task_status NOT NULL DEFAULT 'pending',
    prompted_at   TIMESTAMPTZ,   -- the "time to do it" message
    checked_at    TIMESTAMPTZ,   -- the "did you do it?" message
    nudged_at     TIMESTAMPTZ,   -- the single follow up
    responded_at  TIMESTAMPTZ,
    UNIQUE (block_id, scheduled_for)
);
CREATE INDEX idx_task_open ON task_log (status, scheduled_for) WHERE status IN ('pending', 'prompted', 'checked');
CREATE INDEX idx_task_time ON task_log (scheduled_for);

-- Everything the bot sent or received.
CREATE TABLE message_log (
    id         BIGSERIAL PRIMARY KEY,
    direction  TEXT NOT NULL CHECK (direction IN ('outbound', 'inbound')),
    body       TEXT,
    status     TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMIT;
