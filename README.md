# iCal — AI Calorie & Macro Tracker

> Snap a photo of any meal. Get instant calories, carbs, fat and protein. Share with friends.

**Live site:** https://naremanukiian.github.io/iCal  
**Backend API:** https://calorie-ai-backend-dyko.onrender.com

---

## What it does

- 📸 **Photo analysis** — Upload a meal photo, GPT-4o Vision identifies every food item
- 🔥 **Macro tracking** — Real calories, carbs, fat and protein from a 60,000-item food database
- 📊 **Daily dashboard** — Calorie ring, macro cards, weekly bar chart, streak counter
- 🤖 **AI meal suggestions** — ChatGPT generates personalized meal ideas with full recipes
- 👥 **Social feed** — Share meals publicly, follow users, like and save posts
- 🔍 **Explore** — Discover public meals from other users, filter by type or macros
- 🔒 **Privacy control** — Toggle any post between Public and Private at any time

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | Vanilla HTML / CSS / JS — GitHub Pages |
| Backend | FastAPI (Python 3.11) — Render |
| Database | PostgreSQL — Neon.tech |
| AI Vision | OpenAI GPT-4o Vision API |
| Food Data | 60,000-item JSON dataset |
| Auth | JWT + bcrypt |

---

## Project Structure

```
CalorieAI/
│
├── frontend/                   # Deployed to GitHub Pages
│   ├── index.html              # Landing page
│   ├── login.html              # Login page
│   ├── register.html           # Sign up page
│   ├── dashboard.html          # Main app (SPA)
│   ├── suggest.html            # AI meal suggestions
│   ├── style.css               # Full design system
│   └── script.js               # Shared utilities
│
├── backend/                    # Deployed to Render
│   ├── main.py                 # FastAPI routes
│   ├── social.py               # Social features (posts, feed, follow)
│   ├── analyzer.py             # GPT-4o + food DB lookup
│   ├── auth.py                 # JWT + bcrypt
│   ├── database.py             # PostgreSQL connection pool
│   ├── models.py               # Pydantic schemas
│   ├── download_dataset.py     # Downloads 60k food database
│   ├── requirements.txt        # Python dependencies
│   └── .env                    # Environment variables (never commit)
│
└── database/
    └── schema.sql              # Full DB schema (reference only)
```

---

## Environment Variables

Set these in **Render → Environment**:

| Variable | Value |
|---|---|
| `DATABASE_URL` | Your Neon PostgreSQL connection string |
| `OPENAI_API_KEY` | Your OpenAI API key |
| `JWT_SECRET` | Any long random string |
| `FOOD_DB_PATH` | `food_data.json` |

---

## API Endpoints

### Auth
| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/register` | Create account |
| `POST` | `/login` | Login, returns JWT token |
| `GET` | `/me` | Get current user profile |
| `PATCH` | `/me` | Update profile |

### Meals
| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/analyze` | Upload photo → get macros |
| `GET` | `/history` | Get meal history |
| `DELETE` | `/history/{id}` | Delete meal session |

### Social
| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/posts` | Share a meal as a post |
| `GET` | `/posts/feed` | Get social feed |
| `GET` | `/posts/explore` | Browse public posts |
| `GET` | `/posts/profile/{id}` | Get user's posts |
| `PATCH` | `/posts/{id}/status` | Toggle public/private |
| `DELETE` | `/posts/{id}` | Delete post |
| `POST` | `/posts/{id}/like` | Like a post |
| `DELETE` | `/posts/{id}/like` | Unlike a post |
| `POST` | `/posts/{id}/save` | Save a post |
| `DELETE` | `/posts/{id}/save` | Unsave a post |

### Users
| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/users/search?q=` | Search users by username |
| `GET` | `/users/{id}/profile` | View user profile |
| `POST` | `/follow/{id}` | Follow a user |
| `DELETE` | `/follow/{id}` | Unfollow a user |

### AI
| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/suggest` | Generate AI meal idea via ChatGPT |

---

## Database Schema

```
users           — id, email, username, password_hash, bio, weight, goal, calorie_goal
meal_sessions   — id, user_id, meal_type, total_calories, total_carbs, total_fat, total_protein
food_logs       — id, user_id, session_id, food_name, calories, carbs, fat, protein
posts           — id, user_id, session_id, caption, status (public/private), macros, items_json
follows         — follower_id, following_id
likes           — user_id, post_id
saves           — user_id, post_id
```

---

## How to Deploy

### Backend (Render)
1. Push code to GitHub
2. Go to **render.com** → New Web Service → connect your repo
3. Set Root Directory: `backend`
4. Build command: `pip install -r requirements.txt && python download_dataset.py`
5. Start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
6. Add all environment variables
7. Deploy — tables are created automatically on startup

### Frontend (GitHub Pages)
1. Go to **GitHub repo → Settings → Pages**
2. Source: Deploy from branch `main`, folder `/` (root)
3. Save — site is live at `https://yourusername.github.io/CalorieAI`

---

## How to Push Updates

```bash
# Extract downloaded zip
powershell.exe -command "Expand-Archive -Path 'C:\Users\narem\Downloads\files.zip' -DestinationPath 'C:\Users\narem\Downloads\update' -Force"

# Copy files
cd /mnt/c/Users/narem/workspace/CalorieAI
cp /mnt/c/Users/narem/Downloads/update/*.html .
cp /mnt/c/Users/narem/Downloads/update/*.css .
cp /mnt/c/Users/narem/Downloads/update/*.js .
cp /mnt/c/Users/narem/Downloads/update/*.py backend/

# Push
git add .
git commit -m "Your update description"
git push
```

---

## Features by Phase

| Phase | Features |
|---|---|
| **v1** | Photo analysis, calorie tracking, macro breakdown, user auth |
| **v2** | Bottom nav, analytics page, profile page, clickable date history, weekly charts |
| **v3 (current)** | Social feed, explore, follow system, post sharing, like/save, user search, post privacy toggle, delete posts, AI meal suggestions via ChatGPT |

---

## Known Limitations

- **Render free tier** sleeps after 15 min of inactivity — first request after sleep takes ~30 seconds. The app automatically retries.
- **Explore** only shows meals that have been shared publicly. Log a meal → Share → set Public to populate it.
- **AI suggestions** use your OpenAI API key stored in Render env vars — no key is ever exposed to the browser.

---

## License

MIT — build on it freely.
