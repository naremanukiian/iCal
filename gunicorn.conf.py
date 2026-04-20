"""
gunicorn.conf.py — Production Gunicorn configuration
Start: gunicorn -c gunicorn.conf.py run:app
"""
import multiprocessing
import os

# ── Binding ───────────────────────────────────────────
bind    = "127.0.0.1:8000"       # NGINX proxies to this
backlog = 2048

# ── Workers ───────────────────────────────────────────
# Formula: (2 × CPU cores) + 1
workers     = 2  # t3.micro safe (1 GB RAM)
worker_class = "sync"            # Use "gevent" if you add async routes
threads      = 2
timeout      = 120               # seconds before killing a worker
keepalive    = 5

# ── Logging ───────────────────────────────────────────
loglevel       = "info"
accesslog      = "/var/log/ical/access.log"
errorlog       = "/var/log/ical/error.log"
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# ── Process ───────────────────────────────────────────
proc_name   = "ical"
pidfile     = "/var/run/ical/gunicorn.pid"
daemon      = False              # systemd manages the process

# ── Security ─────────────────────────────────────────
limit_request_line   = 8190
limit_request_fields = 100
forwarded_allow_ips  = "127.0.0.1"  # trust NGINX X-Forwarded-For

# ── Worker lifecycle ──────────────────────────────────
max_requests          = 1000    # restart worker after N requests (prevent memory leaks)
max_requests_jitter   = 100
preload_app           = True    # load app before forking (saves memory)

def on_starting(server):
    os.makedirs("/var/log/ical",  exist_ok=True)
    os.makedirs("/var/run/ical",  exist_ok=True)
    print("🚀  Gunicorn starting — iCal production server")

def worker_exit(server, worker):
    print(f"Worker {worker.pid} exited")
