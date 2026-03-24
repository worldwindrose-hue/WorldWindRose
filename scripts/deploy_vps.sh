#!/usr/bin/env bash
# ============================================================
# ROSA OS v5 — VPS Deployment Script
# Supports: Hetzner Cloud, DigitalOcean, any Ubuntu 22.04 VPS
# ============================================================
set -euo pipefail

# ── CONFIGURATION ─────────────────────────────────────────────────────────
VPS_USER="${VPS_USER:-root}"
VPS_HOST="${VPS_HOST:-}"
VPS_PORT="${VPS_PORT:-22}"
REMOTE_DIR="${REMOTE_DIR:-/opt/rosa}"
DOMAIN="${DOMAIN:-}"  # optional: yourdomain.com

if [ -z "$VPS_HOST" ]; then
    echo "Usage: VPS_HOST=1.2.3.4 [VPS_USER=root] [DOMAIN=yourdomain.com] $0"
    exit 1
fi

ROSA_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SSH="ssh -p $VPS_PORT $VPS_USER@$VPS_HOST"
SCP="scp -P $VPS_PORT"

echo "🚀 Deploying ROSA OS to $VPS_USER@$VPS_HOST:$REMOTE_DIR"
echo ""

# ── REMOTE SETUP ──────────────────────────────────────────────────────────
echo "1️⃣  Setting up server..."
$SSH << 'REMOTE'
set -e
# Docker
if ! command -v docker &>/dev/null; then
    curl -fsSL https://get.docker.com | sh
    systemctl enable docker
    systemctl start docker
fi
# docker-compose
if ! command -v docker-compose &>/dev/null; then
    curl -SL https://github.com/docker/compose/releases/latest/download/docker-compose-linux-x86_64 -o /usr/local/bin/docker-compose
    chmod +x /usr/local/bin/docker-compose
fi
REMOTE
echo "   ✅ Server ready"

# ── SYNC CODE ─────────────────────────────────────────────────────────────
echo "2️⃣  Syncing code..."
$SSH "mkdir -p $REMOTE_DIR/memory"
rsync -avz --progress \
    --exclude=".git" \
    --exclude="__pycache__" \
    --exclude="*.pyc" \
    --exclude=".env" \
    --exclude="memory/*.db" \
    --exclude="memory/chroma" \
    -e "ssh -p $VPS_PORT" \
    "$ROSA_DIR/" "$VPS_USER@$VPS_HOST:$REMOTE_DIR/"
echo "   ✅ Code synced"

# ── SYNC ENV ──────────────────────────────────────────────────────────────
echo "3️⃣  Syncing .env..."
if [ -f "$ROSA_DIR/.env" ]; then
    $SCP -P $VPS_PORT "$ROSA_DIR/.env" "$VPS_USER@$VPS_HOST:$REMOTE_DIR/.env"
    echo "   ✅ .env synced"
else
    echo "   ⚠️  No .env found — create one on the server!"
fi

# ── DOCKER BUILD + DEPLOY ─────────────────────────────────────────────────
echo "4️⃣  Building and starting containers..."
$SSH << REMOTE
cd $REMOTE_DIR
docker-compose build --no-cache
docker-compose down --remove-orphans || true
docker-compose up -d
echo "   ✅ Containers started"
REMOTE

# ── OPTIONAL: SSL WITH CERTBOT ────────────────────────────────────────────
if [ -n "$DOMAIN" ]; then
    echo "5️⃣  Setting up SSL for $DOMAIN..."
    $SSH << REMOTE
apt-get install -y certbot nginx
certbot certonly --standalone -d $DOMAIN --non-interactive --agree-tos -m admin@$DOMAIN || true
# Create nginx config
cat > /etc/nginx/sites-available/rosa << 'NGINX'
server {
    listen 80;
    server_name $DOMAIN;
    return 301 https://\$server_name\$request_uri;
}
server {
    listen 443 ssl http2;
    server_name $DOMAIN;
    ssl_certificate /etc/letsencrypt/live/$DOMAIN/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/$DOMAIN/privkey.pem;
    location / {
        proxy_pass http://localhost:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
    }
}
NGINX
ln -sf /etc/nginx/sites-available/rosa /etc/nginx/sites-enabled/rosa
nginx -t && systemctl reload nginx
REMOTE
    echo "   ✅ SSL configured for $DOMAIN"
fi

# ── STATUS CHECK ──────────────────────────────────────────────────────────
echo ""
echo "5️⃣  Checking health..."
sleep 5
STATUS=$($SSH "curl -sf http://localhost:8000/health || echo 'FAILED'")
if echo "$STATUS" | grep -q "ok"; then
    echo "   ✅ ROSA OS is healthy!"
else
    echo "   ❌ Health check failed. Check logs:"
    echo "   $SSH 'cd $REMOTE_DIR && docker-compose logs --tail=50'"
    exit 1
fi

echo ""
echo "════════════════════════════════════"
echo "🎉 ROSA OS deployed successfully!"
if [ -n "$DOMAIN" ]; then
    echo "   URL: https://$DOMAIN"
else
    echo "   URL: http://$VPS_HOST:8000"
fi
echo ""
echo "   Useful commands:"
echo "   $SSH 'cd $REMOTE_DIR && docker-compose logs -f'"
echo "   $SSH 'cd $REMOTE_DIR && docker-compose restart rosa'"
echo "════════════════════════════════════"
