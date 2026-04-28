# iCal — AI Calorie Tracker
### Flask + Gunicorn + NGINX on AWS EC2

> Snap a meal photo → GPT-4o Vision identifies every food item → instant calories, carbs, fat and protein. Share to your social feed, explore what others are eating, and track weekly trends.

---

## Features

- **Photo → Nutrition in seconds** — GPT-4o Vision + 60 k-item food database
- **AI Meal Suggestions** — text-based meal logging without a photo (`/suggest`)
- **Social Feed & Explore** — post meals, follow friends, like and save posts
- **Weekly Analytics** — bar chart, macro breakdown, streak tracking
- **iPhone-style PWA** — Dynamic Island frame, bottom nav, bottom sheets
- **Offline-ready** — service worker caches assets for repeat visits

---

## Architecture

```
Internet
    │
    ▼
[NGINX :80/:443]          ← reverse proxy, static files, SSL termination
    │
    ├── /static/*  → served directly from disk (30-day cache)
    │
    └── /api/* + /  → proxy to Gunicorn :8000
                            │
                            └── Flask app (4+ workers)
                                    │
                                    ├── PostgreSQL (Neon.tech serverless)
                                    └── OpenAI GPT-4o Vision API
```

---

## Project Structure

```
ical/
├── app/
│   ├── __init__.py          # Flask app factory
│   ├── routes/
│   │   ├── auth.py          # /api/register  /api/login  /api/me
│   │   ├── meals.py         # /api/analyze  /api/log  /api/history  /api/suggest
│   │   ├── social.py        # /api/posts  /api/feed  /api/follow  /api/explore
│   │   └── pages.py         # HTML page routes (/ /dashboard etc.)
│   ├── services/
│   │   ├── database.py      # PostgreSQL connection pool (Neon-safe)
│   │   ├── auth.py          # JWT + bcrypt + @require_auth decorator
│   │   └── analyzer.py      # GPT-4o Vision + 60k food database lookup
│   ├── templates/           # Jinja2 HTML (server-rendered)
│   │   ├── base.html        # iPhone 15 Pro frame + PWA meta + cache busting
│   │   ├── index.html       # Landing page
│   │   ├── login.html
│   │   ├── register.html
│   │   ├── dashboard.html   # Main SPA (Home / Feed / Explore / Analytics / Profile)
│   │   └── suggest.html     # AI text-based meal suggestion UI
│   └── static/
│       ├── css/
│       │   ├── style.css    # Design system (dark tokens, components, sheets)
│       │   └── frame.css    # iPhone 15 Pro frame (desktop only)
│       ├── js/script.js     # Shared utilities (api(), toast, setLoading, etc.)
│       ├── manifest.json    # PWA manifest
│       ├── sw.js            # Service worker (offline support)
│       └── icons/           # App icons (192×192, 512×512)
├── run.py                   # Gunicorn entry point
├── gunicorn.conf.py         # Workers, logging, timeouts
├── nginx.conf               # Reverse proxy config
├── ical.service             # systemd service unit
├── setup.sh                 # One-command EC2 setup
├── requirements.txt
├── download_dataset.py      # Downloads 60k food JSON database
└── .env.example             # Environment variable template
```

---

## Quick Start — AWS EC2

### Step 1 — Launch EC2 instance

1. **AWS Console → EC2 → Launch Instance**
2. AMI: **Ubuntu Server 22.04 LTS (64-bit)**
3. Instance type: **t3.small** (min) or **t3.medium** (recommended)
4. Create or select a key pair
5. Security Group — open these ports:

| Port | Protocol | Source | Purpose |
|------|----------|--------|---------|
| 22   | TCP | Your IP | SSH |
| 80   | TCP | 0.0.0.0/0 | HTTP |
| 443  | TCP | 0.0.0.0/0 | HTTPS (after SSL) |

6. Storage: **20 GB** minimum

---

### Step 2 — SSH in

```bash
chmod 400 your-key.pem
ssh -i your-key.pem ubuntu@YOUR_EC2_PUBLIC_IP
```

---

### Step 3 — Upload the project

**From GitHub (recommended)**
```bash
git clone https://github.com/naremanukiian/iCal.git
cd iCal
```

**Or from local machine**
```bash
scp -i your-key.pem -r ./ical/* ubuntu@YOUR_EC2_IP:/home/ubuntu/ical/
```

---

### Step 4 — Run the setup script

```bash
chmod +x setup.sh
./setup.sh
```

This automatically:
- Installs Python 3.11, pip, NGINX
- Creates a virtualenv and installs dependencies (including Pillow)
- Downloads the 60 k food database
- Configures systemd + NGINX
- Starts everything

---

### Step 5 — Configure environment variables

```bash
nano /home/ubuntu/ical/.env
```

```env
DATABASE_URL=postgresql://neondb_owner:YOUR_PASS@ep-xxx.neon.tech/neondb?sslmode=require
OPENAI_API_KEY=sk-...
JWT_SECRET=generate-a-long-random-string-here
FOOD_DB_PATH=/home/ubuntu/ical/food_data.json
```

Generate a secure JWT secret:
```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

```bash
sudo systemctl restart ical
```

---

### Step 6 — Verify

```bash
sudo systemctl status ical
curl http://localhost:8000/api/health   # → {"status":"healthy","db":"connected"}
sudo nginx -t && sudo systemctl status nginx
sudo journalctl -u ical -f
```

Open `http://YOUR_EC2_PUBLIC_IP` in a browser.

---

### Step 7 — SSL (optional but recommended)

```bash
# Point your domain A record to the EC2 IP first, then:
sudo certbot --nginx -d yourdomain.com -d www.yourdomain.com
```

---

## API Reference

All endpoints are prefixed with `/api/`.

### Auth

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| POST | `/register` | — | Create account |
| POST | `/login` | — | Login → JWT |
| GET | `/me` | JWT | Get own profile |
| PATCH | `/me` | JWT | Update profile / goals |

### Meals

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| POST | `/analyze` | JWT | Photo upload → macros (multipart) |
| POST | `/log` | JWT | Log AI-suggested foods without a photo |
| GET | `/history` | JWT | Meal session history |
| DELETE | `/history/<id>` | JWT | Delete a session |
| POST | `/suggest` | JWT | AI text-based meal suggestion |

#### `POST /api/log` body

```json
{
  "meal_type": "lunch",
  "foods": [
    { "name": "Grilled Chicken", "kcal": 280, "carbs": 0, "fat": 6, "protein": 53, "serving": "200g" }
  ]
}
```

### Social

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| POST | `/posts` | JWT | Share a meal to profile |
| GET | `/posts/feed` | JWT | Posts from followed users |
| GET | `/posts/explore` | JWT | Public posts (filter, search) |
| GET | `/posts/profile/<id>` | JWT | A user's posts |
| GET | `/posts/saved` | JWT | Your saved posts |
| DELETE | `/posts/<id>` | JWT | Delete own post |
| POST | `/posts/<id>/like` | JWT | Like |
| DELETE | `/posts/<id>/like` | JWT | Unlike |
| POST | `/posts/<id>/save` | JWT | Save |
| DELETE | `/posts/<id>/save` | JWT | Unsave |
| GET | `/users/search?q=` | JWT | Search users by username |
| GET | `/users/<id>/profile` | JWT | User profile + stats |
| POST | `/follow/<id>` | JWT | Follow a user |
| DELETE | `/follow/<id>` | JWT | Unfollow a user |

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABASE_URL` | Yes | PostgreSQL (Neon) connection string |
| `OPENAI_API_KEY` | Yes | OpenAI key for GPT-4o Vision |
| `JWT_SECRET` | Yes | Random secret for signing tokens |
| `FOOD_DB_PATH` | Yes | Absolute path to `food_data.json` |
| `FLASK_DEBUG` | No | `true` for development only |

---

## Management Commands

```bash
# App lifecycle
sudo systemctl start   ical
sudo systemctl stop    ical
sudo systemctl restart ical
sudo systemctl status  ical

# Live logs
sudo journalctl -u ical -f
sudo tail -f /var/log/nginx/ical_access.log

# NGINX
sudo nginx -t           # validate config
sudo systemctl reload nginx

# Deploy after git push
cd /home/ubuntu/ical && git pull && pip install -r requirements.txt && sudo systemctl restart ical

# One-liner alias
echo 'alias deploy="cd /home/ubuntu/ical && git pull && sudo systemctl restart ical"' >> ~/.bashrc
source ~/.bashrc
```

---

## Performance

On **t3.small** (2 vCPU, 2 GB RAM):
- Gunicorn workers: `(2×2)+1 = 5`
- Static assets served by NGINX (zero Python overhead)
- Gzip on all text responses
- 30-day cache on `/static/*`
- PostgreSQL pool: 0–20 connections (Neon-safe idle reconnect)

Upgrade to **t3.medium** for > 50 concurrent users.

---

## Troubleshooting

**App won't start**
```bash
sudo journalctl -u ical -n 50 --no-pager
# Common causes: wrong DATABASE_URL, missing .env, import error
```

**502 Bad Gateway**
```bash
sudo systemctl start ical
sudo ss -tlnp | grep 8000   # confirm Gunicorn is listening
```

**DB health returns `connection already closed`**  
Neon serverless closes idle TCP connections. The app automatically detects stale connections and reconnects — no action needed. If it persists, restart: `sudo systemctl restart ical`.

**Food database missing**
```bash
cd /home/ubuntu/ical && source venv/bin/activate && python download_dataset.py
sudo systemctl restart ical
```

**Out of memory (t3.micro)**
```bash
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile && sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

**Login inputs appear white / text invisible**  
Fixed — caused by browser autofill overriding input background. The CSS now uses the `:-webkit-autofill` box-shadow trick and `color-scheme: dark` to force the dark theme.
