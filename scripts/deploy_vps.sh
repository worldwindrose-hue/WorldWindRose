#!/usr/bin/env bash
# ============================================================
# ROSA OS — One-Command VPS Deployment (v6)
# Usage: ./scripts/deploy_vps.sh user@your-vps.com [yourdomain.com]
# ============================================================

set -euo pipefail

VPS="${1:-${ROSA_VPS:-}}"
DOMAIN="${2:-${ROSA_DOMAIN:-}}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
REMOTE_DIR="/opt/rosa"

if [ -z "$VPS" ]; then
    echo "Usage: $0 user@vps.host [domain.com]"
    echo "Or set ROSA_VPS environment variable"
    exit 1
fi

echo ""
echo "🌹 ================================================"
echo "   ROSA OS v6 — Deploying to $VPS"
[ -n "$DOMAIN" ] && echo "   Domain: $DOMAIN"
echo "🌹 ================================================"
echo ""

echo "📁 Preparing remote..."
ssh "$VPS" "mkdir -p $REMOTE_DIR/memory $REMOTE_DIR/memory/logs"

echo "📤 Syncing code..."
rsync -avz --progress \
    --exclude ".git" --exclude "memory/*.db" --exclude "memory/*.log" \
    --exclude "memory/*.json" --exclude "__pycache__" --exclude "*.pyc" \
    --exclude ".env" --exclude ".venv" \
    "$PROJECT_DIR/" "$VPS:$REMOTE_DIR/"

if [ -f "$PROJECT_DIR/.env" ]; then
    echo "🔐 Syncing .env..."
    scp "$PROJECT_DIR/.env" "$VPS:$REMOTE_DIR/.env"
else
    echo "⚠️  No .env — create manually on VPS"
fi

echo "🐳 Building and starting..."
ssh "$VPS" "cd $REMOTE_DIR && \
    docker-compose -f docker-compose.production.yml build rosa && \
    docker-compose -f docker-compose.production.yml up -d rosa nginx && \
    sleep 5 && docker-compose -f docker-compose.production.yml ps"

if [ -n "$DOMAIN" ]; then
    echo "🔒 Setting up SSL for $DOMAIN..."
    ssh "$VPS" "cd $REMOTE_DIR && \
        sed -i 's/server_name _;/server_name $DOMAIN;/g' nginx.conf && \
        docker-compose -f docker-compose.production.yml restart nginx && \
        docker run --rm \
            -v rosa_certbot_certs:/etc/letsencrypt \
            -v rosa_certbot_www:/var/www/certbot \
            certbot/certbot certonly \
            --webroot --webroot-path=/var/www/certbot \
            --email admin@$DOMAIN --agree-tos --no-eff-email -d $DOMAIN && \
        docker-compose -f docker-compose.production.yml --profile ssl up -d"
fi

# Hourly memory sync cron
(crontab -l 2>/dev/null; echo "0 * * * * ROSA_VPS=$VPS bash $SCRIPT_DIR/sync_memory.sh auto >> /tmp/rosa_sync.log 2>&1") | \
    sort -u | crontab - 2>/dev/null || true

sleep 3
echo "🔍 Health check..."
ssh "$VPS" "curl -sf http://localhost:8000/health && echo '✅ ROSA is healthy'" || \
    echo "⚠️  Check logs: ssh $VPS 'docker logs rosa_os'"

echo ""
echo "🌹 ROSA OS v6 deployed!"
[ -n "$DOMAIN" ] && echo "   URL: https://$DOMAIN"
echo "   VPS: http://$(echo $VPS | cut -d@ -f2):8000"
