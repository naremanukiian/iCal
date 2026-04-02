"""
database.py
PostgreSQL connection pool with full SSL support (works locally and on Neon.tech).
"""

import os
import psycopg2
import psycopg2.extras
from psycopg2 import pool
from contextlib import contextmanager
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:password@localhost:5432/calorieai")


def _build_conn_kwargs(url: str) -> dict:
    """
    Parse a PostgreSQL connection URL into kwargs for psycopg2.
    Handles:  postgresql://user:pass@host:port/dbname?sslmode=require
    """
    url = url.replace("postgresql://", "").replace("postgres://", "")

    # Split query string
    sslmode = None
    if "?" in url:
        url, query = url.split("?", 1)
        for part in query.split("&"):
            if part.startswith("sslmode="):
                sslmode = part.split("=", 1)[1]

    user_pass, rest = url.split("@", 1)
    host_port, dbname = rest.rsplit("/", 1)

    user, password = (user_pass.split(":", 1) if ":" in user_pass else (user_pass, ""))
    host, port = (host_port.rsplit(":", 1) if ":" in host_port else (host_port, "5432"))

    kwargs = {
        "dbname": dbname,
        "user": user,
        "password": password,
        "host": host,
        "port": int(port),
    }
    if sslmode:
        kwargs["sslmode"] = sslmode
    # Neon requires SSL — auto-detect by hostname
    if "neon.tech" in host and not sslmode:
        kwargs["sslmode"] = "require"

    return kwargs


_CONN_KWARGS = _build_conn_kwargs(DATABASE_URL)
_pool: pool.ThreadedConnectionPool | None = None


def _get_pool() -> pool.ThreadedConnectionPool:
    global _pool
    if _pool is None or _pool.closed:
        _pool = pool.ThreadedConnectionPool(1, 10, **_CONN_KWARGS)
    return _pool


@contextmanager
def get_db():
    """Yield a psycopg2 connection; commit on success, rollback on error."""
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
    """Create all tables if they don't exist (safe to run multiple times)."""
    ddl = """
        CREATE TABLE IF NOT EXISTS users (
            id            SERIAL PRIMARY KEY,
            email         VARCHAR(255) UNIQUE NOT NULL,
            password_hash VARCHAR(255) NOT NULL,
            weight        NUMERIC(5,2),
            goal          VARCHAR(20) CHECK (goal IN ('lose','maintain','gain')),
            created_at    TIMESTAMPTZ DEFAULT NOW()
        );

        CREATE TABLE IF NOT EXISTS meal_sessions (
            id               SERIAL PRIMARY KEY,
            user_id          INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            total_calories   INTEGER NOT NULL,
            food_summary     TEXT,
            created_at       TIMESTAMPTZ DEFAULT NOW()
        );

        CREATE TABLE IF NOT EXISTS food_logs (
            id             SERIAL PRIMARY KEY,
            user_id        INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            session_id     INTEGER REFERENCES meal_sessions(id) ON DELETE CASCADE,
            food_name      VARCHAR(255) NOT NULL,
            calories       INTEGER NOT NULL,
            serving        VARCHAR(100),
            created_at     TIMESTAMPTZ DEFAULT NOW()
        );

        CREATE INDEX IF NOT EXISTS idx_meal_sessions_user ON meal_sessions(user_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_food_logs_session  ON food_logs(session_id);
        CREATE INDEX IF NOT EXISTS idx_food_logs_user     ON food_logs(user_id, created_at DESC);
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(ddl)
    print("✅  Database tables ready.")
