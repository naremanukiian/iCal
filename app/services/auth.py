"""
app/services/auth.py — JWT + bcrypt authentication
"""
import os
import bcrypt
import jwt
from datetime import datetime, timedelta, timezone
from functools import wraps
from flask import request, jsonify

SECRET_KEY    = os.getenv("JWT_SECRET", "ical-secret-change-in-production")
ALGORITHM     = "HS256"
EXPIRE_HOURS  = 48


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt(12)).decode()


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode(), hashed.encode())
    except Exception:
        return False


def create_token(user_id: int, email: str) -> str:
    return jwt.encode({
        "sub":   str(user_id),
        "email": email,
        "iat":   datetime.now(timezone.utc),
        "exp":   datetime.now(timezone.utc) + timedelta(hours=EXPIRE_HOURS),
    }, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])


def require_auth(f):
    """Decorator — extracts Bearer token, injects `current_user` into kwargs."""
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return jsonify({"detail": "Missing or invalid Authorization header."}), 401
        token = auth.split(" ", 1)[1]
        try:
            payload = decode_token(token)
        except jwt.ExpiredSignatureError:
            return jsonify({"detail": "Session expired — please log in again."}), 401
        except jwt.InvalidTokenError:
            return jsonify({"detail": "Invalid token."}), 401
        kwargs["current_user"] = payload
        return f(*args, **kwargs)
    return decorated
