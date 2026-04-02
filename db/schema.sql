-- CalorieAI Database Schema
-- Run this manually OR let the backend auto-create tables on startup.
-- Compatible with PostgreSQL 14+ and Neon.tech

CREATE TABLE IF NOT EXISTS users (
    id            SERIAL PRIMARY KEY,
    email         VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    weight        NUMERIC(5,2),
    goal          VARCHAR(20) CHECK (goal IN ('lose','maintain','gain')),
    created_at    TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS meal_sessions (
    id             SERIAL PRIMARY KEY,
    user_id        INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    total_calories INTEGER NOT NULL,
    food_summary   TEXT,
    created_at     TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS food_logs (
    id          SERIAL PRIMARY KEY,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    session_id  INTEGER REFERENCES meal_sessions(id) ON DELETE CASCADE,
    food_name   VARCHAR(255) NOT NULL,
    calories    INTEGER NOT NULL,
    serving     VARCHAR(100),
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_meal_sessions_user ON meal_sessions(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_food_logs_session  ON food_logs(session_id);
CREATE INDEX IF NOT EXISTS idx_food_logs_user     ON food_logs(user_id, created_at DESC);
