"""
main.py — iCal v3 Backend
"""
import os
from datetime import date
import psycopg2.extras
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from analyzer import analyze_food_image
from auth import create_token, get_current_user, hash_password, verify_password
from database import get_db, init_db
from models import (
    AnalyzeResponse, FoodItem, FoodLogItem, HistoryResponse,
    LoginRequest, MealSessionOut, RegisterRequest, TokenResponse, UserProfile,
)
from social import router as social_router

load_dotenv()

app = FastAPI(title="iCal API", version="3.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.include_router(social_router)


@app.on_event("startup")
async def startup():
    init_db()
    _init_social_tables()
    print("🚀 iCal v3 API ready!")


def _init_social_tables():
    ddl = """
    CREATE TABLE IF NOT EXISTS follows (
        id           SERIAL PRIMARY KEY,
        follower_id  INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        following_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        created_at   TIMESTAMPTZ DEFAULT NOW(),
        UNIQUE(follower_id, following_id)
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
        items_json      JSONB DEFAULT '[]',
        created_at      TIMESTAMPTZ DEFAULT NOW()
    );
    CREATE TABLE IF NOT EXISTS likes (
        id SERIAL PRIMARY KEY,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        post_id INTEGER NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
        created_at TIMESTAMPTZ DEFAULT NOW(),
        UNIQUE(user_id, post_id)
    );
    CREATE TABLE IF NOT EXISTS saves (
        id SERIAL PRIMARY KEY,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        post_id INTEGER NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
        created_at TIMESTAMPTZ DEFAULT NOW(),
        UNIQUE(user_id, post_id)
    );
    ALTER TABLE posts ADD COLUMN IF NOT EXISTS status VARCHAR(10) DEFAULT 'public';
    ALTER TABLE users ADD COLUMN IF NOT EXISTS username VARCHAR(50);
    ALTER TABLE users ADD COLUMN IF NOT EXISTS bio TEXT DEFAULT '';
    ALTER TABLE users ADD COLUMN IF NOT EXISTS calorie_goal INTEGER DEFAULT 2000;
    UPDATE users SET username = split_part(email,'@',1) WHERE username IS NULL;
    CREATE INDEX IF NOT EXISTS idx_posts_user   ON posts(user_id, created_at DESC);
    CREATE INDEX IF NOT EXISTS idx_posts_status ON posts(status, created_at DESC);
    CREATE INDEX IF NOT EXISTS idx_follows_flwr ON follows(follower_id);
    CREATE INDEX IF NOT EXISTS idx_likes_post   ON likes(post_id);
    CREATE INDEX IF NOT EXISTS idx_users_uname  ON users(username);
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(ddl)
    print("✅ All tables ready.")


# ── Health ──────────────────────────────────────────

@app.get("/")
def root():
    return {"status": "ok", "service": "iCal API", "version": "3.0.0"}

@app.get("/health")
def health():
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
        return {"status": "healthy", "db": "connected"}
    except Exception as e:
        return JSONResponse(status_code=503, content={"status": "unhealthy", "error": str(e)})


# ── Auth ────────────────────────────────────────────

@app.post("/register", response_model=TokenResponse, status_code=201)
def register(body: RegisterRequest):
    username = (body.username or body.email.split("@")[0]).strip()
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM users WHERE email=%s", (body.email,))
            if cur.fetchone():
                raise HTTPException(409, "Email already registered.")
            cur.execute(
                """INSERT INTO users (email,username,password_hash,weight,goal,calorie_goal)
                   VALUES (%s,%s,%s,%s,%s,%s) RETURNING id""",
                (body.email, username, hash_password(body.password),
                 body.weight, body.goal, body.calorie_goal or 2000)
            )
            user_id = cur.fetchone()[0]
    token = create_token(user_id, body.email)
    return TokenResponse(token=token, user_id=user_id, email=body.email,
                         username=username, calorie_goal=body.calorie_goal or 2000)


@app.post("/login", response_model=TokenResponse)
def login(body: LoginRequest):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id,email,username,password_hash,calorie_goal FROM users WHERE email=%s",
                (body.email,)
            )
            row = cur.fetchone()
    if not row or not verify_password(body.password, row[3]):
        raise HTTPException(401, "Incorrect email or password.")
    token = create_token(row[0], row[1])
    return TokenResponse(token=token, user_id=row[0], email=row[1],
                         username=row[2] or row[1].split("@")[0],
                         calorie_goal=row[4] or 2000)


@app.get("/me", response_model=UserProfile)
def get_me(current_user: dict = Depends(get_current_user)):
    uid = int(current_user["sub"])
    with get_db() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT id,email,username,bio,weight,goal,calorie_goal,created_at FROM users WHERE id=%s",
                (uid,)
            )
            u = cur.fetchone()
    if not u:
        raise HTTPException(404, "User not found.")
    return UserProfile(
        id=u["id"], email=u["email"],
        username=u["username"] or u["email"].split("@")[0],
        bio=u["bio"], weight=float(u["weight"]) if u["weight"] else None,
        goal=u["goal"], calorie_goal=u["calorie_goal"] or 2000,
        created_at=u["created_at"].isoformat()
    )


@app.patch("/me")
def update_profile(body: dict, current_user: dict = Depends(get_current_user)):
    uid     = int(current_user["sub"])
    allowed = {"username", "bio", "calorie_goal", "weight", "goal"}
    updates = {k: v for k, v in body.items() if k in allowed and v is not None}
    if not updates:
        raise HTTPException(400, "No valid fields to update.")
    sets   = ", ".join(f"{k}=%s" for k in updates)
    values = list(updates.values()) + [uid]
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(f"UPDATE users SET {sets} WHERE id=%s", values)
    return {"message": "Profile updated."}


# ── Analyze ─────────────────────────────────────────

ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp", "image/heic", "image/gif"}

@app.post("/analyze", response_model=AnalyzeResponse)
async def analyze(
    image:     UploadFile = File(...),
    meal_type: str = "other",
    current_user: dict = Depends(get_current_user),
):
    ct = (image.content_type or "").lower()
    if ct not in ALLOWED_TYPES:
        raise HTTPException(415, "Unsupported file type. Use JPEG, PNG or WebP.")
    image_bytes = await image.read()
    if not image_bytes:
        raise HTTPException(400, "Empty file.")
    if len(image_bytes) > 10 * 1024 * 1024:
        raise HTTPException(413, "Image too large. Max 10MB.")

    try:
        foods = await analyze_food_image(image_bytes, ct or "image/jpeg")
    except Exception as e:
        raise HTTPException(500, f"Analysis failed: {e}")

    if not foods:
        raise HTTPException(422, "No food items detected. Try a clearer photo.")

    total_kcal    = sum(f["kcal"]    for f in foods)
    total_carbs   = round(sum(f["carbs"]   for f in foods), 1)
    total_fat     = round(sum(f["fat"]     for f in foods), 1)
    total_protein = round(sum(f["protein"] for f in foods), 1)
    food_summary  = ", ".join(f["name"] for f in foods)
    uid           = int(current_user["sub"])

    if meal_type not in {"breakfast","lunch","dinner","snacks","other"}:
        meal_type = "other"

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO meal_sessions
                   (user_id,meal_type,total_calories,total_carbs,total_fat,total_protein,food_summary)
                   VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                (uid, meal_type, total_kcal, total_carbs, total_fat, total_protein, food_summary)
            )
            session_id = cur.fetchone()[0]
            for f in foods:
                cur.execute(
                    """INSERT INTO food_logs
                       (user_id,session_id,food_name,calories,carbs,fat,protein,serving)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (uid, session_id, f["name"], f["kcal"],
                     f["carbs"], f["fat"], f["protein"], f.get("serving"))
                )

    return AnalyzeResponse(
        foods=[FoodItem(name=f["name"], kcal=f["kcal"], carbs=f["carbs"],
                        fat=f["fat"], protein=f["protein"], serving=f.get("serving"))
               for f in foods],
        total_kcal=total_kcal, total_carbs=total_carbs,
        total_fat=total_fat, total_protein=total_protein,
        session_id=session_id,
    )


# ── History ─────────────────────────────────────────

@app.get("/history", response_model=HistoryResponse)
def get_history(limit: int = 100, current_user: dict = Depends(get_current_user)):
    uid = int(current_user["sub"])
    with get_db() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """SELECT id,meal_type,total_calories,total_carbs,total_fat,total_protein,
                          food_summary,created_at
                   FROM meal_sessions WHERE user_id=%s ORDER BY created_at DESC LIMIT %s""",
                (uid, limit)
            )
            sessions = [dict(r) for r in cur.fetchall()]

            if not sessions:
                return HistoryResponse(sessions=[], total_kcal_today=0,
                                       total_carbs_today=0.0, total_fat_today=0.0,
                                       total_protein_today=0.0)

            sids = [s["id"] for s in sessions]
            cur.execute(
                """SELECT id,session_id,food_name,calories,carbs,fat,protein,serving,created_at
                   FROM food_logs WHERE session_id=ANY(%s) ORDER BY created_at ASC""",
                (sids,)
            )
            logs = [dict(r) for r in cur.fetchall()]

            today = date.today().isoformat()
            cur.execute(
                """SELECT COALESCE(SUM(total_calories),0) AS kcal_sum,
                          COALESCE(SUM(total_carbs),0)    AS carbs_sum,
                          COALESCE(SUM(total_fat),0)      AS fat_sum,
                          COALESCE(SUM(total_protein),0)  AS protein_sum
                   FROM meal_sessions WHERE user_id=%s AND created_at::date=%s""",
                (uid, today)
            )
            tr = cur.fetchone()
            total_kcal_today    = int(tr["kcal_sum"])    if tr else 0
            total_carbs_today   = float(tr["carbs_sum"]) if tr else 0.0
            total_fat_today     = float(tr["fat_sum"])   if tr else 0.0
            total_protein_today = float(tr["protein_sum"]) if tr else 0.0

    logs_by_session = {}
    for log in logs:
        logs_by_session.setdefault(log["session_id"], []).append(log)

    out = []
    for s in sessions:
        items = [
            FoodLogItem(id=lg["id"], food_name=lg["food_name"], calories=lg["calories"],
                        carbs=float(lg["carbs"]), fat=float(lg["fat"]), protein=float(lg["protein"]),
                        serving=lg.get("serving"), created_at=lg["created_at"].isoformat())
            for lg in logs_by_session.get(s["id"], [])
        ]
        out.append(MealSessionOut(
            id=s["id"], meal_type=s["meal_type"] or "other",
            total_calories=s["total_calories"],
            total_carbs=float(s["total_carbs"]), total_fat=float(s["total_fat"]),
            total_protein=float(s["total_protein"]), food_summary=s["food_summary"],
            created_at=s["created_at"].isoformat(), items=items,
        ))

    return HistoryResponse(sessions=out, total_kcal_today=total_kcal_today,
                           total_carbs_today=total_carbs_today, total_fat_today=total_fat_today,
                           total_protein_today=total_protein_today)


@app.delete("/history/{session_id}")
def delete_session(session_id: int, current_user: dict = Depends(get_current_user)):
    uid = int(current_user["sub"])
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM meal_sessions WHERE id=%s AND user_id=%s RETURNING id",
                (session_id, uid)
            )
            if not cur.fetchone():
                raise HTTPException(404, "Session not found.")
    return {"message": "Deleted."}


# ── AI Meal Suggestion ───────────────────────────────

@app.post("/suggest")
async def suggest_meal(body: dict, current_user: dict = Depends(get_current_user)):
    import httpx
    prompt  = body.get("prompt", "")
    api_key = os.getenv("OPENAI_API_KEY", "")
    if not prompt:
        raise HTTPException(400, "Prompt is required.")
    if not api_key:
        raise HTTPException(500, "OpenAI API key not configured.")
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"model": "gpt-4o", "max_tokens": 1000,
                  "messages": [{"role": "user", "content": prompt}]},
        )
    if resp.status_code != 200:
        raise HTTPException(502, f"OpenAI error: {resp.text[:200]}")
    result = resp.json()["choices"][0]["message"]["content"]
    return {"result": result}


# ── Error handlers ───────────────────────────────────

@app.exception_handler(404)
async def not_found(req, exc):
    return JSONResponse(status_code=404, content={"detail": "Not found."})

@app.exception_handler(500)
async def server_error(req, exc):
    return JSONResponse(status_code=500, content={"detail": "Server error."})
