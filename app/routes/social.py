"""
app/routes/social.py — Social features
Posts CRUD, feed, explore, follow/unfollow, likes, saves, user search
"""
import psycopg2.extras
from flask import Blueprint, request, jsonify

from app.services.database import get_db
from app.services.auth     import require_auth

social_bp = Blueprint("social", __name__)


def _err(msg, status=400): return jsonify({"detail": msg}), status
def _ok(data, status=200): return jsonify(data), status


# ── User search ───────────────────────────────────────

@social_bp.get("/users/search")
@require_auth
def search_users(current_user: dict):
    q  = request.args.get("q", "").strip()
    if not q:
        return _ok({"users": []})
    me   = int(current_user["sub"])
    term = f"%{q.lower()}%"
    with get_db() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT u.id, u.email, u.username, u.bio,
                       EXISTS(SELECT 1 FROM follows f
                              WHERE f.follower_id = %s AND f.following_id = u.id) AS following,
                       (SELECT COUNT(*) FROM follows WHERE following_id = u.id) AS followers_count,
                       (SELECT COUNT(*) FROM posts WHERE user_id = u.id AND status = 'public') AS posts_count
                FROM users u
                WHERE u.id != %s
                  AND (LOWER(u.username) LIKE %s OR LOWER(u.email) LIKE %s)
                ORDER BY u.username LIMIT 20
            """, (me, me, term, term))
            users = [dict(r) for r in cur.fetchall()]
    return _ok({"users": users})


@social_bp.get("/users/<int:user_id>/profile")
@require_auth
def get_user_profile(user_id: int, current_user: dict):
    me = int(current_user["sub"])
    with get_db() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT u.id, u.email, u.username, u.bio, u.calorie_goal,
                       EXISTS(SELECT 1 FROM follows WHERE follower_id=%(me)s AND following_id=u.id) AS following,
                       (SELECT COUNT(*) FROM follows WHERE following_id=u.id) AS followers_count,
                       (SELECT COUNT(*) FROM follows WHERE follower_id=u.id) AS following_count,
                       (SELECT COUNT(*) FROM posts WHERE user_id=u.id AND status='public') AS posts_count,
                       (SELECT COUNT(*) FROM meal_sessions WHERE user_id=u.id) AS meals_count
                FROM users u WHERE u.id=%(uid)s
            """, {"me": me, "uid": user_id})
            user = cur.fetchone()
    if not user:
        return _err("User not found.", 404)
    return _ok(dict(user))


# ── Follows ───────────────────────────────────────────

@social_bp.post("/follow/<int:target_id>")
@require_auth
def follow(target_id: int, current_user: dict):
    me = int(current_user["sub"])
    if me == target_id:
        return _err("Cannot follow yourself.")
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM users WHERE id=%s", (target_id,))
            if not cur.fetchone():
                return _err("User not found.", 404)
            cur.execute(
                "INSERT INTO follows (follower_id,following_id) VALUES (%s,%s) ON CONFLICT DO NOTHING",
                (me, target_id)
            )
    return _ok({"following": True, "message": "Followed."})


@social_bp.delete("/follow/<int:target_id>")
@require_auth
def unfollow(target_id: int, current_user: dict):
    me = int(current_user["sub"])
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM follows WHERE follower_id=%s AND following_id=%s", (me, target_id))
    return _ok({"following": False, "message": "Unfollowed."})


# ── Posts ─────────────────────────────────────────────

@social_bp.post("/posts")
@require_auth
def create_post(current_user: dict):
    me         = int(current_user["sub"])
    body       = request.get_json(silent=True) or {}
    session_id = body.get("session_id")
    caption    = body.get("caption", "").strip()
    status     = body.get("status", "public")
    if status not in ("public", "private"):
        status = "public"

    with get_db() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT ms.*,
                       COALESCE(json_agg(json_build_object(
                           'food_name', fl.food_name, 'calories', fl.calories,
                           'carbs', fl.carbs, 'fat', fl.fat,
                           'protein', fl.protein, 'serving', fl.serving
                       )) FILTER (WHERE fl.id IS NOT NULL), '[]') AS items
                FROM meal_sessions ms
                LEFT JOIN food_logs fl ON fl.session_id = ms.id
                WHERE ms.id = %s AND ms.user_id = %s
                GROUP BY ms.id
            """, (session_id, me))
            session = cur.fetchone()
            if not session:
                return _err("Meal session not found.", 404)

            cur.execute("""
                INSERT INTO posts
                  (user_id,session_id,caption,status,meal_type,
                   total_calories,total_carbs,total_fat,total_protein,food_summary,items_json)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                RETURNING id
            """, (
                me, session_id, caption, status, session["meal_type"],
                session["total_calories"], float(session["total_carbs"]),
                float(session["total_fat"]), float(session["total_protein"]),
                session["food_summary"],
                psycopg2.extras.Json(session["items"] or [])
            ))
            post_id = cur.fetchone()["id"]

    return _ok({"post_id": post_id, "status": status, "message": "Posted!"}, 201)


@social_bp.patch("/posts/<int:post_id>/status")
@require_auth
def update_post_status(post_id: int, current_user: dict):
    me     = int(current_user["sub"])
    body   = request.get_json(silent=True) or {}
    status = body.get("status", "public")
    if status not in ("public", "private"):
        return _err("Status must be 'public' or 'private'.")
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE posts SET status=%s WHERE id=%s AND user_id=%s RETURNING id",
                (status, post_id, me)
            )
            if not cur.fetchone():
                return _err("Post not found.", 404)
    return _ok({"post_id": post_id, "status": status})


@social_bp.delete("/posts/<int:post_id>")
@require_auth
def delete_post(post_id: int, current_user: dict):
    me = int(current_user["sub"])
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM posts WHERE id=%s AND user_id=%s RETURNING id",
                (post_id, me)
            )
            if not cur.fetchone():
                return _err("Post not found.", 404)
    return _ok({"message": "Deleted."})


# ── Feed & Explore ────────────────────────────────────

def _post_query(where: str, params: dict, me: int) -> str:
    return f"""
        SELECT p.*, u.email AS author_email, u.username AS author_username,
               EXISTS(SELECT 1 FROM likes l WHERE l.post_id=p.id AND l.user_id=%(me)s) AS liked,
               EXISTS(SELECT 1 FROM saves s WHERE s.post_id=p.id AND s.user_id=%(me)s) AS saved,
               (SELECT COUNT(*) FROM likes WHERE post_id=p.id) AS like_count,
               (p.user_id = %(me)s) AS is_owner
        FROM posts p JOIN users u ON u.id = p.user_id
        WHERE {where}
        ORDER BY like_count DESC, p.created_at DESC
        LIMIT %(limit)s OFFSET %(offset)s
    """


def _serialize_posts(rows) -> list:
    out = []
    for p in rows:
        p = dict(p)
        if p.get("created_at"):
            p["created_at"] = p["created_at"].isoformat()
        p["total_carbs"]   = float(p.get("total_carbs", 0) or 0)
        p["total_fat"]     = float(p.get("total_fat", 0) or 0)
        p["total_protein"] = float(p.get("total_protein", 0) or 0)
        p["like_count"]    = int(p.get("like_count", 0) or 0)
        p["liked"]         = bool(p.get("liked", False))
        p["saved"]         = bool(p.get("saved", False))
        p["is_owner"]      = bool(p.get("is_owner", False))
        p["author_username"] = p.get("author_username") or (p.get("author_email","").split("@")[0])
        if p.get("items_json") and not isinstance(p["items_json"], list):
            import json
            try:    p["items_json"] = json.loads(p["items_json"])
            except: p["items_json"] = []
        out.append(p)
    return out


@social_bp.get("/posts/feed")
@require_auth
def get_feed(current_user: dict):
    me     = int(current_user["sub"])
    limit  = min(int(request.args.get("limit", 20)), 100)
    offset = int(request.args.get("offset", 0))
    params = {"me": me, "limit": limit, "offset": offset}
    where  = """(
        p.status = 'public' OR p.user_id = %(me)s
        OR (p.status = 'public' AND EXISTS(
            SELECT 1 FROM follows f WHERE f.follower_id=%(me)s AND f.following_id=p.user_id
        ))
    )"""
    with get_db() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(_post_query(where, params, me), params)
            posts = _serialize_posts(cur.fetchall())
    return _ok({"posts": posts, "count": len(posts)})


@social_bp.get("/posts/explore")
@require_auth
def get_explore(current_user: dict):
    me        = int(current_user["sub"])
    limit     = min(int(request.args.get("limit", 30)), 100)
    offset    = int(request.args.get("offset", 0))
    min_cal   = int(request.args.get("min_cal", 0))
    max_cal   = int(request.args.get("max_cal", 9999))
    meal_type = request.args.get("meal_type", "").strip()
    search    = request.args.get("search", "").strip()

    where  = ["p.status = 'public'",
              "p.total_calories >= %(min_cal)s",
              "p.total_calories <= %(max_cal)s"]
    params = {"me": me, "limit": limit, "offset": offset, "min_cal": min_cal, "max_cal": max_cal}

    if meal_type:
        where.append("p.meal_type = %(meal_type)s")
        params["meal_type"] = meal_type
    if search:
        where.append("(p.food_summary ILIKE %(search)s OR p.caption ILIKE %(search)s OR u.username ILIKE %(search)s)")
        params["search"] = f"%{search}%"

    sql = f"""
        SELECT p.*, u.email AS author_email, u.username AS author_username,
               EXISTS(SELECT 1 FROM likes l WHERE l.post_id=p.id AND l.user_id=%(me)s) AS liked,
               EXISTS(SELECT 1 FROM saves s WHERE s.post_id=p.id AND s.user_id=%(me)s) AS saved,
               (SELECT COUNT(*) FROM likes WHERE post_id=p.id) AS like_count,
               (p.user_id = %(me)s) AS is_owner
        FROM posts p JOIN users u ON u.id = p.user_id
        WHERE {' AND '.join(where)}
        ORDER BY like_count DESC, p.created_at DESC
        LIMIT %(limit)s OFFSET %(offset)s
    """
    with get_db() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            posts = _serialize_posts(cur.fetchall())
    return _ok({"posts": posts, "count": len(posts)})


@social_bp.get("/posts/profile/<int:user_id>")
@require_auth
def get_profile_posts(user_id: int, current_user: dict):
    me = int(current_user["sub"])
    params = {"me": me, "uid": user_id, "limit": 50, "offset": 0}
    where  = "p.user_id = %(uid)s AND (p.status = 'public' OR p.user_id = %(me)s)"
    with get_db() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(_post_query(where, params, me), params)
            posts = _serialize_posts(cur.fetchall())
    return _ok({"posts": posts})


@social_bp.get("/posts/saved")
@require_auth
def get_saved(current_user: dict):
    me = int(current_user["sub"])
    with get_db() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT p.*, u.email AS author_email, u.username AS author_username,
                       TRUE AS saved,
                       (SELECT COUNT(*) FROM likes WHERE post_id=p.id) AS like_count,
                       (p.user_id = %(me)s) AS is_owner
                FROM saves s
                JOIN posts p ON p.id = s.post_id
                JOIN users u ON u.id = p.user_id
                WHERE s.user_id = %(me)s
                ORDER BY s.created_at DESC
            """, {"me": me})
            posts = _serialize_posts(cur.fetchall())
    return _ok({"posts": posts})


# ── Likes & Saves ─────────────────────────────────────

@social_bp.post("/posts/<int:post_id>/like")
@require_auth
def like_post(post_id: int, current_user: dict):
    me = int(current_user["sub"])
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO likes (user_id,post_id) VALUES (%s,%s) ON CONFLICT DO NOTHING RETURNING id",
                (me, post_id)
            )
            liked = cur.fetchone() is not None
            cur.execute("SELECT COUNT(*) FROM likes WHERE post_id=%s", (post_id,))
            count = cur.fetchone()[0]
    return _ok({"liked": liked, "like_count": count})


@social_bp.delete("/posts/<int:post_id>/like")
@require_auth
def unlike_post(post_id: int, current_user: dict):
    me = int(current_user["sub"])
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM likes WHERE user_id=%s AND post_id=%s", (me, post_id))
            cur.execute("SELECT COUNT(*) FROM likes WHERE post_id=%s", (post_id,))
            count = cur.fetchone()[0]
    return _ok({"liked": False, "like_count": count})


@social_bp.post("/posts/<int:post_id>/save")
@require_auth
def save_post(post_id: int, current_user: dict):
    me = int(current_user["sub"])
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO saves (user_id,post_id) VALUES (%s,%s) ON CONFLICT DO NOTHING RETURNING id",
                (me, post_id)
            )
            saved = cur.fetchone() is not None
    return _ok({"saved": saved})


@social_bp.delete("/posts/<int:post_id>/save")
@require_auth
def unsave_post(post_id: int, current_user: dict):
    me = int(current_user["sub"])
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM saves WHERE user_id=%s AND post_id=%s", (me, post_id))
    return _ok({"saved": False})
