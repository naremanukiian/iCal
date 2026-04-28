"""
app/services/database.py — v13
Adds age, gender, height, activity_level for Mifflin-St Jeor TDEE
Adds protein_goal, carbs_goal, fat_goal for personalized macros
"""
import os
import psycopg2
import psycopg2.extras
from psycopg2 import pool
from contextlib import contextmanager

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:password@localhost:5432/ical")

def _parse(url):
    url = url.replace("postgresql://","").replace("postgres://","")
    sslmode = None
    if "?" in url:
        url, qs = url.split("?",1)
        for p in qs.split("&"):
            if p.startswith("sslmode="): sslmode = p.split("=",1)[1]
    user_pass, rest = url.split("@",1)
    host_port, dbname = rest.rsplit("/",1)
    user, password = user_pass.split(":",1) if ":" in user_pass else (user_pass,"")
    host, port = host_port.rsplit(":",1) if ":" in host_port else (host_port,"5432")
    kw = {"dbname":dbname,"user":user,"password":password,"host":host,"port":int(port),"connect_timeout":10}
    if sslmode: kw["sslmode"] = sslmode
    elif "neon.tech" in host: kw["sslmode"] = "require"
    return kw

_KW = _parse(DATABASE_URL)
_pool = None

def _get_pool():
    global _pool
    if _pool is None or _pool.closed:
        _pool = pool.ThreadedConnectionPool(0,20,**_KW)
    return _pool

@contextmanager
def get_db():
    global _pool
    conn = _get_pool().getconn()
    if conn.closed:
        try: _get_pool().putconn(conn, close=True)
        except Exception: pass
        _pool = None
        conn = _get_pool().getconn()
    try:
        yield conn
        conn.commit()
    except Exception:
        try: conn.rollback()
        except Exception: pass
        raise
    finally:
        try: _get_pool().putconn(conn)
        except Exception: pass

def init_db():
    ddl = """
    CREATE TABLE IF NOT EXISTS users (
        id            SERIAL PRIMARY KEY,
        email         VARCHAR(255) UNIQUE NOT NULL,
        username      VARCHAR(50),
        password_hash VARCHAR(255) NOT NULL,
        bio           TEXT DEFAULT '',
        weight        NUMERIC(5,2),
        height        NUMERIC(5,1),
        age           INTEGER,
        gender        VARCHAR(10),
        activity_level VARCHAR(20) DEFAULT 'moderate',
        goal          VARCHAR(20),
        calorie_goal  INTEGER DEFAULT 2000,
        protein_goal  INTEGER DEFAULT 150,
        carbs_goal    INTEGER DEFAULT 200,
        fat_goal      INTEGER DEFAULT 65,
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
        photo_url      TEXT,
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
        status          VARCHAR(10) DEFAULT 'public',
        meal_type       VARCHAR(20) DEFAULT 'other',
        total_calories  INTEGER DEFAULT 0,
        total_carbs     NUMERIC(8,2) DEFAULT 0,
        total_fat       NUMERIC(8,2) DEFAULT 0,
        total_protein   NUMERIC(8,2) DEFAULT 0,
        food_summary    TEXT,
        photo_url       TEXT,
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
    ALTER TABLE users ADD COLUMN IF NOT EXISTS username VARCHAR(50);
    ALTER TABLE users ADD COLUMN IF NOT EXISTS bio TEXT DEFAULT '';
    ALTER TABLE users ADD COLUMN IF NOT EXISTS calorie_goal INTEGER DEFAULT 2000;
    ALTER TABLE users ADD COLUMN IF NOT EXISTS height NUMERIC(5,1);
    ALTER TABLE users ADD COLUMN IF NOT EXISTS age INTEGER;
    ALTER TABLE users ADD COLUMN IF NOT EXISTS gender VARCHAR(10);
    ALTER TABLE users ADD COLUMN IF NOT EXISTS activity_level VARCHAR(20) DEFAULT 'moderate';
    ALTER TABLE users ADD COLUMN IF NOT EXISTS protein_goal INTEGER DEFAULT 150;
    ALTER TABLE users ADD COLUMN IF NOT EXISTS carbs_goal INTEGER DEFAULT 200;
    ALTER TABLE users ADD COLUMN IF NOT EXISTS fat_goal INTEGER DEFAULT 65;
    ALTER TABLE posts ADD COLUMN IF NOT EXISTS status VARCHAR(10) DEFAULT 'public';
    ALTER TABLE posts ADD COLUMN IF NOT EXISTS photo_url TEXT;
    ALTER TABLE meal_sessions ADD COLUMN IF NOT EXISTS photo_url TEXT;
    UPDATE users SET username = split_part(email,'@',1) WHERE username IS NULL;
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
    print("Database tables ready (v13).")
