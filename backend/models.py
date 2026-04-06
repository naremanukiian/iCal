from pydantic import BaseModel, EmailStr, Field, field_validator
from typing import Optional, List

class RegisterRequest(BaseModel):
    email:        EmailStr
    password:     str = Field(min_length=6)
    username:     Optional[str] = None
    weight:       Optional[float] = None
    goal:         Optional[str] = None
    calorie_goal: Optional[int] = Field(default=2000, gt=0, lt=10000)

    @field_validator("goal")
    @classmethod
    def validate_goal(cls, v):
        if v and v not in ("lose","maintain","gain"):
            raise ValueError("goal must be lose, maintain, or gain")
        return v

class LoginRequest(BaseModel):
    email:    EmailStr
    password: str

class TokenResponse(BaseModel):
    token:        str
    user_id:      int
    email:        str
    username:     str
    calorie_goal: int

class UserProfile(BaseModel):
    id:           int
    email:        str
    username:     str
    bio:          Optional[str]
    weight:       Optional[float]
    goal:         Optional[str]
    calorie_goal: int
    created_at:   str

class FoodItem(BaseModel):
    name:    str
    kcal:    int
    carbs:   float
    fat:     float
    protein: float
    serving: Optional[str] = None

class AnalyzeResponse(BaseModel):
    foods:         List[FoodItem]
    total_kcal:    int
    total_carbs:   float
    total_fat:     float
    total_protein: float
    session_id:    int

class FoodLogItem(BaseModel):
    id:         int
    food_name:  str
    calories:   int
    carbs:      float
    fat:        float
    protein:    float
    serving:    Optional[str]
    created_at: str

class MealSessionOut(BaseModel):
    id:             int
    meal_type:      str
    total_calories: int
    total_carbs:    float
    total_fat:      float
    total_protein:  float
    food_summary:   Optional[str]
    created_at:     str
    items:          List[FoodLogItem]

class HistoryResponse(BaseModel):
    sessions:            List[MealSessionOut]
    total_kcal_today:    int
    total_carbs_today:   float
    total_fat_today:     float
    total_protein_today: float
