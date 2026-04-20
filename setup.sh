#!/bin/bash
# ════════════════════════════════════════════════════════
#  iCal — EC2 Ubuntu 22.04 LTS Setup Script
#
#  Run as ubuntu user:
#    chmod +x setup.sh && ./setup.sh
#
#  This script will:
#    1. Install Python 3.11, pip, nginx
#    2. Clone the GitHub repo
#    3. Set up virtualenv + install dependencies
#    4. Download the 60k food database
#    5. Configure systemd service
#    6. Configure NGINX
#    7. Open firewall ports
#    8. Start everything
# ════════════════════════════════════════════════════════
set -e  # Exit on any error

# ── Colours ──────────────────────────────────────────
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

info()    { echo -e "${GREEN}[INFO]${NC} $1"; }
warn()    { echo -e "${YELLOW}[WARN]${NC} $1"; }
section() { echo -e "\n${GREEN}═══ $1 ═══${NC}"; }

# ── Config — edit these before running ───────────────
APP_DIR="/home/ubuntu/ical"
GITHUB_REPO="https://github.com/naremanukiian/CalorieAI.git"
PYTHON_VERSION="python3.11"
SERVICE_NAME="ical"

# ════════════════════════════════════════════════════════
section "1. System updates"
sudo apt-get update -y
sudo apt-get upgrade -y

# ════════════════════════════════════════════════════════
section "2. Install dependencies"
sudo apt-get install -y \
    python3.11 python3.11-venv python3.11-dev \
    python3-pip \
    nginx \
    git \
    curl \
    ufw \
    libpq-dev \
    build-essential \
    certbot python3-certbot-nginx

info "Python version: $(python3.11 --version)"
info "NGINX version: $(nginx -v 2>&1)"

# ════════════════════════════════════════════════════════

section "2.5. Add swap space (t3.micro)"
if [ ! -f /swapfile ]; then
    sudo fallocate -l 2G /swapfile
    sudo chmod 600 /swapfile
    sudo mkswap /swapfile
    sudo swapon /swapfile
    echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
    info "2GB swap added"
else
    info "Swap already exists — skipping"
fi

section "3. Clone repository"
if [ -d "$APP_DIR" ]; then
    warn "Directory $APP_DIR already exists — pulling latest"
    cd "$APP_DIR" && git pull
else
    git clone "$GITHUB_REPO" "$APP_DIR"
fi
cd "$APP_DIR"
info "Repo ready at $APP_DIR"

# ════════════════════════════════════════════════════════
section "4. Create virtual environment"
$PYTHON_VERSION -m venv "$APP_DIR/venv"
source "$APP_DIR/venv/bin/activate"
pip install --upgrade pip wheel
pip install -r "$APP_DIR/requirements.txt"
info "Dependencies installed"

# ════════════════════════════════════════════════════════
section "5. Download 60k food database"
if [ ! -f "$APP_DIR/food_data.json" ]; then
    info "Downloading food database..."
    python3 "$APP_DIR/download_dataset.py" || warn "Download failed — manual download may be needed"
else
    info "food_data.json already exists — skipping"
fi

# ════════════════════════════════════════════════════════
section "6. Create .env file"
if [ ! -f "$APP_DIR/.env" ]; then
    cp "$APP_DIR/.env.example" "$APP_DIR/.env"
    warn "Created .env from template."
    warn "IMPORTANT: Edit $APP_DIR/.env with your real values before continuing!"
    warn "  nano $APP_DIR/.env"
    warn "Then run: sudo systemctl restart $SERVICE_NAME"
else
    info ".env already exists — skipping"
fi

# ════════════════════════════════════════════════════════
section "7. Create log + pid directories"
sudo mkdir -p /var/log/ical /var/run/ical
sudo chown ubuntu:www-data /var/log/ical /var/run/ical
sudo chmod 775 /var/log/ical /var/run/ical

# ════════════════════════════════════════════════════════
section "8. Install systemd service"
sudo cp "$APP_DIR/ical.service" /etc/systemd/system/ical.service
sudo systemctl daemon-reload
sudo systemctl enable $SERVICE_NAME
info "Service installed: $SERVICE_NAME"

# ════════════════════════════════════════════════════════
section "9. Configure NGINX"
sudo cp "$APP_DIR/nginx.conf" /etc/nginx/sites-available/ical
sudo ln -sf /etc/nginx/sites-available/ical /etc/nginx/sites-enabled/ical
sudo rm -f /etc/nginx/sites-enabled/default

# Test config
sudo nginx -t && info "NGINX config OK" || { echo "NGINX config error!"; exit 1; }

# ════════════════════════════════════════════════════════
section "10. Configure firewall"
sudo ufw allow ssh
sudo ufw allow 'Nginx Full'
sudo ufw --force enable
info "Firewall configured: SSH + HTTP + HTTPS"

# ════════════════════════════════════════════════════════
section "11. Set permissions"
sudo chown -R ubuntu:www-data "$APP_DIR"
sudo chmod -R 755 "$APP_DIR/app/static"
sudo chmod 640 "$APP_DIR/.env"

# ════════════════════════════════════════════════════════
section "12. Start services"
sudo systemctl restart nginx
info "NGINX started"

# Only start app if .env is configured
if grep -q "YOUR_PASSWORD" "$APP_DIR/.env" 2>/dev/null; then
    warn "⚠  .env still has placeholder values."
    warn "   Edit: nano $APP_DIR/.env"
    warn "   Then: sudo systemctl start $SERVICE_NAME"
else
    sudo systemctl start $SERVICE_NAME
    sleep 2
    if sudo systemctl is-active --quiet $SERVICE_NAME; then
        info "iCal app started"
    else
        warn "App failed to start. Check logs:"
        warn "  sudo journalctl -u $SERVICE_NAME -n 50"
    fi
fi

# ════════════════════════════════════════════════════════
section "Setup complete"
PUBLIC_IP=$(curl -s http://169.254.169.254/latest/meta-data/public-ipv4 2>/dev/null || echo "YOUR_EC2_IP")
echo ""
echo -e "${GREEN}Your app is live at:${NC}"
echo -e "  http://$PUBLIC_IP"
echo ""
echo -e "${YELLOW}Next steps:${NC}"
echo "  1. Edit .env:     nano $APP_DIR/.env"
echo "  2. Restart app:   sudo systemctl restart $SERVICE_NAME"
echo "  3. View logs:     sudo journalctl -u $SERVICE_NAME -f"
echo "  4. NGINX logs:    sudo tail -f /var/log/nginx/ical_access.log"
echo "  5. Add SSL:       sudo certbot --nginx -d yourdomain.com"
echo ""
echo -e "${GREEN}Management commands:${NC}"
echo "  sudo systemctl status  $SERVICE_NAME"
echo "  sudo systemctl restart $SERVICE_NAME"
echo "  sudo systemctl stop    $SERVICE_NAME"
echo ""
