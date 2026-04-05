"""
main.py — iCal FastAPI Backend
Run: uvicorn main:app --reload --port 8000
"""

import os
from datetime import date
from typing import List

import psycopg2.extras
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from analyzer import analyze_food_image
from auth import create_token, get_current_user, hash_password, verify_password
from database import get_db, init_db
from models import (
    AnalyzeResponse, FoodItem, FoodLogItem,
    HistoryResponse, LoginRequest, MealSessionOut,
    RegisterRequest, TokenResponse, UserProfile,
)

load_dotenv()

app = FastAPI(title="iCal API", version="1.0.0",
              description="AI food calorie & macro tracker")

app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


@app.on_event("startup")
async def startup():
    init_db()
    print("🚀  iCal API is live at http://localhost:8000")
    print("📖  Docs: http://localhost:8000/docs")


# ── Health ─────────────────────────────────────────

@app.get("/")
def root():
    return {"status": "ok", "service": "iCal API", "version": "1.0.0"}

@app.get("/health")
def health():
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
        return {"status": "healthy", "db": "connected"}
    except Exception as e:
        return JSONResponse(status_code=503, content={"status": "unhealthy", "error": str(e)})


# ── Auth ───────────────────────────────────────────

@app.post("/register", response_model=TokenResponse, status_code=201)
def register(body: RegisterRequest):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM users WHERE email = %s", (body.email,))
            if cur.fetchone():
                raise HTTPException(409, "An account with this email already exists.")
            hashed = hash_password(body.password)
            cur.execute(
                "INSERT INTO users (email,password_hash,weight,goal,calorie_goal) VALUES (%s,%s,%s,%s,%s) RETURNING id",
                (body.email, hashed, body.weight, body.goal, body.calorie_goal or 2000)
            )
            user_id = cur.fetchone()[0]
    token = create_token(user_id, body.email)
    return TokenResponse(token=token, user_id=user_id, email=body.email, calorie_goal=body.calorie_goal or 2000)


@app.post("/login", response_model=TokenResponse)
def login(body: LoginRequest):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id,email,password_hash,calorie_goal FROM users WHERE email = %s", (body.email,))
            row = cur.fetchone()
    if not row or not verify_password(body.password, row[2]):
        raise HTTPException(401, "Incorrect email or password.")
    token = create_token(row[0], row[1])
    return TokenResponse(token=token, user_id=row[0], email=row[1], calorie_goal=row[3] or 2000)


@app.get("/me", response_model=UserProfile)
def get_me(current_user: dict = Depends(get_current_user)):
    user_id = int(current_user["sub"])
    with get_db() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT id,email,weight,goal,calorie_goal,created_at FROM users WHERE id=%s", (user_id,))
            u = cur.fetchone()
    if not u:
        raise HTTPException(404, "User not found.")
    return UserProfile(
        id=u["id"], email=u["email"],
        weight=float(u["weight"]) if u["weight"] else None,
        goal=u["goal"], calorie_goal=u["calorie_goal"] or 2000,
        created_at=u["created_at"].isoformat()
    )


# ── Analyze ────────────────────────────────────────

ALLOWED = {"image/jpeg", "image/png", "image/webp", "image/heic", "image/gif"}

@app.post("/analyze", response_model=AnalyzeResponse)
async def analyze(
    image:     UploadFile = File(...),
    meal_type: str = "other",
    current_user: dict = Depends(get_current_user),
):
    ct = (image.content_type or "").lower()
    if ct not in ALLOWED:
        raise HTTPException(415, f"Unsupported file type. Please upload JPEG, PNG or WebP.")

    image_bytes = await image.read()
    if not image_bytes:
        raise HTTPException(400, "Empty file.")
    if len(image_bytes) > 10 * 1024 * 1024:
        raise HTTPException(413, "Image too large. Max 10 MB.")

    try:
        foods = await analyze_food_image(image_bytes, ct or "image/jpeg")
    except Exception as e:
        raise HTTPException(500, f"Analysis failed: {str(e)}")

    if not foods:
        raise HTTPException(422, "No food items detected. Please try a clearer photo.")

    total_kcal    = sum(f["kcal"]    for f in foods)
    total_carbs   = round(sum(f["carbs"]   for f in foods), 1)
    total_fat     = round(sum(f["fat"]     for f in foods), 1)
    total_protein = round(sum(f["protein"] for f in foods), 1)
    food_summary  = ", ".join(f["name"] for f in foods)
    user_id       = int(current_user["sub"])

    valid_types = {"breakfast", "lunch", "dinner", "snacks", "other"}
    if meal_type not in valid_types:
        meal_type = "other"

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO meal_sessions
                   (user_id,meal_type,total_calories,total_carbs,total_fat,total_protein,food_summary)
                   VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                (user_id, meal_type, total_kcal, total_carbs, total_fat, total_protein, food_summary)
            )
            session_id = cur.fetchone()[0]
            for f in foods:
                cur.execute(
                    """INSERT INTO food_logs
                       (user_id,session_id,food_name,calories,carbs,fat,protein,serving)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (user_id, session_id, f["name"], f["kcal"],
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


# ── History ────────────────────────────────────────

@app.get("/history", response_model=HistoryResponse)
def get_history(limit: int = 30, current_user: dict = Depends(get_current_user)):
    user_id = int(current_user["sub"])

    with get_db() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """SELECT id,meal_type,total_calories,total_carbs,total_fat,total_protein,food_summary,created_at
                   FROM meal_sessions WHERE user_id=%s ORDER BY created_at DESC LIMIT %s""",
                (user_id, limit)
            )
            sessions = [dict(r) for r in cur.fetchall()]

            if not sessions:
                return HistoryResponse(
                    sessions=[],
                    total_kcal_today=0,
                    total_carbs_today=0.0,
                    total_fat_today=0.0,
                    total_protein_today=0.0
                )

            sids = [s["id"] for s in sessions]
            cur.execute(
                """SELECT id,session_id,food_name,calories,carbs,fat,protein,serving,created_at
                   FROM food_logs WHERE session_id=ANY(%s) ORDER BY created_at ASC""",
                (sids,)
            )
            logs = [dict(r) for r in cur.fetchall()]

            # Today's totals using individual column aliases
            today = date.today().isoformat()
            cur.execute(
                """SELECT
                     COALESCE(SUM(total_calories),0) AS kcal_sum,
                     COALESCE(SUM(total_carbs),0)    AS carbs_sum,
                     COALESCE(SUM(total_fat),0)      AS fat_sum,
                     COALESCE(SUM(total_protein),0)  AS protein_sum
                   FROM meal_sessions
                   WHERE user_id=%s AND created_at::date=%s""",
                (user_id, today)
            )
            totals_row = cur.fetchone()
            if totals_row:
                total_kcal_today    = int(totals_row["kcal_sum"])
                total_carbs_today   = float(totals_row["carbs_sum"])
                total_fat_today     = float(totals_row["fat_sum"])
                total_protein_today = float(totals_row["protein_sum"])
            else:
                total_kcal_today    = 0
                total_carbs_today   = 0.0
                total_fat_today     = 0.0
                total_protein_today = 0.0

    logs_by_session = {}
    for log in logs:
        sid = log["session_id"]
        logs_by_session.setdefault(sid, []).append(log)

    out = []
    for s in sessions:
        items = [
            FoodLogItem(
                id=lg["id"],
                food_name=lg["food_name"],
                calories=lg["calories"],
                carbs=float(lg["carbs"]),
                fat=float(lg["fat"]),
                protein=float(lg["protein"]),
                serving=lg.get("serving"),
                created_at=lg["created_at"].isoformat()
            )
            for lg in logs_by_session.get(s["id"], [])
        ]
        out.append(MealSessionOut(
            id=s["id"],
            meal_type=s["meal_type"] or "other",
            total_calories=s["total_calories"],
            total_carbs=float(s["total_carbs"]),
            total_fat=float(s["total_fat"]),
            total_protein=float(s["total_protein"]),
            food_summary=s["food_summary"],
            created_at=s["created_at"].isoformat(),
            items=items,
        ))

    return HistoryResponse(
        sessions=out,
        total_kcal_today=total_kcal_today,
        total_carbs_today=total_carbs_today,
        total_fat_today=total_fat_today,
        total_protein_today=total_protein_today
    )


@app.delete("/history/{session_id}")
def delete_session(session_id: int, current_user: dict = Depends(get_current_user)):
    user_id = int(current_user["sub"])
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM meal_sessions WHERE id=%s AND user_id=%s RETURNING id",
                (session_id, user_id)
            )
            if not cur.fetchone():
                raise HTTPException(404, "Session not found.")
    return {"message": "Deleted."}


# ── Error handlers ──────────────────────────────────

@app.exception_handler(404)
async def not_found(req, exc):
    return JSONResponse(status_code=404, content={"detail": "Not found."})

@app.exception_handler(500)
async def server_error(req, exc):
    return JSONResponse(status_code=500, content={"detail": "Server error. Please try again."})
