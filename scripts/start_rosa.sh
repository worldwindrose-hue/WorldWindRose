#!/usr/bin/env bash
# ============================================================
# ROSA OS — Universal Startup Script
# Запускает сервер, ngrok туннель и watchdog одной командой
# Использование: ./scripts/start_rosa.sh [--no-tunnel] [--no-qr]
# ============================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PORT=8000
HOST="0.0.0.0"
LOG_DIR="${PROJECT_DIR}/memory/logs"
NO_TUNNEL=false
NO_QR=false

# ── Parse flags ────────────────────────────────────────────
for arg in "$@"; do
  case $arg in
    --no-tunnel) NO_TUNNEL=true ;;
    --no-qr)     NO_QR=true ;;
  esac
done

# ── Setup ──────────────────────────────────────────────────
mkdir -p "$LOG_DIR" "${PROJECT_DIR}/memory"
cd "$PROJECT_DIR"

echo ""
echo "🌹 ================================================="
echo "   ROSA OS — Starting up"
echo "   $(date)"
echo "🌹 ================================================="
echo ""

# ── Local IP ───────────────────────────────────────────────
LOCAL_IP=$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || echo "127.0.0.1")
echo "📍 Local IP:  http://${LOCAL_IP}:${PORT}"
echo "📍 Localhost: http://127.0.0.1:${PORT}"

# ── Kill any existing Rosa processes ───────────────────────
echo ""
echo "🛑 Stopping existing ROSA processes..."
pkill -f "uvicorn core.app:app" 2>/dev/null || true
pkill -f "ngrok http ${PORT}"   2>/dev/null || true
pkill -f "start_rosa_tunnel"    2>/dev/null || true
sleep 1

# ── Start ngrok tunnel ─────────────────────────────────────
if [ "$NO_TUNNEL" = false ]; then
  echo ""
  echo "🔌 Starting ngrok tunnel..."

  # Use native ngrok binary (brew-installed)
  NGROK_BIN=$(command -v ngrok || echo "/opt/homebrew/bin/ngrok")

  # Start ngrok in background, output JSON to file
  NGROK_LOG="${LOG_DIR}/ngrok.log"
  "$NGROK_BIN" http "$PORT" --log=stdout --log-format=json > "$NGROK_LOG" 2>&1 &
  NGROK_PID=$!
  echo $NGROK_PID > "${PROJECT_DIR}/memory/ngrok.pid"

  # Poll until tunnel URL appears in log (max 10s)
  TUNNEL_URL=""
  for i in {1..20}; do
    sleep 0.5
    TUNNEL_URL=$(python3 -c "
import json, sys
try:
    with open('${NGROK_LOG}') as f:
        for line in f:
            try:
                d = json.loads(line)
                if d.get('msg') == 'started tunnel':
                    print(d.get('url',''))
                    break
            except: pass
except: pass
" 2>/dev/null || true)
    [ -n "$TUNNEL_URL" ] && break
  done

  if [ -z "$TUNNEL_URL" ]; then
    echo "⚠️  Туннель не запустился за 10с — проверьте ngrok.log"
    echo "   Продолжаю без публичного URL..."
  else
    # Ensure HTTPS
    TUNNEL_URL="${TUNNEL_URL/http:\/\//https://}"
    echo "$TUNNEL_URL" > "${PROJECT_DIR}/memory/tunnel.txt"
    echo "🌐 Public URL: ${TUNNEL_URL}"
    echo ""

    if [ "$NO_QR" = false ]; then
      echo "📱 QR Code (scan with iPhone Camera):"
      echo ""
      python3 -c "
import qrcode
url = '${TUNNEL_URL}'
qr = qrcode.QRCode(border=1)
qr.add_data(url)
qr.make(fit=True)
qr.print_ascii(invert=True)
print()
print('  → ' + url)
" 2>/dev/null || echo "  (pip install qrcode to show QR)"
    fi
  fi
fi

# ── Start uvicorn with --host 0.0.0.0 ─────────────────────
echo ""
echo "🚀 Starting ROSA OS server on ${HOST}:${PORT}..."
echo "   Logs: ${LOG_DIR}/rosa.log"
echo ""

exec uvicorn core.app:app \
  --host "$HOST" \
  --port "$PORT" \
  --reload \
  --log-level info \
  2>&1 | tee -a "${LOG_DIR}/rosa.log"
