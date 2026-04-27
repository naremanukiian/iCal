"""
app/routes/auth.py v13
- /api/register: accepts age, gender, height, activity_level
- Mifflin-St Jeor TDEE with activity multiplier
- Personalized macro targets (protein/carbs/fat)
- /api/login, /api/me, /api/me PATCH
"""
from flask import Blueprint, request, jsonify
import psycopg2.extras
from app.services.database import get_db
from app.services.auth import hash_password, verify_password, create_token, require_auth

auth_bp = Blueprint("auth", __name__)

def _err(msg, status=400): return jsonify({"detail": msg}), status
def _ok(data, status=200):  return jsonify(data), status


# ── Science-based calorie calculator ──────────────────
# Mifflin-St Jeor BMR → multiply by TDEE factor → adjust for goal

ACTIVITY_MULTIPLIERS = {
    "sedentary":   1.2,    # desk job, little/no exercise
    "light":       1.375,  # light exercise 1-3 days/week
    "moderate":    1.55,   # moderate exercise 3-5 days/week
    "active":      1.725,  # hard exercise 6-7 days/week
    "very_active": 1.9,    # very hard exercise + physical job
}

GOAL_ADJUSTMENTS = {
    "lose":     -500,   # 500 kcal deficit → ~0.5kg/week loss
    "maintain":  0,
    "gain":     +300,   # 300 kcal surplus → lean bulk
}

def calculate_tdee(weight_kg, height_cm, age, gender, activity_level, goal):
    """
    Mifflin-St Jeor BMR:
      Male:   10*weight + 6.25*height - 5*age + 5
      Female: 10*weight + 6.25*height - 5*age - 161
    TDEE = BMR * activity_multiplier
    Calorie goal = TDEE + goal_adjustment
    """
    try:
        w = float(weight_kg or 70)
        h = float(height_cm or 170)
        a = int(age or 25)
        g = (gender or "male").lower()
        act = (activity_level or "moderate").lower()
        gl  = (goal or "maintain").lower()

        # BMR
        if g == "female":
            bmr = 10*w + 6.25*h - 5*a - 161
        else:  # male or other
            bmr = 10*w + 6.25*h - 5*a + 5

        bmr = max(bmr, 1000)  # safety floor

        # TDEE
        multiplier = ACTIVITY_MULTIPLIERS.get(act, 1.55)
        tdee = bmr * multiplier

        # Goal adjustment
        adjustment = GOAL_ADJUSTMENTS.get(gl, 0)
        calorie_goal = max(int(round(tdee + adjustment)), 1200)  # never below 1200

        # Macros (science-based)
        # Protein: 1.6-2.2g/kg for active, 1.0g/kg sedentary
        protein_factor = {"lose": 2.0, "gain": 1.8, "maintain": 1.6}.get(gl, 1.6)
        protein_g = max(int(round(w * protein_factor)), 50)
        protein_kcal = protein_g * 4

        # Fat: 25-35% of calories
        fat_pct = 0.28  # 28%
        fat_kcal = calorie_goal * fat_pct
        fat_g = max(int(round(fat_kcal / 9)), 30)

        # Carbs: remaining calories
        carbs_kcal = calorie_goal - protein_kcal - (fat_g * 9)
        carbs_g = max(int(round(carbs_kcal / 4)), 50)

        return calorie_goal, protein_g, carbs_g, fat_g

    except Exception:
        # Safe fallbacks
        return 2000, 150, 200, 65


# ── Register ──────────────────────────────────────────

@auth_bp.post("/register")
def register():
    body = request.get_json(silent=True) or {}
    email    = (body.get("email") or "").strip().lower()
    password = body.get("password") or ""
    username = (body.get("username") or email.split("@")[0]).strip()
    weight   = body.get("weight")
    height   = body.get("height")
    age      = body.get("age")
    gender   = body.get("gender")
    activity = body.get("activity_level", "moderate")
    goal     = body.get("goal", "maintain")

    if not email or "@" not in email:
        return _err("Valid email is required.")
    if len(password) < 6:
        return _err("Password must be at least 6 characters.")

    # Calculate smart calorie + macro goals
    calorie_goal, protein_goal, carbs_goal, fat_goal = calculate_tdee(
        weight, height, age, gender, activity, goal
    )

    # Override if client explicitly sent calorie_goal
    if body.get("calorie_goal"):
        try:
            calorie_goal = max(int(body["calorie_goal"]), 1200)
        except Exception:
            pass

    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT id FROM users WHERE email=%s", (email,))
                if cur.fetchone():
                    return _err("Email already registered.", 409)
                cur.execute(
                    """INSERT INTO users
                       (email,username,password_hash,weight,height,age,gender,
                        activity_level,goal,calorie_goal,protein_goal,carbs_goal,fat_goal)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                    (email, username, hash_password(password),
                     weight, height, age, gender,
                     activity, goal, calorie_goal, protein_goal, carbs_goal, fat_goal)
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
        "protein_goal": protein_goal,
        "carbs_goal":   carbs_goal,
        "fat_goal":     fat_goal,
        "goal":         goal,
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
                """SELECT id,email,username,password_hash,
                          calorie_goal,protein_goal,carbs_goal,fat_goal,goal
                   FROM users WHERE email=%s""",
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
        "protein_goal": row[5] or 150,
        "carbs_goal":   row[6] or 200,
        "fat_goal":     row[7] or 65,
        "goal":         row[8] or "maintain",
    })


# ── Get / Update profile ──────────────────────────────

@auth_bp.get("/me")
@require_auth
def get_me(current_user: dict):
    uid = int(current_user["sub"])
    with get_db() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """SELECT id,email,username,bio,weight,height,age,gender,
                          activity_level,goal,calorie_goal,protein_goal,carbs_goal,fat_goal,
                          created_at FROM users WHERE id=%s""",
                (uid,)
            )
            u = cur.fetchone()
    if not u:
        return _err("User not found.", 404)
    return _ok({
        "id":             u["id"],
        "email":          u["email"],
        "username":       u["username"] or u["email"].split("@")[0],
        "bio":            u["bio"] or "",
        "weight":         float(u["weight"]) if u["weight"] else None,
        "height":         float(u["height"]) if u["height"] else None,
        "age":            u["age"],
        "gender":         u["gender"],
        "activity_level": u["activity_level"] or "moderate",
        "goal":           u["goal"],
        "calorie_goal":   u["calorie_goal"] or 2000,
        "protein_goal":   u["protein_goal"] or 150,
        "carbs_goal":     u["carbs_goal"] or 200,
        "fat_goal":       u["fat_goal"] or 65,
        "created_at":     u["created_at"].isoformat(),
    })


@auth_bp.patch("/me")
@require_auth
def update_me(current_user: dict):
    uid  = int(current_user["sub"])
    body = request.get_json(silent=True) or {}
    allowed = {"username","bio","calorie_goal","weight","height","age",
               "gender","activity_level","goal","protein_goal","carbs_goal","fat_goal"}
    updates = {k: v for k,v in body.items() if k in allowed and v is not None}
    if not updates:
        return _err("No valid fields to update.")
    # Recalculate macros if body metrics changed
    recalc_fields = {"weight","height","age","gender","activity_level","goal"}
    if recalc_fields & set(updates.keys()):
        with get_db() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    "SELECT weight,height,age,gender,activity_level,goal FROM users WHERE id=%s",
                    (uid,)
                )
                u = dict(cur.fetchone())
        merged = {**u, **updates}
        cal, pro, carbs, fat = calculate_tdee(
            merged.get("weight"), merged.get("height"), merged.get("age"),
            merged.get("gender"), merged.get("activity_level"), merged.get("goal")
        )
        if "calorie_goal" not in updates: updates["calorie_goal"] = cal
        if "protein_goal" not in updates: updates["protein_goal"] = pro
        if "carbs_goal"   not in updates: updates["carbs_goal"]   = carbs
        if "fat_goal"     not in updates: updates["fat_goal"]     = fat
    sets   = ", ".join(f"{k}=%s" for k in updates)
    values = list(updates.values()) + [uid]
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(f"UPDATE users SET {sets} WHERE id=%s", values)
    return _ok({"message": "Profile updated.", **updates})
