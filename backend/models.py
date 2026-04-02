"""
models.py  —  Pydantic request / response schemas.
"""

from pydantic import BaseModel, EmailStr, Field, field_validator
from typing import Optional, List
from datetime import datetime


# ── Auth ───────────────────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    email:    EmailStr
    password: str = Field(min_length=6, max_length=128)
    weight:   Optional[float] = Field(default=None, gt=0, lt=500)
    goal:     Optional[str]   = None

    @field_validator("goal")
    @classmethod
    def validate_goal(cls, v):
        if v is not None and v not in ("lose", "maintain", "gain"):
            raise ValueError("goal must be 'lose', 'maintain', or 'gain'")
        return v


class LoginRequest(BaseModel):
    email:    EmailStr
    password: str


class TokenResponse(BaseModel):
    token:    str
    user_id:  int
    email:    str


class UserProfile(BaseModel):
    id:         int
    email:      str
    weight:     Optional[float]
    goal:       Optional[str]
    created_at: str


# ── Food Analysis ──────────────────────────────────────────────────────────────

class FoodItem(BaseModel):
    name:    str
    kcal:    int
    serving: Optional[str] = None


class AnalyzeResponse(BaseModel):
    foods:      List[FoodItem]
    total_kcal: int
    session_id: int


# ── History ───────────────────────────────────────────────────────────────────

class FoodLogItem(BaseModel):
    id:         int
    food_name:  str
    calories:   int
    serving:    Optional[str]
    created_at: str


class MealSessionOut(BaseModel):
    id:             int
    total_calories: int
    food_summary:   Optional[str]
    created_at:     str
    items:          List[FoodLogItem]


class HistoryResponse(BaseModel):
    sessions:   List[MealSessionOut]
    total_kcal_today: int
