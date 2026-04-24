"""
app/services/database.py — PostgreSQL connection pool
Compatible with Neon.tech SSL and standard PostgreSQL.
"""
import os
import psycopg2
import psycopg2.extras
from psycopg2 import pool
from contextlib import contextmanager

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:password@localhost:5432/ical")


def _parse(url: str) -> dict:
    url = url.replace("postgresql://", "").replace("postgres://", "")
    sslmode = None
    if "?" in url:
        url, qs = url.split("?", 1)
        for part in qs.split("&"):
            if part.startswith("sslmode="):
                sslmode = part.split("=", 1)[1]
    user_pass, rest   = url.split("@", 1)
    host_port, dbname = rest.rsplit("/", 1)
    user, password = user_pass.split(":", 1) if ":" in user_pass else (user_pass, "")
    host, port     = host_port.rsplit(":", 1) if ":" in host_port else (host_port, "5432")
    kw = {
        "dbname":   dbname,
        "user":     user,
        "password": password,
        "host":     host,
        "port":     int(port),
        "connect_timeout": 10,
    }
    if sslmode:
        kw["sslmode"] = sslmode
    elif "neon.tech" in host:
        kw["sslmode"] = "require"
    return kw


_KW   = _parse(DATABASE_URL)
_pool = None


def _get_pool():
    global _pool
    if _pool is None or _pool.closed:
        _pool = pool.ThreadedConnectionPool(2, 20, **_KW)
    return _pool


@contextmanager
def get_db():
    """Context manager — yields a connection, commits or rolls back."""
    conn = _get_pool().getconn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        _get_pool().putconn(conn)


def init_db():
    """Create tables if they don't exist. Safe to run on every startup."""
    ddl = """
    CREATE TABLE IF NOT EXISTS users (
        id            SERIAL PRIMARY KEY,
        email         VARCHAR(255) UNIQUE NOT NULL,
        username      VARCHAR(50),
        password_hash VARCHAR(255) NOT NULL,
        bio           TEXT DEFAULT '',
        weight        NUMERIC(5,2),
        goal          VARCHAR(20) CHECK (goal IN ('lose','maintain','gain')),
        calorie_goal  INTEGER DEFAULT 2000,
        created_at    TIMESTAMPTZ DEFAULT NOW()
    );

    CREATE TABLE IF NOT EXISTS meal_sessions (
        id             SERIAL PRIMARY KEY,
        user_id        INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        meal_type      VARCHAR(20) DEFAULT 'other',
        total_calories INTEGER NOT NULL DEFAULT 0,
        total_carbs    NUMERIC(8,2) NOT NULL DEFAULT 0,
        total_fat      NUMERIC(8,2) NOT NULL DEFAULT 0,
        total_protein  NUMERIC(8,2) NOT NULL DEFAULT 0,
        food_summary   TEXT,
        created_at     TIMESTAMPTZ DEFAULT NOW()
    );

    CREATE TABLE IF NOT EXISTS food_logs (
        id          SERIAL PRIMARY KEY,
        user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        session_id  INTEGER REFERENCES meal_sessions(id) ON DELETE CASCADE,
        food_name   VARCHAR(255) NOT NULL,
        calories    INTEGER NOT NULL DEFAULT 0,
        carbs       NUMERIC(8,2) NOT NULL DEFAULT 0,
        fat         NUMERIC(8,2) NOT NULL DEFAULT 0,
        protein     NUMERIC(8,2) NOT NULL DEFAULT 0,
        serving     VARCHAR(100),
        created_at  TIMESTAMPTZ DEFAULT NOW()
    );

    CREATE TABLE IF NOT EXISTS posts (
        id              SERIAL PRIMARY KEY,
        user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        session_id      INTEGER REFERENCES meal_sessions(id) ON DELETE SET NULL,
        caption         TEXT DEFAULT '',
        status          VARCHAR(10) DEFAULT 'public' CHECK (status IN ('public','private')),
        meal_type       VARCHAR(20) DEFAULT 'other',
        total_calories  INTEGER DEFAULT 0,
        total_carbs     NUMERIC(8,2) DEFAULT 0,
        total_fat       NUMERIC(8,2) DEFAULT 0,
        total_protein   NUMERIC(8,2) DEFAULT 0,
        food_summary    TEXT,
        items_json      JSONB DEFAULT '[]',
        created_at      TIMESTAMPTZ DEFAULT NOW()
    );

    CREATE TABLE IF NOT EXISTS follows (
        id           SERIAL PRIMARY KEY,
        follower_id  INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        following_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        created_at   TIMESTAMPTZ DEFAULT NOW(),
        UNIQUE(follower_id, following_id)
    );

    CREATE TABLE IF NOT EXISTS likes (
        id         SERIAL PRIMARY KEY,
        user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        post_id    INTEGER NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
        created_at TIMESTAMPTZ DEFAULT NOW(),
        UNIQUE(user_id, post_id)
    );

    CREATE TABLE IF NOT EXISTS saves (
        id         SERIAL PRIMARY KEY,
        user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        post_id    INTEGER NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
        created_at TIMESTAMPTZ DEFAULT NOW(),
        UNIQUE(user_id, post_id)
    );

    -- Safe migrations for existing databases
    ALTER TABLE users ADD COLUMN IF NOT EXISTS username VARCHAR(50);
    ALTER TABLE users ADD COLUMN IF NOT EXISTS bio TEXT DEFAULT '';
    ALTER TABLE users ADD COLUMN IF NOT EXISTS calorie_goal INTEGER DEFAULT 2000;
    ALTER TABLE posts ADD COLUMN IF NOT EXISTS status VARCHAR(10) DEFAULT 'public';
    ALTER TABLE meal_sessions ADD COLUMN IF NOT EXISTS photo_url TEXT;
    ALTER TABLE posts ADD COLUMN IF NOT EXISTS photo_url TEXT;
    UPDATE users SET username = split_part(email,'@',1) WHERE username IS NULL;

    -- Indexes
    CREATE INDEX IF NOT EXISTS idx_ms_user      ON meal_sessions(user_id, created_at DESC);
    CREATE INDEX IF NOT EXISTS idx_fl_session   ON food_logs(session_id);
    CREATE INDEX IF NOT EXISTS idx_posts_user   ON posts(user_id, created_at DESC);
    CREATE INDEX IF NOT EXISTS idx_posts_status ON posts(status, created_at DESC);
    CREATE INDEX IF NOT EXISTS idx_follows_flwr ON follows(follower_id);
    CREATE INDEX IF NOT EXISTS idx_likes_post   ON likes(post_id);
    CREATE INDEX IF NOT EXISTS idx_users_uname  ON users(username);
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(ddl)
    print("✅  Database tables ready.")
