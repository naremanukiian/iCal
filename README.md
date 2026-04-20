# iCal — AI Calorie Tracker
### Flask + Gunicorn + NGINX on AWS EC2

> Snap a meal photo → GPT-4o identifies every food item → instant calories, carbs, fat and protein.

---

## Architecture

```
Internet
    │
    ▼
[NGINX :80/:443]          ← reverse proxy, static files, SSL
    │
    ├── /static/*  → served directly from disk (fast, cached)
    │
    └── /api/* + /  → proxy to Gunicorn :8000
                            │
                            └── Flask app (4+ workers)
                                    │
                                    ├── PostgreSQL (Neon.tech)
                                    └── OpenAI GPT-4o API
```

---

## Project Structure

```
ical/
├── app/
│   ├── __init__.py          # Flask app factory
│   ├── routes/
│   │   ├── auth.py          # /api/register  /api/login  /api/me
│   │   ├── meals.py         # /api/analyze   /api/history  /api/suggest
│   │   ├── social.py        # /api/posts     /api/feed     /api/follow
│   │   └── pages.py         # HTML page routes (/ /dashboard etc.)
│   ├── services/
│   │   ├── database.py      # PostgreSQL connection pool
│   │   ├── auth.py          # JWT + bcrypt + @require_auth decorator
│   │   └── analyzer.py      # GPT-4o Vision + 60k food database
│   ├── templates/           # Jinja2 HTML (served by Flask)
│   │   ├── base.html        # iPhone 17 Pro frame + PWA meta
│   │   ├── index.html       # Landing page
│   │   ├── login.html
│   │   ├── register.html
│   │   ├── dashboard.html   # Main SPA (all 5 tabs)
│   │   └── suggest.html     # AI meal suggestions
│   └── static/
│       ├── css/
│       │   ├── style.css    # Design system (tokens, components)
│       │   └── frame.css    # iPhone 17 Pro frame (desktop only)
│       ├── js/script.js     # Shared utilities (api(), toast, etc.)
│       ├── manifest.json    # PWA manifest
│       ├── sw.js            # Service worker (offline support)
│       └── icons/           # App icons (192×192, 512×512)
├── run.py                   # Gunicorn entry point
├── gunicorn.conf.py         # Workers, logging, timeouts
├── nginx.conf               # Reverse proxy config
├── ical.service             # systemd service unit
├── setup.sh                 # One-command EC2 setup
├── requirements.txt
├── download_dataset.py      # Downloads 60k food database
└── .env.example             # Environment variable template
```

---

## Quick Start — AWS EC2

### Step 1 — Launch EC2 instance

1. Go to **AWS Console → EC2 → Launch Instance**
2. Choose **Ubuntu Server 22.04 LTS (64-bit)**
3. Instance type: **t3.small** (minimum) or **t3.medium** (recommended)
4. Key pair: create or select one
5. Security Group — open these ports:

| Port | Protocol | Source | Purpose |
|------|----------|--------|---------|
| 22   | TCP | Your IP | SSH |
| 80   | TCP | 0.0.0.0/0 | HTTP |
| 443  | TCP | 0.0.0.0/0 | HTTPS (after SSL) |

6. Storage: **20 GB** minimum
7. Launch the instance

---

### Step 2 — SSH into your instance

```bash
chmod 400 your-key.pem
ssh -i your-key.pem ubuntu@YOUR_EC2_PUBLIC_IP
```

---

### Step 3 — Upload your project

**Option A — from GitHub (recommended)**
```bash
# On EC2, edit setup.sh first to set your repo URL
# Then just run it:
curl -sSL https://raw.githubusercontent.com/YOUR_USERNAME/YOUR_REPO/main/setup.sh | bash
```

**Option B — upload from local machine**
```bash
# From your local machine:
scp -i your-key.pem -r ./ical-ec2/* ubuntu@YOUR_EC2_IP:/home/ubuntu/ical/
```

---

### Step 4 — Run the setup script

```bash
cd /home/ubuntu/ical
chmod +x setup.sh
./setup.sh
```

This automatically:
- Installs Python 3.11, pip, NGINX
- Creates a virtualenv
- Installs all Python dependencies
- Downloads the 60k food database
- Configures systemd + NGINX
- Opens firewall ports
- Starts everything

---

### Step 5 — Configure environment variables

```bash
nano /home/ubuntu/ical/.env
```

Fill in:
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

Restart the app:
```bash
sudo systemctl restart ical
```

---

### Step 6 — Verify it's running

```bash
# Check app status
sudo systemctl status ical

# Health check
curl http://localhost:8000/api/health

# Check NGINX
sudo nginx -t && sudo systemctl status nginx

# View logs live
sudo journalctl -u ical -f
```

Open your browser: `http://YOUR_EC2_PUBLIC_IP`

---

### Step 7 — Add SSL (HTTPS) — optional but recommended

```bash
# Point your domain's A record to your EC2 IP first, then:
sudo certbot --nginx -d yourdomain.com -d www.yourdomain.com

# Auto-renewal is set up automatically
sudo systemctl status certbot.timer
```

Then update `nginx.conf` to uncomment the SSL + redirect blocks.

---

## Management Commands

```bash
# App service
sudo systemctl start   ical
sudo systemctl stop    ical
sudo systemctl restart ical
sudo systemctl status  ical

# Live logs
sudo journalctl -u ical -f
sudo tail -f /var/log/ical/access.log
sudo tail -f /var/log/nginx/ical_access.log

# NGINX
sudo nginx -t                   # test config
sudo systemctl reload nginx     # reload without downtime
sudo systemctl restart nginx    # full restart

# Deploy new code (after git push)
cd /home/ubuntu/ical
git pull
source venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart ical

# Create a deploy alias
echo 'alias deploy="cd /home/ubuntu/ical && git pull && sudo systemctl restart ical"' >> ~/.bashrc
source ~/.bashrc
# Then just run: deploy
```

---

## API Endpoints

All endpoints are prefixed with `/api/`.

### Auth
| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| POST | `/api/register` | — | Create account |
| POST | `/api/login` | — | Login, get JWT |
| GET | `/api/me` | JWT | Get profile |
| PATCH | `/api/me` | JWT | Update profile |

### Meals
| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| POST | `/api/analyze` | JWT | Upload photo → macros |
| GET | `/api/history` | JWT | Meal history |
| DELETE | `/api/history/<id>` | JWT | Delete session |
| POST | `/api/suggest` | JWT | AI meal suggestion |

### Social
| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| POST | `/api/posts` | JWT | Share a meal |
| GET | `/api/posts/feed` | JWT | Social feed |
| GET | `/api/posts/explore` | JWT | Browse public posts |
| GET | `/api/posts/profile/<id>` | JWT | User's posts |
| PATCH | `/api/posts/<id>/status` | JWT | Toggle public/private |
| DELETE | `/api/posts/<id>` | JWT | Delete post |
| POST | `/api/posts/<id>/like` | JWT | Like |
| DELETE | `/api/posts/<id>/like` | JWT | Unlike |
| POST | `/api/posts/<id>/save` | JWT | Save |
| DELETE | `/api/posts/<id>/save` | JWT | Unsave |
| GET | `/api/users/search?q=` | JWT | Search users |
| GET | `/api/users/<id>/profile` | JWT | User profile |
| POST | `/api/follow/<id>` | JWT | Follow user |
| DELETE | `/api/follow/<id>` | JWT | Unfollow user |

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABASE_URL` | Yes | PostgreSQL connection string |
| `OPENAI_API_KEY` | Yes | OpenAI key for GPT-4o |
| `JWT_SECRET` | Yes | Secret for signing tokens |
| `FOOD_DB_PATH` | Yes | Path to food_data.json |
| `FLASK_DEBUG` | No | Set `true` for dev only |

---

## Performance

On a **t3.small** (2 vCPU, 2 GB RAM):
- Gunicorn workers: `(2×2)+1 = 5`
- Static files served by NGINX (no Python overhead)
- Gzip compression on all text assets
- 30-day cache headers on static assets
- Connection pool: 2–20 PostgreSQL connections

Upgrade to **t3.medium** if you expect > 50 concurrent users.

---

## Troubleshooting

**App won't start**
```bash
sudo journalctl -u ical -n 50 --no-pager
# Usually: wrong DATABASE_URL or missing .env
```

**502 Bad Gateway**
```bash
# Gunicorn not running
sudo systemctl start ical
# Or check if port 8000 is in use
sudo ss -tlnp | grep 8000
```

**Food database missing**
```bash
cd /home/ubuntu/ical
source venv/bin/activate
python download_dataset.py
sudo systemctl restart ical
```

**Permission errors**
```bash
sudo chown -R ubuntu:www-data /home/ubuntu/ical
sudo chmod -R 755 /home/ubuntu/ical/app/static
```

**Out of memory (t3.micro)**
```bash
# Add swap space
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```
