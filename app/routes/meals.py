"""
app/routes/meals.py — Meal tracking routes
POST   /api/analyze
GET    /api/history
DELETE /api/history/<session_id>
POST   /api/suggest
"""
import asyncio
import os
from datetime import date

import psycopg2.extras
from flask import Blueprint, request, jsonify

from app.services.database import get_db
from app.services.auth     import require_auth
from app.services.analyzer import analyze_food_image

meals_bp = Blueprint("meals", __name__)

ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp", "image/heic", "image/gif"}


def _err(msg, status=400): return jsonify({"detail": msg}), status
def _ok(data, status=200): return jsonify(data), status


# ── Analyze ───────────────────────────────────────────

@meals_bp.post("/analyze")
@require_auth
def analyze(current_user: dict):
    if "image" not in request.files:
        return _err("No image uploaded.")

    file      = request.files["image"]
    meal_type = request.form.get("meal_type") or request.args.get("meal_type", "other")
    ct        = (file.content_type or "").lower()

    if ct not in ALLOWED_TYPES:
        return _err("Unsupported file type. Use JPEG, PNG or WebP.", 415)

    image_bytes = file.read()
    if not image_bytes:
        return _err("Empty file.", 400)
    if len(image_bytes) > 10 * 1024 * 1024:
        return _err("Image too large. Max 10 MB.", 413)

    if meal_type not in {"breakfast","lunch","dinner","snacks","other"}:
        meal_type = "other"

    # Run async analyzer in sync Flask context
    try:
        foods = asyncio.run(analyze_food_image(image_bytes, ct or "image/jpeg"))
    except Exception as e:
        return _err(f"Analysis failed: {e}", 500)

    if not foods:
        return _err("No food items detected. Try a clearer photo.", 422)

    total_kcal    = sum(f["kcal"]    for f in foods)
    total_carbs   = round(sum(f["carbs"]   for f in foods), 1)
    total_fat     = round(sum(f["fat"]     for f in foods), 1)
    total_protein = round(sum(f["protein"] for f in foods), 1)
    food_summary  = ", ".join(f["name"] for f in foods)
    uid           = int(current_user["sub"])

    # Compress uploaded image to a small JPEG thumbnail (~30KB) stored as base64
    # This lets posts display real food photos in the feed
    photo_url = None
    try:
        import base64, io
        from PIL import Image
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        img.thumbnail((400, 400), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=65, optimize=True)
        photo_url = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
    except Exception:
        photo_url = None  # graceful fallback if Pillow unavailable

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO meal_sessions
                   (user_id,meal_type,total_calories,total_carbs,total_fat,total_protein,food_summary,photo_url)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                (uid, meal_type, total_kcal, total_carbs, total_fat, total_protein, food_summary, photo_url)
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

    return _ok({
        "foods":         foods,
        "total_kcal":    total_kcal,
        "total_carbs":   total_carbs,
        "total_fat":     total_fat,
        "total_protein": total_protein,
        "session_id":    session_id,
        "photo_url":     photo_url,
    })


# ── History ───────────────────────────────────────────

@meals_bp.get("/history")
@require_auth
def get_history(current_user: dict):
    uid   = int(current_user["sub"])
    limit = min(int(request.args.get("limit", 100)), 500)

    with get_db() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """SELECT id,meal_type,total_calories,total_carbs,total_fat,
                          total_protein,food_summary,photo_url,created_at
                   FROM meal_sessions WHERE user_id=%s
                   ORDER BY created_at DESC LIMIT %s""",
                (uid, limit)
            )
            sessions = [dict(r) for r in cur.fetchall()]

            if not sessions:
                return _ok({"sessions":[], "total_kcal_today":0,
                            "total_carbs_today":0.0, "total_fat_today":0.0,
                            "total_protein_today":0.0})

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

    logs_by = {}
    for lg in logs:
        logs_by.setdefault(lg["session_id"], []).append({
            "id":         lg["id"],
            "food_name":  lg["food_name"],
            "calories":   lg["calories"],
            "carbs":      float(lg["carbs"]),
            "fat":        float(lg["fat"]),
            "protein":    float(lg["protein"]),
            "serving":    lg.get("serving"),
            "created_at": lg["created_at"].isoformat(),
        })

    out = [{
        "id":             s["id"],
        "meal_type":      s["meal_type"] or "other",
        "total_calories": s["total_calories"],
        "total_carbs":    float(s["total_carbs"]),
        "total_fat":      float(s["total_fat"]),
        "total_protein":  float(s["total_protein"]),
        "food_summary":   s["food_summary"],
        "created_at":     s["created_at"].isoformat(),
        "photo_url":      s.get("photo_url"),
        "items":          logs_by.get(s["id"], []),
    } for s in sessions]

    return _ok({
        "sessions":            out,
        "total_kcal_today":    int(tr["kcal_sum"])     if tr else 0,
        "total_carbs_today":   float(tr["carbs_sum"])  if tr else 0.0,
        "total_fat_today":     float(tr["fat_sum"])    if tr else 0.0,
        "total_protein_today": float(tr["protein_sum"]) if tr else 0.0,
    })


@meals_bp.delete("/history/<int:session_id>")
@require_auth
def delete_session(session_id: int, current_user: dict):
    uid = int(current_user["sub"])
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM meal_sessions WHERE id=%s AND user_id=%s RETURNING id",
                (session_id, uid)
            )
            if not cur.fetchone():
                return _err("Session not found.", 404)
    return _ok({"message": "Deleted."})


# ── AI Meal Suggestion ────────────────────────────────

@meals_bp.post("/suggest")
@require_auth
def suggest_meal(current_user: dict):
    import httpx

    body    = request.get_json(silent=True) or {}
    prompt  = body.get("prompt", "")
    api_key = os.getenv("OPENAI_API_KEY", "")

    if not prompt:
        return _err("Prompt is required.")
    if not api_key:
        return _err("OpenAI API key not configured.", 500)

    try:
        resp = httpx.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"model": "gpt-4o", "max_tokens": 1200,
                  "messages": [{"role": "user", "content": prompt}]},
            timeout=30.0,
        )
    except Exception as e:
        return _err(f"Request failed: {e}", 502)

    if resp.status_code != 200:
        return _err(f"OpenAI error: {resp.text[:200]}", 502)

    result = resp.json()["choices"][0]["message"]["content"]
    return _ok({"result": result})

# ── Direct food log (no image, e.g. from AI suggestions) ─────────────────────

@meals_bp.post("/log")
@require_auth
def log_foods(current_user: dict):
    body      = request.get_json(silent=True) or {}
    foods     = body.get("foods", [])
    meal_type = body.get("meal_type", "other")

    if not foods:
        return _err("No foods provided.")
    if meal_type not in {"breakfast","lunch","dinner","snacks","other"}:
        meal_type = "other"

    items = []
    for f in foods[:10]:
        try:
            name    = str(f.get("name", "Food")).strip()[:255]
            kcal    = max(int(f.get("kcal", 0)), 0)
            carbs   = round(max(float(f.get("carbs", 0)), 0), 1)
            fat     = round(max(float(f.get("fat",   0)), 0), 1)
            protein = round(max(float(f.get("protein",0)), 0), 1)
            serving = str(f.get("serving", "1 serving"))[:100]
            items.append({"name":name,"kcal":kcal,"carbs":carbs,"fat":fat,"protein":protein,"serving":serving})
        except Exception:
            continue

    if not items:
        return _err("No valid food items.")

    uid           = int(current_user["sub"])
    total_kcal    = sum(f["kcal"]    for f in items)
    total_carbs   = round(sum(f["carbs"]   for f in items), 1)
    total_fat     = round(sum(f["fat"]     for f in items), 1)
    total_protein = round(sum(f["protein"] for f in items), 1)
    food_summary  = ", ".join(f["name"] for f in items)

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO meal_sessions
                   (user_id,meal_type,total_calories,total_carbs,total_fat,total_protein,food_summary)
                   VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                (uid, meal_type, total_kcal, total_carbs, total_fat, total_protein, food_summary)
            )
            session_id = cur.fetchone()[0]
            for f in items:
                cur.execute(
                    """INSERT INTO food_logs
                       (user_id,session_id,food_name,calories,carbs,fat,protein,serving)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (uid, session_id, f["name"], f["kcal"],
                     f["carbs"], f["fat"], f["protein"], f["serving"])
                )

    return _ok({
        "session_id":    session_id,
        "total_kcal":    total_kcal,
        "total_carbs":   total_carbs,
        "total_fat":     total_fat,
        "total_protein": total_protein,
        "foods":         items,
    }, 201)
