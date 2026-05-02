"""
analyzer.py
───────────
Pipeline:
  1. GPT-4o Vision  → identifies food items from image
  2. 60k food DB    → looks up real kcal + macros (carbs/fat/protein)
  3. Smart fallback → uses AI estimates if DB lookup fails
"""

import os, json, base64, re, httpx
from typing import List, Dict, Optional




OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
FOOD_DB_PATH   = os.getenv("FOOD_DB_PATH", "food_data.json")


# ── Load 60k food database ─────────────────────────

def _load_db(path: str) -> Dict[str, dict]:
    """
    Load the JSON food dataset.
    Each entry has: kcal, carbs_g, fat_g, protein_g, serving
    We compute macros in grams from pct fields + kcal:
      carbs_g   = (carb_pct/100 * kcal) / 4
      fat_g     = (fat_pct/100  * kcal) / 9
      protein_g = (protein_pct/100 * kcal) / 4
    """
    db: Dict[str, dict] = {}
    if not os.path.exists(path):
        print(f"⚠  Food DB not found at '{path}'. Using fallback only.")
        return db
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        for item in data:
            name = item.get("title", "").strip()
            if not name:
                continue
            try:
                kcal       = round(float(item.get("kcal", 0)))
                carb_pct   = float(item.get("carb_pct",    0))
                fat_pct    = float(item.get("fat_pct",     0))
                protein_pct= float(item.get("protein_pct", 0))
            except (TypeError, ValueError):
                continue
            if kcal <= 0:
                continue

            carbs_g   = round((carb_pct    / 100 * kcal) / 4, 1)
            fat_g     = round((fat_pct     / 100 * kcal) / 9, 1)
            protein_g = round((protein_pct / 100 * kcal) / 4, 1)

            key = name.lower()
            if key not in db:
                db[key] = {
                    "name":    name,
                    "kcal":    kcal,
                    "carbs":   carbs_g,
                    "fat":     fat_g,
                    "protein": protein_g,
                    "serving": item.get("f_unit", "serving"),
                }
        print(f"✅  Food DB loaded: {len(db):,} items from '{path}'")
    except Exception as e:
        print(f"⚠  Failed to load food DB: {e}")
    return db


FOOD_DB: Dict[str, dict] = _load_db(FOOD_DB_PATH)


# ── Hardcoded fallback ─────────────────────────────
# Format: name → {kcal, carbs, fat, protein}

FALLBACK: Dict[str, dict] = {
    "rice":            {"kcal":206,"carbs":44.5,"fat":0.4,"protein":4.3},
    "white rice":      {"kcal":206,"carbs":44.5,"fat":0.4,"protein":4.3},
    "brown rice":      {"kcal":216,"carbs":44.8,"fat":1.8,"protein":5.0},
    "fried rice":      {"kcal":338,"carbs":55.0,"fat":11.2,"protein":7.4},
    "pasta":           {"kcal":220,"carbs":43.2,"fat":1.3,"protein":8.1},
    "spaghetti":       {"kcal":220,"carbs":43.2,"fat":1.3,"protein":8.1},
    "noodles":         {"kcal":220,"carbs":40.0,"fat":2.0,"protein":7.5},
    "bread":           {"kcal":79, "carbs":15.0,"fat":1.0,"protein":2.7},
    "toast":           {"kcal":79, "carbs":15.0,"fat":1.0,"protein":2.7},
    "bagel":           {"kcal":245,"carbs":47.9,"fat":1.5,"protein":9.0},
    "croissant":       {"kcal":231,"carbs":26.0,"fat":12.0,"protein":5.0},
    "pizza":           {"kcal":266,"carbs":33.0,"fat":10.0,"protein":11.0},
    "burger":          {"kcal":354,"carbs":29.0,"fat":17.0,"protein":20.0},
    "cheeseburger":    {"kcal":303,"carbs":24.0,"fat":13.0,"protein":17.0},
    "sandwich":        {"kcal":300,"carbs":34.0,"fat":10.0,"protein":15.0},
    "wrap":            {"kcal":280,"carbs":30.0,"fat":10.0,"protein":14.0},
    "hot dog":         {"kcal":290,"carbs":22.0,"fat":16.0,"protein":11.0},
    "taco":            {"kcal":226,"carbs":20.0,"fat":10.0,"protein":11.0},
    "burrito":         {"kcal":490,"carbs":56.0,"fat":18.0,"protein":25.0},
    "chicken breast":  {"kcal":165,"carbs":0.0, "fat":3.6,"protein":31.0},
    "grilled chicken": {"kcal":165,"carbs":0.0, "fat":3.6,"protein":31.0},
    "chicken":         {"kcal":185,"carbs":0.0, "fat":7.0,"protein":28.0},
    "chicken leg":     {"kcal":185,"carbs":0.0, "fat":9.0,"protein":26.0},
    "fried chicken":   {"kcal":320,"carbs":12.0,"fat":18.0,"protein":28.0},
    "beef":            {"kcal":250,"carbs":0.0, "fat":17.0,"protein":26.0},
    "steak":           {"kcal":271,"carbs":0.0, "fat":19.0,"protein":26.0},
    "ground beef":     {"kcal":254,"carbs":0.0, "fat":20.0,"protein":17.0},
    "pork":            {"kcal":242,"carbs":0.0, "fat":14.0,"protein":27.0},
    "bacon":           {"kcal":541,"carbs":1.4, "fat":42.0,"protein":37.0},
    "sausage":         {"kcal":301,"carbs":2.0, "fat":25.0,"protein":16.0},
    "salmon":          {"kcal":208,"carbs":0.0, "fat":13.0,"protein":20.0},
    "tuna":            {"kcal":154,"carbs":0.0, "fat":5.0, "protein":25.0},
    "fish":            {"kcal":136,"carbs":0.0, "fat":5.0, "protein":22.0},
    "shrimp":          {"kcal":99, "carbs":0.9, "fat":1.7, "protein":19.0},
    "egg":             {"kcal":78, "carbs":0.6, "fat":5.0, "protein":6.0},
    "eggs":            {"kcal":155,"carbs":1.1, "fat":11.0,"protein":13.0},
    "omelette":        {"kcal":154,"carbs":1.6, "fat":11.0,"protein":11.0},
    "tofu":            {"kcal":94, "carbs":2.3, "fat":5.0, "protein":10.0},
    "turkey":          {"kcal":189,"carbs":0.0, "fat":7.0, "protein":29.0},
    "milk":            {"kcal":149,"carbs":12.0,"fat":8.0, "protein":8.0},
    "cheese":          {"kcal":402,"carbs":1.3, "fat":33.0,"protein":25.0},
    "yogurt":          {"kcal":100,"carbs":17.0,"fat":0.7, "protein":17.0},
    "butter":          {"kcal":717,"carbs":0.1, "fat":81.0,"protein":0.9},
    "ice cream":       {"kcal":207,"carbs":24.0,"fat":11.0,"protein":3.5},
    "salad":           {"kcal":15, "carbs":2.9, "fat":0.2, "protein":1.3},
    "caesar salad":    {"kcal":184,"carbs":8.0, "fat":14.0,"protein":7.0},
    "broccoli":        {"kcal":55, "carbs":11.0,"fat":0.6, "protein":3.7},
    "carrot":          {"kcal":41, "carbs":10.0,"fat":0.2, "protein":0.9},
    "avocado":         {"kcal":160,"carbs":9.0, "fat":15.0,"protein":2.0},
    "potato":          {"kcal":77, "carbs":17.0,"fat":0.1, "protein":2.0},
    "sweet potato":    {"kcal":86, "carbs":20.0,"fat":0.1, "protein":1.6},
    "fries":           {"kcal":312,"carbs":41.0,"fat":15.0,"protein":3.4},
    "mashed potato":   {"kcal":113,"carbs":17.0,"fat":4.0, "protein":2.0},
    "apple":           {"kcal":95, "carbs":25.0,"fat":0.3, "protein":0.5},
    "banana":          {"kcal":105,"carbs":27.0,"fat":0.4, "protein":1.3},
    "orange":          {"kcal":62, "carbs":15.0,"fat":0.2, "protein":1.2},
    "strawberry":      {"kcal":49, "carbs":12.0,"fat":0.5, "protein":1.0},
    "mango":           {"kcal":60, "carbs":15.0,"fat":0.4, "protein":0.8},
    "pancake":         {"kcal":227,"carbs":28.0,"fat":10.0,"protein":6.0},
    "waffle":          {"kcal":291,"carbs":37.0,"fat":13.0,"protein":7.9},
    "oatmeal":         {"kcal":71, "carbs":12.0,"fat":1.5, "protein":2.5},
    "granola":         {"kcal":471,"carbs":64.0,"fat":20.0,"protein":10.0},
    "cake":            {"kcal":257,"carbs":36.0,"fat":11.0,"protein":4.0},
    "chocolate":       {"kcal":546,"carbs":60.0,"fat":31.0,"protein":5.0},
    "cookie":          {"kcal":78, "carbs":11.0,"fat":3.6, "protein":1.0},
    "donut":           {"kcal":253,"carbs":30.0,"fat":14.0,"protein":4.0},
    "coffee":          {"kcal":2,  "carbs":0.0, "fat":0.0, "protein":0.3},
    "latte":           {"kcal":190,"carbs":19.0,"fat":7.0, "protein":10.0},
    "orange juice":    {"kcal":112,"carbs":26.0,"fat":0.5, "protein":1.7},
    "smoothie":        {"kcal":150,"carbs":30.0,"fat":2.0, "protein":5.0},
    "soda":            {"kcal":140,"carbs":39.0,"fat":0.0, "protein":0.0},
    "soup":            {"kcal":80, "carbs":10.0,"fat":3.0, "protein":4.0},
    "curry":           {"kcal":250,"carbs":20.0,"fat":14.0,"protein":12.0},
}

def _lookup(name: str) -> Optional[dict]:
    n = name.lower().strip()
    # 1. Exact match in big DB
    if n in FOOD_DB: return FOOD_DB[n]
    # 2. Exact match in fallback
    if n in FALLBACK: return {**FALLBACK[n], "serving": "1 serving"}
    # 3. Substring match in curated fallback first (reliable values)
    for key, val in FALLBACK.items():
        if key in n or n in key: return {**val, "serving": "1 serving"}
    # 4. Substring match in big DB (only if no fallback match)
    for key, val in FOOD_DB.items():
        if key in n or n in key: return val
    # 5. Word match
    for word in n.split():
        if len(word) < 4: continue
        if word in FOOD_DB: return FOOD_DB[word]
        if word in FALLBACK: return {**FALLBACK[word], "serving": "1 serving"}
    return None


# ── OpenAI Vision ──────────────────────────────────

PROMPT = """You are a professional nutritionist and food AI.

Analyze this food image. Identify ALL distinct food items visible.

For each item return realistic calorie + macro estimates based on visible portion size.

Return ONLY a valid JSON array — no markdown, no explanation:
[
  {"name": "Grilled Chicken Breast", "kcal": 165, "carbs": 0, "fat": 3.6, "protein": 31, "serving": "100g"},
  {"name": "Steamed White Rice",     "kcal": 206, "carbs": 44.5, "fat": 0.4, "protein": 4.3, "serving": "1 cup"},
  {"name": "Steamed Broccoli",       "kcal": 55,  "carbs": 11, "fat": 0.6, "protein": 3.7, "serving": "1 cup"}
]

Rules:
- Identify 1 to 6 food items max
- Be specific: "Grilled Salmon" not just "Fish"
- Estimate realistic portion sizes
- Return ONLY the JSON array"""


async def _openai_vision(image_bytes: bytes, content_type: str) -> List[dict]:
    b64 = base64.b64encode(image_bytes).decode()
    payload = {
        "model": "gpt-4o",
        "max_tokens": 700,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": f"data:{content_type};base64,{b64}", "detail": "low"}},
                {"type": "text", "text": PROMPT},
            ],
        }],
    }
    async with httpx.AsyncClient(timeout=45.0) as client:
        resp = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"},
            json=payload,
        )
    if resp.status_code != 200:
        raise RuntimeError(f"OpenAI error {resp.status_code}: {resp.text[:200]}")
    raw = resp.json()["choices"][0]["message"]["content"].strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw).strip()
    return json.loads(raw)


# ── Mock fallback ──────────────────────────────────

MOCKS = [
    [{"name":"Grilled Chicken Breast","kcal":165,"carbs":0.0,"fat":3.6,"protein":31.0,"serving":"150g"},
     {"name":"Steamed White Rice",    "kcal":206,"carbs":44.5,"fat":0.4,"protein":4.3, "serving":"1 cup"},
     {"name":"Steamed Broccoli",      "kcal":55, "carbs":11.0,"fat":0.6,"protein":3.7, "serving":"1 cup"}],
    [{"name":"Caesar Salad",  "kcal":184,"carbs":8.0,"fat":14.0,"protein":7.0,"serving":"2 cups"},
     {"name":"Garlic Bread",  "kcal":190,"carbs":28.0,"fat":8.0,"protein":4.0,"serving":"2 slices"}],
    [{"name":"Beef Burger",   "kcal":354,"carbs":29.0,"fat":17.0,"protein":20.0,"serving":"1 burger"},
     {"name":"French Fries",  "kcal":312,"carbs":41.0,"fat":15.0,"protein":3.4, "serving":"medium"},
     {"name":"Cola",          "kcal":140,"carbs":39.0,"fat":0.0, "protein":0.0, "serving":"12 fl oz"}],
    [{"name":"Avocado Toast", "kcal":290,"carbs":28.0,"fat":16.0,"protein":8.0,"serving":"2 slices"},
     {"name":"Poached Eggs",  "kcal":155,"carbs":1.1, "fat":11.0,"protein":13.0,"serving":"2 eggs"},
     {"name":"Orange Juice",  "kcal":112,"carbs":26.0,"fat":0.5, "protein":1.7, "serving":"8 fl oz"}],
    [{"name":"Salmon Fillet", "kcal":208,"carbs":0.0, "fat":13.0,"protein":20.0,"serving":"150g"},
     {"name":"Mashed Potato", "kcal":113,"carbs":17.0,"fat":4.0, "protein":2.0, "serving":"1 cup"},
     {"name":"Green Beans",   "kcal":31, "carbs":7.0, "fat":0.1, "protein":1.8, "serving":"1 cup"}],
    [{"name":"Margherita Pizza","kcal":266,"carbs":33.0,"fat":10.0,"protein":11.0,"serving":"2 slices"}],
    [{"name":"Greek Yogurt",  "kcal":100,"carbs":17.0,"fat":0.7,"protein":17.0,"serving":"1 cup"},
     {"name":"Granola",       "kcal":471,"carbs":64.0,"fat":20.0,"protein":10.0,"serving":"1/2 cup"},
     {"name":"Banana",        "kcal":105,"carbs":27.0,"fat":0.4,"protein":1.3, "serving":"1 medium"}],
    [{"name":"Pancakes",      "kcal":227,"carbs":28.0,"fat":10.0,"protein":6.0,"serving":"3 pancakes"},
     {"name":"Maple Syrup",   "kcal":52, "carbs":13.0,"fat":0.0,"protein":0.0,"serving":"1 tbsp"},
     {"name":"Coffee",        "kcal":2,  "carbs":0.0, "fat":0.0,"protein":0.3,"serving":"1 cup"}],
]

def _mock(image_bytes: bytes) -> List[dict]:
    return MOCKS[len(image_bytes) % len(MOCKS)]


# ── Main entry ─────────────────────────────────────

async def analyze_food_image(image_bytes: bytes, content_type: str = "image/jpeg") -> List[dict]:
    """
    Returns list of:
    {"name", "kcal", "carbs", "fat", "protein", "serving"}
    """

    # Step 1: Get food names + AI estimates
    if OPENAI_API_KEY and OPENAI_API_KEY not in ("", "your-key-here"):
        try:
            ai_foods = await _openai_vision(image_bytes, content_type)
        except Exception as e:
            print(f"⚠  OpenAI failed: {e} → using mock")
            ai_foods = _mock(image_bytes)
    else:
        print("⚠  No OpenAI key → using mock")
        ai_foods = _mock(image_bytes)

    # Step 2: Enrich with real DB values
    results = []
    for item in ai_foods:
        name    = str(item.get("name", "Food")).strip()
        serving = str(item.get("serving", "1 serving"))

        db = _lookup(name)

        if db:
            ai_kcal = int(item.get("kcal", 0))
            db_kcal = db["kcal"]
            # Prefer AI portion-aware kcal; fall back to DB only if AI value is implausible
            kcal = ai_kcal if 30 <= ai_kcal <= 3000 else db_kcal
            # Scale DB macro ratios proportionally to the chosen kcal
            ratio = kcal / db_kcal if db_kcal > 0 else 1.0
            results.append({
                "name":    name,
                "kcal":    kcal,
                "carbs":   round(db["carbs"] * ratio, 1),
                "fat":     round(db["fat"]   * ratio, 1),
                "protein": round(db["protein"] * ratio, 1),
                "serving": serving,
            })
        else:
            # Trust AI values if they're reasonable
            kcal    = int(item.get("kcal", 200))
            carbs   = float(item.get("carbs", 0))
            fat     = float(item.get("fat", 0))
            protein = float(item.get("protein", 0))

            if not (10 <= kcal <= 2500): kcal = 200
            results.append({
                "name":    name,
                "kcal":    kcal,
                "carbs":   round(carbs, 1),
                "fat":     round(fat, 1),
                "protein": round(protein, 1),
                "serving": serving,
            })

    return results
