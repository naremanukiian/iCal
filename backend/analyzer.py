"""
analyzer.py
───────────
Food detection pipeline:
  1. OpenAI GPT-4o Vision  →  identifies foods from the image
  2. 60 000-item food database  →  looks up real calorie values
  3. Intelligent fallback  →  if lookup fails, trusts the AI estimate

Dataset: https://github.com/theoyuncu8/food_tracker_data/main/60000_food_data.json
"""

import os
import json
import base64
import re
import httpx
from typing import List, Dict, Optional
from dotenv import load_dotenv

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
FOOD_DB_PATH   = os.getenv("FOOD_DB_PATH", "food_data.json")

# ── Load 60 000-item food database ────────────────────────────────────────────

def _load_food_db(path: str) -> Dict[str, dict]:
    """
    Load the JSON food dataset into a dict keyed by lowercase food name.
    Each value: {"kcal": int, "serving": str, "carb_pct": int, ...}
    """
    db: Dict[str, dict] = {}

    if not os.path.exists(path):
        print(f"⚠  Food database not found at '{path}'. Using built-in fallback.")
        return db

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        for item in data:
            raw_name = item.get("title", "").strip()
            if not raw_name:
                continue
            try:
                kcal = round(float(item.get("kcal", 0)))
            except (TypeError, ValueError):
                continue
            if kcal <= 0:
                continue

            key = raw_name.lower()
            # Store first occurrence (usually the cleanest entry)
            if key not in db:
                db[key] = {
                    "kcal":    kcal,
                    "serving": item.get("f_unit", "serving"),
                    "name":    raw_name,
                }

        print(f"✅  Food database loaded: {len(db):,} items from '{path}'")
    except Exception as e:
        print(f"⚠  Failed to load food database: {e}")

    return db


FOOD_DB: Dict[str, dict] = _load_food_db(FOOD_DB_PATH)

# ── Hardcoded fallback (always available, common foods) ───────────────────────

FALLBACK_DB: Dict[str, int] = {
    # Grains
    "rice": 206, "white rice": 206, "brown rice": 216, "fried rice": 338,
    "pasta": 220, "spaghetti": 220, "noodles": 220, "bread": 79,
    "toast": 79, "bagel": 245, "croissant": 231, "pita": 165,
    # Proteins
    "chicken breast": 165, "grilled chicken": 165, "chicken": 185,
    "chicken leg": 185, "chicken wing": 203, "beef": 250,
    "steak": 271, "ground beef": 254, "pork": 242, "bacon": 541,
    "salmon": 208, "tuna": 154, "shrimp": 99, "fish": 136,
    "egg": 78, "eggs": 155, "omelette": 154, "tofu": 94,
    "turkey": 189, "lamb": 294, "sausage": 301,
    # Dairy
    "milk": 149, "cheese": 402, "yogurt": 100, "butter": 717,
    "ice cream": 207, "cream": 340, "cottage cheese": 98,
    # Vegetables
    "salad": 15, "green salad": 15, "caesar salad": 184,
    "broccoli": 55, "carrot": 41, "spinach": 23,
    "tomato": 18, "cucumber": 16, "lettuce": 5,
    "corn": 86, "peas": 81, "avocado": 160,
    "mushroom": 22, "onion": 40, "pepper": 31, "asparagus": 20,
    # Starchy veg
    "potato": 77, "mashed potato": 113, "sweet potato": 86,
    "french fries": 312, "fries": 312, "chips": 536,
    # Fruits
    "apple": 95, "banana": 105, "orange": 62, "grape": 104,
    "strawberry": 49, "watermelon": 30, "mango": 60,
    "pineapple": 50, "blueberry": 57, "cherry": 50,
    # Fast food / meals
    "burger": 354, "cheeseburger": 303, "pizza": 266,
    "sandwich": 300, "wrap": 280, "hot dog": 290,
    "taco": 226, "burrito": 490, "nachos": 346,
    "fried chicken": 320, "nuggets": 296,
    # Snacks & sweets
    "chocolate": 546, "cookie": 78, "cake": 257, "donut": 253,
    "muffin": 340, "granola bar": 193, "popcorn": 375,
    "pretzel": 380, "cracker": 421,
    # Breakfast
    "pancake": 227, "waffle": 291, "oatmeal": 71,
    "cereal": 367, "granola": 471,
    # Drinks
    "coffee": 2, "latte": 190, "cappuccino": 74,
    "orange juice": 45, "apple juice": 46,
    "smoothie": 150, "milkshake": 230,
    "soda": 37, "cola": 37,
    # Sauces
    "ketchup": 112, "mayonnaise": 680, "mustard": 66,
}


def _lookup_calories(food_name: str) -> Optional[dict]:
    """
    Search the 60k DB then the fallback for a given food name.
    Returns {"kcal": int, "serving": str} or None.
    """
    name = food_name.lower().strip()

    # 1. Exact match in big DB
    if name in FOOD_DB:
        return FOOD_DB[name]

    # 2. Exact match in fallback
    if name in FALLBACK_DB:
        return {"kcal": FALLBACK_DB[name], "serving": "1 serving"}

    # 3. Partial match in big DB (first word or substring)
    for key, val in FOOD_DB.items():
        if key in name or name in key:
            return val

    # 4. Partial match in fallback
    for key, kcal in FALLBACK_DB.items():
        if key in name or name in key:
            return {"kcal": kcal, "serving": "1 serving"}

    # 5. Word-by-word match
    words = name.split()
    for word in words:
        if len(word) < 4:
            continue
        if word in FOOD_DB:
            return FOOD_DB[word]
        if word in FALLBACK_DB:
            return {"kcal": FALLBACK_DB[word], "serving": "1 serving"}

    return None


# ── OpenAI Vision ─────────────────────────────────────────────────────────────

VISION_PROMPT = """You are a professional nutritionist and food recognition AI.

Analyze this food image carefully and identify ALL distinct food items visible on the plate or in the image.

For each food item:
1. Give a specific, clear name (e.g. "Grilled Chicken Breast" not just "Chicken")
2. Estimate realistic calories based on the visible portion size
3. Note the approximate serving size

Return ONLY a valid JSON array with no extra text, markdown, or explanation:
[
  {"name": "Grilled Chicken Breast", "kcal": 165, "serving": "150g"},
  {"name": "Steamed White Rice", "kcal": 206, "serving": "1 cup"},
  {"name": "Steamed Broccoli", "kcal": 55, "serving": "1 cup"}
]

Rules:
- Identify 1 to 6 food items maximum
- Be specific about cooking method when visible (grilled, fried, boiled, raw)
- Estimate realistic portion sizes for a typical meal
- If unsure about exact calories, give your best estimate
- Return ONLY the JSON array, nothing else"""


async def _call_openai_vision(image_bytes: bytes, content_type: str) -> List[dict]:
    """Call GPT-4o Vision API and return parsed food list."""
    b64 = base64.b64encode(image_bytes).decode()
    data_url = f"data:{content_type};base64,{b64}"

    payload = {
        "model": "gpt-4o",
        "max_tokens": 600,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type":      "image_url",
                        "image_url": {"url": data_url, "detail": "low"},
                    },
                    {"type": "text", "text": VISION_PROMPT},
                ],
            }
        ],
    }

    async with httpx.AsyncClient(timeout=45.0) as client:
        resp = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type":  "application/json",
            },
            json=payload,
        )

    if resp.status_code != 200:
        raise RuntimeError(f"OpenAI API error {resp.status_code}: {resp.text[:200]}")

    raw = resp.json()["choices"][0]["message"]["content"].strip()

    # Strip markdown code fences if present
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    raw = raw.strip()

    return json.loads(raw)


# ── Mock fallback (when OpenAI is unavailable) ────────────────────────────────

MOCK_RESPONSES = [
    [
        {"name": "Grilled Chicken Breast", "kcal": 165, "serving": "150g"},
        {"name": "Steamed White Rice",     "kcal": 206, "serving": "1 cup"},
        {"name": "Steamed Broccoli",       "kcal": 55,  "serving": "1 cup"},
    ],
    [
        {"name": "Caesar Salad",  "kcal": 184, "serving": "2 cups"},
        {"name": "Garlic Bread",  "kcal": 190, "serving": "2 slices"},
    ],
    [
        {"name": "Beef Burger",  "kcal": 354, "serving": "1 burger"},
        {"name": "French Fries", "kcal": 312, "serving": "medium portion"},
        {"name": "Cola",         "kcal": 140, "serving": "12 fl oz"},
    ],
    [
        {"name": "Avocado Toast",   "kcal": 290, "serving": "2 slices"},
        {"name": "Poached Eggs",    "kcal": 156, "serving": "2 eggs"},
        {"name": "Orange Juice",    "kcal": 112, "serving": "8 fl oz"},
    ],
    [
        {"name": "Margherita Pizza", "kcal": 285, "serving": "2 slices"},
    ],
    [
        {"name": "Salmon Fillet",   "kcal": 208, "serving": "150g"},
        {"name": "Mashed Potato",   "kcal": 113, "serving": "1 cup"},
        {"name": "Green Beans",     "kcal": 31,  "serving": "1 cup"},
    ],
]


def _mock_response(image_bytes: bytes) -> List[dict]:
    idx = len(image_bytes) % len(MOCK_RESPONSES)
    return MOCK_RESPONSES[idx]


# ── Main public function ───────────────────────────────────────────────────────

async def analyze_food_image(
    image_bytes: bytes,
    content_type: str = "image/jpeg",
) -> List[dict]:
    """
    Analyze a food photo and return a list of:
      {"name": str, "kcal": int, "serving": str}

    Pipeline:
      1. GPT-4o Vision  →  identifies foods + AI calorie estimates
      2. 60k food DB    →  replaces AI calories with real database values
      3. Mock fallback  →  if OpenAI is unavailable
    """

    # ── Step 1: Get food names from OpenAI Vision ──────────────────────────────
    ai_foods: List[dict] = []

    if OPENAI_API_KEY and OPENAI_API_KEY not in ("", "your-key-here"):
        try:
            ai_foods = await _call_openai_vision(image_bytes, content_type)
        except Exception as e:
            print(f"⚠  OpenAI Vision failed: {e}  →  using mock response")
            ai_foods = _mock_response(image_bytes)
    else:
        print("⚠  No OpenAI key set  →  using mock response")
        ai_foods = _mock_response(image_bytes)

    # ── Step 2: Enrich with real food database calories ────────────────────────
    results: List[dict] = []

    for item in ai_foods:
        name    = str(item.get("name", "Unknown Food")).strip()
        ai_kcal = int(item.get("kcal", 0))
        serving = str(item.get("serving", "1 serving"))

        db_entry = _lookup_calories(name)

        if db_entry:
            # Use database value (more accurate than AI estimate)
            kcal    = db_entry["kcal"]
            serving = db_entry.get("serving", serving)
        elif 10 <= ai_kcal <= 2500:
            # Trust the AI estimate if it's in a sensible range
            kcal = ai_kcal
        else:
            # Last resort: 200 kcal generic estimate
            kcal = 200

        results.append({
            "name":    name,
            "kcal":    kcal,
            "serving": serving,
        })

    return results
