"""
auth.py
JWT creation / validation + bcrypt password hashing.
"""

import os
import bcrypt
import jwt
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from dotenv import load_dotenv

load_dotenv()

SECRET_KEY      = os.getenv("JWT_SECRET", "calorieai-fallback-secret")
ALGORITHM       = "HS256"
EXPIRE_HOURS    = 48          # token stays valid 48 h
security        = HTTPBearer()


# ── Passwords ──────────────────────────────────────────────────────────────────

def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt(rounds=12)).decode()


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode(), hashed.encode())
    except Exception:
        return False


# ── Tokens ────────────────────────────────────────────────────────────────────

def create_token(user_id: int, email: str) -> str:
    payload = {
        "sub":   str(user_id),
        "email": email,
        "iat":   datetime.now(timezone.utc),
        "exp":   datetime.now(timezone.utc) + timedelta(hours=EXPIRE_HOURS),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, detail="Session expired — please log in again.")
    except jwt.InvalidTokenError:
        raise HTTPException(401, detail="Invalid authentication token.")


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Security(security),
) -> dict:
    """FastAPI dependency — extracts the authenticated user from Bearer token."""
    return decode_token(credentials.credentials)
