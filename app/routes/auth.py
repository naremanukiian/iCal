"""
app/routes/auth.py — Authentication routes
POST /api/register
POST /api/login
GET  /api/me
PATCH /api/me
"""
from flask import Blueprint, request, jsonify
import psycopg2.extras

from app.services.database import get_db
from app.services.auth     import (
    hash_password, verify_password, create_token, require_auth
)

auth_bp = Blueprint("auth", __name__)


# ── Helpers ───────────────────────────────────────────

def _err(msg: str, status: int = 400):
    return jsonify({"detail": msg}), status

def _ok(data: dict, status: int = 200):
    return jsonify(data), status


# ── Register ──────────────────────────────────────────

@auth_bp.post("/register")
def register():
    body = request.get_json(silent=True) or {}
    email    = (body.get("email") or "").strip().lower()
    password = body.get("password") or ""
    username = (body.get("username") or email.split("@")[0]).strip()
    weight   = body.get("weight")
    goal     = body.get("goal")
    calorie_goal = int(body.get("calorie_goal") or 2000)

    if not email or "@" not in email:
        return _err("Valid email is required.")
    if len(password) < 6:
        return _err("Password must be at least 6 characters.")
    if goal and goal not in ("lose", "maintain", "gain"):
        return _err("Goal must be lose, maintain, or gain.")

    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT id FROM users WHERE email=%s", (email,))
                if cur.fetchone():
                    return _err("Email already registered.", 409)
                cur.execute(
                    """INSERT INTO users
                       (email,username,password_hash,weight,goal,calorie_goal)
                       VALUES (%s,%s,%s,%s,%s,%s) RETURNING id""",
                    (email, username, hash_password(password), weight, goal, calorie_goal)
                )
                user_id = cur.fetchone()[0]
    except Exception as e:
        return _err(f"Registration failed: {e}", 500)

    token = create_token(user_id, email)
    return _ok({
        "token":        token,
        "user_id":      user_id,
        "email":        email,
        "username":     username,
        "calorie_goal": calorie_goal,
    }, 201)


# ── Login ─────────────────────────────────────────────

@auth_bp.post("/login")
def login():
    body     = request.get_json(silent=True) or {}
    email    = (body.get("email") or "").strip().lower()
    password = body.get("password") or ""

    if not email or not password:
        return _err("Email and password are required.")

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id,email,username,password_hash,calorie_goal FROM users WHERE email=%s",
                (email,)
            )
            row = cur.fetchone()

    if not row or not verify_password(password, row[3]):
        return _err("Incorrect email or password.", 401)

    token = create_token(row[0], row[1])
    return _ok({
        "token":        token,
        "user_id":      row[0],
        "email":        row[1],
        "username":     row[2] or row[1].split("@")[0],
        "calorie_goal": row[4] or 2000,
    })


# ── Get profile ───────────────────────────────────────

@auth_bp.get("/me")
@require_auth
def get_me(current_user: dict):
    uid = int(current_user["sub"])
    with get_db() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT id,email,username,bio,weight,goal,calorie_goal,created_at FROM users WHERE id=%s",
                (uid,)
            )
            u = cur.fetchone()
    if not u:
        return _err("User not found.", 404)
    return _ok({
        "id":           u["id"],
        "email":        u["email"],
        "username":     u["username"] or u["email"].split("@")[0],
        "bio":          u["bio"] or "",
        "weight":       float(u["weight"]) if u["weight"] else None,
        "goal":         u["goal"],
        "calorie_goal": u["calorie_goal"] or 2000,
        "created_at":   u["created_at"].isoformat(),
    })


# ── Update profile ────────────────────────────────────

@auth_bp.patch("/me")
@require_auth
def update_me(current_user: dict):
    uid     = int(current_user["sub"])
    body    = request.get_json(silent=True) or {}
    allowed = {"username", "bio", "calorie_goal", "weight", "goal"}
    updates = {k: v for k, v in body.items() if k in allowed and v is not None}
    if not updates:
        return _err("No valid fields to update.")
    sets   = ", ".join(f"{k}=%s" for k in updates)
    values = list(updates.values()) + [uid]
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(f"UPDATE users SET {sets} WHERE id=%s", values)
    return _ok({"message": "Profile updated."})
