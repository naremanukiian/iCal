"""
main.py  —  CalorieAI FastAPI Backend
Run: uvicorn main:app --reload --port 8000
"""

import os
from datetime import date, timezone
from typing import List

import psycopg2.extras
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from analyzer import analyze_food_image
from auth import create_token, get_current_user, hash_password, verify_password
from database import get_db, init_db
from models import (
    AnalyzeResponse,
    FoodItem,
    FoodLogItem,
    HistoryResponse,
    LoginRequest,
    MealSessionOut,
    RegisterRequest,
    TokenResponse,
    UserProfile,
)

load_dotenv()

# ── App ────────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="CalorieAI API",
    version="2.0.0",
    description="AI-powered food calorie tracker using GPT-4o Vision + 60k food database",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # tighten to your domain in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def on_startup():
    init_db()
    print("🚀  CalorieAI API is live at http://localhost:8000")
    print("📖  Swagger docs:  http://localhost:8000/docs")


# ── Utility ────────────────────────────────────────────────────────────────────

def _row_to_dict(row) -> dict:
    """Convert a psycopg2 RealDictRow (or tuple) to a plain dict."""
    if hasattr(row, "keys"):
        return dict(row)
    return row


# ── Health ─────────────────────────────────────────────────────────────────────

@app.get("/", tags=["health"])
def root():
    return {"status": "ok", "service": "CalorieAI", "version": "2.0.0"}


@app.get("/health", tags=["health"])
def health():
    # quick DB ping
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
        return {"status": "healthy", "db": "connected"}
    except Exception as e:
        return JSONResponse(status_code=503, content={"status": "unhealthy", "error": str(e)})


# ── Auth ───────────────────────────────────────────────────────────────────────

@app.post("/register", response_model=TokenResponse, status_code=201, tags=["auth"])
def register(body: RegisterRequest):
    """Create a new user account."""
    with get_db() as conn:
        with conn.cursor() as cur:
            # Check duplicate email
            cur.execute("SELECT id FROM users WHERE email = %s", (body.email,))
            if cur.fetchone():
                raise HTTPException(
                    status_code=409,
                    detail="An account with this email already exists. Please log in.",
                )

            hashed = hash_password(body.password)
            cur.execute(
                """
                INSERT INTO users (email, password_hash, weight, goal)
                VALUES (%s, %s, %s, %s)
                RETURNING id
                """,
                (body.email, hashed, body.weight, body.goal),
            )
            user_id = cur.fetchone()[0]

    token = create_token(user_id, body.email)
    return TokenResponse(token=token, user_id=user_id, email=body.email)


@app.post("/login", response_model=TokenResponse, tags=["auth"])
def login(body: LoginRequest):
    """Authenticate and receive a JWT."""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, email, password_hash FROM users WHERE email = %s",
                (body.email,),
            )
            row = cur.fetchone()

    if not row or not verify_password(body.password, row[2]):
        raise HTTPException(
            status_code=401,
            detail="Incorrect email or password.",
        )

    token = create_token(row[0], row[1])
    return TokenResponse(token=token, user_id=row[0], email=row[1])


@app.get("/me", response_model=UserProfile, tags=["auth"])
def get_me(current_user: dict = Depends(get_current_user)):
    """Return the current user's profile."""
    user_id = int(current_user["sub"])
    with get_db() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT id, email, weight, goal, created_at FROM users WHERE id = %s",
                (user_id,),
            )
            user = cur.fetchone()
    if not user:
        raise HTTPException(404, "User not found.")
    return UserProfile(
        id=user["id"],
        email=user["email"],
        weight=float(user["weight"]) if user["weight"] else None,
        goal=user["goal"],
        created_at=user["created_at"].isoformat(),
    )


# ── Food Analysis ──────────────────────────────────────────────────────────────

ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif", "image/heic"}
MAX_SIZE_MB   = 10


@app.post("/analyze", response_model=AnalyzeResponse, tags=["food"])
async def analyze(
    image: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
):
    """
    Upload a food photo → GPT-4o detects foods → database enriches calories.
    Saves the result to the user's meal history.
    """
    # Validate content type
    ct = (image.content_type or "").lower()
    if ct not in ALLOWED_TYPES:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type '{ct}'. Please upload a JPEG, PNG, or WebP image.",
        )

    # Read file
    image_bytes = await image.read()
    if not image_bytes:
        raise HTTPException(400, "Empty file. Please upload a valid image.")
    if len(image_bytes) > MAX_SIZE_MB * 1024 * 1024:
        raise HTTPException(413, f"Image too large. Maximum allowed size is {MAX_SIZE_MB} MB.")

    # Run AI analysis
    try:
        foods = await analyze_food_image(image_bytes, ct or "image/jpeg")
    except Exception as e:
        raise HTTPException(500, f"Food analysis failed: {str(e)}")

    if not foods:
        raise HTTPException(422, "No food items could be detected in this image. Please try a clearer photo.")

    total_kcal  = sum(f["kcal"] for f in foods)
    food_summary = ", ".join(f["name"] for f in foods)
    user_id     = int(current_user["sub"])

    # Persist to database
    with get_db() as conn:
        with conn.cursor() as cur:
            # Create meal session
            cur.execute(
                """
                INSERT INTO meal_sessions (user_id, total_calories, food_summary)
                VALUES (%s, %s, %s)
                RETURNING id
                """,
                (user_id, total_kcal, food_summary),
            )
            session_id = cur.fetchone()[0]

            # Insert individual food log entries
            for f in foods:
                cur.execute(
                    """
                    INSERT INTO food_logs (user_id, session_id, food_name, calories, serving)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (user_id, session_id, f["name"], f["kcal"], f.get("serving")),
                )

    return AnalyzeResponse(
        foods=[
            FoodItem(name=f["name"], kcal=f["kcal"], serving=f.get("serving"))
            for f in foods
        ],
        total_kcal=total_kcal,
        session_id=session_id,
    )


# ── History ────────────────────────────────────────────────────────────────────

@app.get("/history", response_model=HistoryResponse, tags=["food"])
def get_history(
    limit: int = 20,
    current_user: dict = Depends(get_current_user),
):
    """Return the user's meal history (most recent first)."""
    user_id = int(current_user["sub"])

    with get_db() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # Fetch recent meal sessions
            cur.execute(
                """
                SELECT id, total_calories, food_summary, created_at
                FROM   meal_sessions
                WHERE  user_id = %s
                ORDER  BY created_at DESC
                LIMIT  %s
                """,
                (user_id, limit),
            )
            sessions = [dict(r) for r in cur.fetchall()]

            if not sessions:
                return HistoryResponse(sessions=[], total_kcal_today=0)

            session_ids = [s["id"] for s in sessions]

            # Fetch food log items for those sessions
            cur.execute(
                """
                SELECT id, session_id, food_name, calories, serving, created_at
                FROM   food_logs
                WHERE  session_id = ANY(%s)
                ORDER  BY created_at ASC
                """,
                (session_ids,),
            )
            logs = [dict(r) for r in cur.fetchall()]

            # Calculate today's total calories
            today_str = date.today().isoformat()
            cur.execute(
                """
                SELECT COALESCE(SUM(total_calories), 0)
                FROM   meal_sessions
                WHERE  user_id = %s
                  AND  created_at::date = %s
                """,
                (user_id, today_str),
            )
            total_kcal_today = int(cur.fetchone()["coalesce"])

    # Group logs by session
    logs_by_session: dict = {}
    for log in logs:
        sid = log["session_id"]
        if sid not in logs_by_session:
            logs_by_session[sid] = []
        logs_by_session[sid].append(log)

    session_out: List[MealSessionOut] = []
    for s in sessions:
        items = [
            FoodLogItem(
                id=lg["id"],
                food_name=lg["food_name"],
                calories=lg["calories"],
                serving=lg.get("serving"),
                created_at=lg["created_at"].isoformat(),
            )
            for lg in logs_by_session.get(s["id"], [])
        ]
        session_out.append(
            MealSessionOut(
                id=s["id"],
                total_calories=s["total_calories"],
                food_summary=s["food_summary"],
                created_at=s["created_at"].isoformat(),
                items=items,
            )
        )

    return HistoryResponse(sessions=session_out, total_kcal_today=total_kcal_today)


@app.delete("/history/{session_id}", tags=["food"])
def delete_session(
    session_id: int,
    current_user: dict = Depends(get_current_user),
):
    """Delete a specific meal session from history."""
    user_id = int(current_user["sub"])
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM meal_sessions WHERE id = %s AND user_id = %s RETURNING id",
                (session_id, user_id),
            )
            if not cur.fetchone():
                raise HTTPException(404, "Meal session not found.")
    return {"message": "Deleted successfully."}


# ── Global error handlers ──────────────────────────────────────────────────────

@app.exception_handler(404)
async def not_found_handler(request, exc):
    return JSONResponse(status_code=404, content={"detail": "Endpoint not found."})


@app.exception_handler(500)
async def server_error_handler(request, exc):
    return JSONResponse(
        status_code=500,
        content={"detail": "An unexpected server error occurred. Please try again."},
    )
