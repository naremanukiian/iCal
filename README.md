# 🍎 CalorieAI v2 — AI Food Calorie Tracker

> GPT-4o Vision + 60,000-item food database + PostgreSQL + JWT auth

---

## ⚡ Quick Start (5 minutes)

### Step 1 — Get a free PostgreSQL database (Neon.tech)
1. Go to **https://neon.tech** → Sign up free (no credit card)
2. Create a project named `calorieai`
3. Copy your connection string — looks like:
   ```
   postgresql://user:pass@ep-something.us-east-2.aws.neon.tech/neondb?sslmode=require
   ```
4. In the Neon dashboard → **SQL Editor** → run the contents of `db/schema.sql`

### Step 2 — Configure the backend
```bash
cd backend
# The .env file is already filled in — just update DATABASE_URL:
nano .env    # or open in any text editor
```
Set `DATABASE_URL` to your Neon connection string.

### Step 3 — Install Python dependencies
```bash
cd backend

# Create virtual environment
python -m venv venv
source venv/bin/activate        # Mac/Linux
venv\Scripts\activate           # Windows

pip install -r requirements.txt
```

### Step 4 — Download the food database
```bash
# Still in backend/ with venv active:
python download_dataset.py
```
This downloads `food_data.json` (~15 MB, 60,000 foods) from GitHub.

### Step 5 — Run the backend
```bash
uvicorn main:app --reload --port 8000
```

You should see:
```
✅  Food database loaded: 60,000 items from 'food_data.json'
✅  Database tables ready.
🚀  CalorieAI API is live at http://localhost:8000
📖  Swagger docs:  http://localhost:8000/docs
```

### Step 6 — Run the frontend
Open a second terminal:
```bash
cd frontend
python -m http.server 3000
```
Open **http://localhost:3000** in your browser.

---

## 📁 Project Structure

```
calorie-ai/
├── frontend/
│   ├── index.html       ← Landing page
│   ├── login.html       ← Login
│   ├── register.html    ← Registration
│   ├── dashboard.html   ← Main app
│   ├── style.css        ← Complete design system
│   └── script.js        ← Shared utilities
│
├── backend/
│   ├── main.py              ← FastAPI app + all routes
│   ├── auth.py              ← JWT + bcrypt
│   ├── database.py          ← PostgreSQL pool (Neon-compatible)
│   ├── models.py            ← Pydantic schemas
│   ├── analyzer.py          ← GPT-4o Vision + 60k food DB
│   ├── download_dataset.py  ← One-click dataset downloader
│   ├── food_data.json       ← 60k food database (after download)
│   ├── requirements.txt
│   └── .env                 ← Your config (never commit this!)
│
└── db/
    └── schema.sql       ← Database schema
```

---

## 🔌 API Endpoints

| Method | Path              | Auth | Description                     |
|--------|-------------------|------|---------------------------------|
| GET    | /                 | No   | Health check                    |
| GET    | /health           | No   | DB connectivity check           |
| POST   | /register         | No   | Create account                  |
| POST   | /login            | No   | Login, get JWT                  |
| GET    | /me               | Yes  | Get user profile                |
| POST   | /analyze          | Yes  | Upload image → get calories     |
| GET    | /history          | Yes  | Get meal history + today total  |
| DELETE | /history/{id}     | Yes  | Delete a meal session           |

**Auth:** Send `Authorization: Bearer <token>` header.

---

## 🧠 How the AI pipeline works

1. **Image upload** → sent to GPT-4o Vision API
2. **GPT-4o** → identifies food items + estimates portion sizes
3. **60k food database** → looks up real calorie values by name
4. **Fallback** → if not found in DB, uses AI's estimate (if reasonable)
5. **Result saved** → to PostgreSQL with full meal session

---

## 🔧 Troubleshooting

| Problem | Fix |
|---------|-----|
| `Cannot connect to server` | Start backend: `uvicorn main:app --reload --port 8000` |
| `Database connection error` | Check `DATABASE_URL` in `.env` |
| `sslmode required` error | Add `?sslmode=require` to your DATABASE_URL |
| `food_data.json not found` | Run `python download_dataset.py` in `backend/` |
| OpenAI error 401 | Check your `OPENAI_API_KEY` in `.env` |
| CORS error in browser | Make sure backend is on port 8000 and `API_BASE` in script.js matches |
| Port 3000 busy | Use `python -m http.server 3001`, open `http://localhost:3001` |

---

## 🔒 Security Note

**Your OpenAI API key is in `.env`** — never commit this file to GitHub.
Add `.env` to your `.gitignore`:
```
echo ".env" >> .gitignore
```
