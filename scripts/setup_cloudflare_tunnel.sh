#!/usr/bin/env bash
# ============================================================
# ROSA OS — Cloudflare Tunnel Setup
# Creates a permanent public URL without a paid ngrok plan.
# Usage: ./scripts/setup_cloudflare_tunnel.sh [port]
# ============================================================

set -euo pipefail

PORT="${1:-8000}"
TUNNEL_NAME="rosa-os"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "🌩️  Setting up Cloudflare Tunnel for ROSA OS on port $PORT..."

# Install cloudflared if not present
if ! command -v cloudflared &>/dev/null; then
    echo "📦 Installing cloudflared..."
    if command -v brew &>/dev/null; then
        brew install cloudflare/cloudflare/cloudflared
    else
        ARCH=$(uname -m)
        if [ "$ARCH" = "arm64" ]; then
            URL="https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64"
        else
            URL="https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64"
        fi
        curl -L "$URL" -o /usr/local/bin/cloudflared
        chmod +x /usr/local/bin/cloudflared
    fi
fi

echo "✅ cloudflared $(cloudflared --version)"

# Login (opens browser)
if [ ! -f ~/.cloudflared/cert.pem ]; then
    echo "🔐 Login to Cloudflare (browser will open)..."
    cloudflared tunnel login
fi

# Create tunnel (ignore if exists)
cloudflared tunnel create "$TUNNEL_NAME" 2>/dev/null || echo "  (tunnel '$TUNNEL_NAME' already exists)"

# Get tunnel ID
TUNNEL_ID=$(cloudflared tunnel list --output json 2>/dev/null | \
    python3 -c "import json,sys; tunnels=json.load(sys.stdin); \
    t=[t for t in tunnels if t.get('name')=='$TUNNEL_NAME']; \
    print(t[0]['id'] if t else '')" 2>/dev/null || echo "")

if [ -z "$TUNNEL_ID" ]; then
    echo "❌ Could not find tunnel ID"
    exit 1
fi

echo "🔗 Tunnel ID: $TUNNEL_ID"

# Write tunnel config
CONFIG_DIR="$HOME/.cloudflared"
mkdir -p "$CONFIG_DIR"
cat > "$CONFIG_DIR/config.yml" << EOF
tunnel: $TUNNEL_ID
credentials-file: $CONFIG_DIR/$TUNNEL_ID.json

ingress:
  - service: http://localhost:$PORT

EOF

echo "✅ Tunnel config written to $CONFIG_DIR/config.yml"

# Save to .env
TUNNEL_URL="https://$TUNNEL_NAME.cfargotunnel.com"
ENV_FILE="$PROJECT_DIR/.env"
if [ -f "$ENV_FILE" ]; then
    # Update or add
    if grep -q "CLOUDFLARE_TUNNEL" "$ENV_FILE"; then
        sed -i.bak "s|CLOUDFLARE_TUNNEL_URL=.*|CLOUDFLARE_TUNNEL_URL=$TUNNEL_URL|" "$ENV_FILE"
        sed -i.bak "s|TUNNEL_PROVIDER=.*|TUNNEL_PROVIDER=cloudflare|" "$ENV_FILE"
    else
        echo "" >> "$ENV_FILE"
        echo "CLOUDFLARE_TUNNEL_URL=$TUNNEL_URL" >> "$ENV_FILE"
        echo "TUNNEL_PROVIDER=cloudflare" >> "$ENV_FILE"
    fi
fi

echo ""
echo "🌹 Cloudflare Tunnel ready!"
echo "   URL: $TUNNEL_URL"
echo "   Start tunnel: cloudflared tunnel run $TUNNEL_NAME"
echo "   Or add to start_rosa.sh with TUNNEL_PROVIDER=cloudflare"
