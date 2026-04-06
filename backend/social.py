"""
social.py — iCal v3 Social Features
All social routes: posts, feed, explore, likes, saves, follows, user search
"""

import psycopg2.extras
from fastapi import APIRouter, Depends, HTTPException
from auth import get_current_user
from database import get_db

router = APIRouter()


# ══════════════════════════════════════════
# USER SEARCH
# ══════════════════════════════════════════

@router.get("/users/search")
def search_users(q: str = "", current_user: dict = Depends(get_current_user)):
    if not q or len(q.strip()) < 1:
        return {"users": []}
    me = int(current_user["sub"])
    term = f"%{q.strip().lower()}%"
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
                ORDER BY u.username
                LIMIT 20
            """, (me, me, term, term))
            users = [dict(r) for r in cur.fetchall()]
    return {"users": users}


@router.get("/users/{user_id}/profile")
def get_user_profile(user_id: int, current_user: dict = Depends(get_current_user)):
    me = int(current_user["sub"])
    with get_db() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT u.id, u.email, u.username, u.bio, u.calorie_goal,
                       EXISTS(SELECT 1 FROM follows WHERE follower_id=%s AND following_id=u.id) AS following,
                       (SELECT COUNT(*) FROM follows WHERE following_id=u.id) AS followers_count,
                       (SELECT COUNT(*) FROM follows WHERE follower_id=u.id) AS following_count,
                       (SELECT COUNT(*) FROM posts WHERE user_id=u.id AND status='public') AS posts_count,
                       (SELECT COUNT(*) FROM meal_sessions WHERE user_id=u.id) AS meals_count
                FROM users u WHERE u.id=%s
            """, (me, user_id))
            user = cur.fetchone()
    if not user:
        raise HTTPException(404, "User not found.")
    return dict(user)


# ══════════════════════════════════════════
# FOLLOW SYSTEM
# ══════════════════════════════════════════

@router.post("/follow/{target_id}")
def follow_user(target_id: int, current_user: dict = Depends(get_current_user)):
    me = int(current_user["sub"])
    if me == target_id:
        raise HTTPException(400, "Cannot follow yourself.")
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM users WHERE id=%s", (target_id,))
            if not cur.fetchone():
                raise HTTPException(404, "User not found.")
            cur.execute(
                "INSERT INTO follows (follower_id,following_id) VALUES (%s,%s) ON CONFLICT DO NOTHING",
                (me, target_id)
            )
    return {"following": True, "message": "Followed."}


@router.delete("/follow/{target_id}")
def unfollow_user(target_id: int, current_user: dict = Depends(get_current_user)):
    me = int(current_user["sub"])
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM follows WHERE follower_id=%s AND following_id=%s", (me, target_id))
    return {"following": False, "message": "Unfollowed."}


# ══════════════════════════════════════════
# POSTS — CREATE, READ, UPDATE, DELETE
# ══════════════════════════════════════════

@router.post("/posts")
def create_post(body: dict, current_user: dict = Depends(get_current_user)):
    me         = int(current_user["sub"])
    session_id = body.get("session_id")
    caption    = body.get("caption", "").strip()
    status     = body.get("status", "public")

    if status not in ("public", "private"):
        status = "public"

    with get_db() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # Get session data
            cur.execute("""
                SELECT ms.*,
                       COALESCE(json_agg(json_build_object(
                           'food_name', fl.food_name,
                           'calories',  fl.calories,
                           'carbs',     fl.carbs,
                           'fat',       fl.fat,
                           'protein',   fl.protein,
                           'serving',   fl.serving
                       )) FILTER (WHERE fl.id IS NOT NULL), '[]') AS items
                FROM meal_sessions ms
                LEFT JOIN food_logs fl ON fl.session_id = ms.id
                WHERE ms.id = %s AND ms.user_id = %s
                GROUP BY ms.id
            """, (session_id, me))
            session = cur.fetchone()
            if not session:
                raise HTTPException(404, "Meal session not found.")

            cur.execute("""
                INSERT INTO posts
                  (user_id, session_id, caption, status,
                   meal_type, total_calories, total_carbs, total_fat, total_protein,
                   food_summary, items_json)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                RETURNING id
            """, (
                me, session_id, caption, status,
                session["meal_type"],
                session["total_calories"], float(session["total_carbs"]),
                float(session["total_fat"]), float(session["total_protein"]),
                session["food_summary"],
                psycopg2.extras.Json(session["items"] or [])
            ))
            post_id = cur.fetchone()["id"]

    return {"post_id": post_id, "status": status, "message": "Posted!"}


@router.patch("/posts/{post_id}/status")
def update_post_status(post_id: int, body: dict, current_user: dict = Depends(get_current_user)):
    me     = int(current_user["sub"])
    status = body.get("status", "public")
    if status not in ("public", "private"):
        raise HTTPException(400, "Status must be 'public' or 'private'.")
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE posts SET status=%s WHERE id=%s AND user_id=%s RETURNING id",
                (status, post_id, me)
            )
            if not cur.fetchone():
                raise HTTPException(404, "Post not found.")
    return {"post_id": post_id, "status": status}


@router.delete("/posts/{post_id}")
def delete_post(post_id: int, current_user: dict = Depends(get_current_user)):
    me = int(current_user["sub"])
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM posts WHERE id=%s AND user_id=%s RETURNING id",
                (post_id, me)
            )
            if not cur.fetchone():
                raise HTTPException(404, "Post not found.")
    return {"message": "Deleted."}


# ══════════════════════════════════════════
# FEED
# ══════════════════════════════════════════

@router.get("/posts/feed")
def get_feed(limit: int = 20, offset: int = 0, current_user: dict = Depends(get_current_user)):
    me = int(current_user["sub"])
    with get_db() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT p.*, u.email AS author_email, u.username AS author_username,
                       EXISTS(SELECT 1 FROM likes l WHERE l.post_id=p.id AND l.user_id=%(me)s) AS liked,
                       EXISTS(SELECT 1 FROM saves s WHERE s.post_id=p.id AND s.user_id=%(me)s) AS saved,
                       (SELECT COUNT(*) FROM likes WHERE post_id=p.id) AS like_count,
                       (p.user_id = %(me)s) AS is_owner
                FROM posts p
                JOIN users u ON u.id = p.user_id
                WHERE (
                    p.status = 'public'
                    OR p.user_id = %(me)s
                    OR (p.status = 'public' AND EXISTS(
                        SELECT 1 FROM follows f WHERE f.follower_id=%(me)s AND f.following_id=p.user_id
                    ))
                )
                ORDER BY p.created_at DESC
                LIMIT %(limit)s OFFSET %(offset)s
            """, {"me": me, "limit": limit, "offset": offset})
            posts = [dict(r) for r in cur.fetchall()]

    return {"posts": _serialize_posts(posts), "count": len(posts)}


# ══════════════════════════════════════════
# EXPLORE — FIXED with named params
# ══════════════════════════════════════════

@router.get("/posts/explore")
def get_explore(
    limit:     int = 30,
    offset:    int = 0,
    min_cal:   int = 0,
    max_cal:   int = 9999,
    meal_type: str = "",
    search:    str = "",
    current_user: dict = Depends(get_current_user)
):
    me = int(current_user["sub"])

    where  = ["p.status = 'public'"]
    params = {
        "min_cal": min_cal,
        "max_cal": max_cal,
        "me":      me,
        "limit":   limit,
        "offset":  offset,
    }

    where.append("p.total_calories >= %(min_cal)s")
    where.append("p.total_calories <= %(max_cal)s")

    if meal_type and meal_type.strip():
        where.append("p.meal_type = %(meal_type)s")
        params["meal_type"] = meal_type.strip()

    if search and search.strip():
        where.append("(p.food_summary ILIKE %(search)s OR p.caption ILIKE %(search)s OR u.username ILIKE %(search)s)")
        params["search"] = f"%{search.strip()}%"

    sql = f"""
        SELECT p.*, u.email AS author_email, u.username AS author_username,
               EXISTS(SELECT 1 FROM likes l WHERE l.post_id=p.id AND l.user_id=%(me)s) AS liked,
               EXISTS(SELECT 1 FROM saves s WHERE s.post_id=p.id AND s.user_id=%(me)s) AS saved,
               (SELECT COUNT(*) FROM likes WHERE post_id=p.id) AS like_count,
               (p.user_id = %(me)s) AS is_owner
        FROM posts p
        JOIN users u ON u.id = p.user_id
        WHERE {' AND '.join(where)}
        ORDER BY like_count DESC, p.created_at DESC
        LIMIT %(limit)s OFFSET %(offset)s
    """

    with get_db() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            posts = [dict(r) for r in cur.fetchall()]

    return {"posts": _serialize_posts(posts), "count": len(posts)}


@router.get("/posts/profile/{user_id}")
def get_profile_posts(user_id: int, current_user: dict = Depends(get_current_user)):
    me = int(current_user["sub"])
    with get_db() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT p.*, u.email AS author_email, u.username AS author_username,
                       EXISTS(SELECT 1 FROM likes l WHERE l.post_id=p.id AND l.user_id=%(me)s) AS liked,
                       (SELECT COUNT(*) FROM likes WHERE post_id=p.id) AS like_count,
                       (p.user_id = %(me)s) AS is_owner
                FROM posts p JOIN users u ON u.id = p.user_id
                WHERE p.user_id = %(uid)s
                  AND (p.status = 'public' OR p.user_id = %(me)s)
                ORDER BY p.created_at DESC
                LIMIT 50
            """, {"me": me, "uid": user_id})
            posts = [dict(r) for r in cur.fetchall()]
    return {"posts": _serialize_posts(posts)}


@router.get("/posts/saved")
def get_saved(current_user: dict = Depends(get_current_user)):
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
            posts = [dict(r) for r in cur.fetchall()]
    return {"posts": _serialize_posts(posts)}


# ══════════════════════════════════════════
# LIKES & SAVES
# ══════════════════════════════════════════

@router.post("/posts/{post_id}/like")
def like_post(post_id: int, current_user: dict = Depends(get_current_user)):
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
    return {"liked": liked, "like_count": count}


@router.delete("/posts/{post_id}/like")
def unlike_post(post_id: int, current_user: dict = Depends(get_current_user)):
    me = int(current_user["sub"])
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM likes WHERE user_id=%s AND post_id=%s", (me, post_id))
            cur.execute("SELECT COUNT(*) FROM likes WHERE post_id=%s", (post_id,))
            count = cur.fetchone()[0]
    return {"liked": False, "like_count": count}


@router.post("/posts/{post_id}/save")
def save_post(post_id: int, current_user: dict = Depends(get_current_user)):
    me = int(current_user["sub"])
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO saves (user_id,post_id) VALUES (%s,%s) ON CONFLICT DO NOTHING RETURNING id",
                (me, post_id)
            )
            saved = cur.fetchone() is not None
    return {"saved": saved}


@router.delete("/posts/{post_id}/save")
def unsave_post(post_id: int, current_user: dict = Depends(get_current_user)):
    me = int(current_user["sub"])
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM saves WHERE user_id=%s AND post_id=%s", (me, post_id))
    return {"saved": False}


# ══════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════

def _serialize_posts(posts: list) -> list:
    for p in posts:
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
    return posts
