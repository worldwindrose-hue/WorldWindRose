#!/usr/bin/env bash
# ============================================================
# ROSA OS — Universal Startup Script
# Запускает сервер, ngrok туннель и watchdog одной командой
# Использование: ./scripts/start_rosa.sh [--no-tunnel] [--no-qr]
# ============================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
VENV_PYTHON="${PROJECT_DIR}/.venv/bin/python3"
PYTHON="${VENV_PYTHON:-python3}"
PORT=8000
HOST="0.0.0.0"
LOG_DIR="${PROJECT_DIR}/memory/logs"
NGROK_TOKEN="3BOcGYvq82lU8d6UIB9r9UO62Et_2zrsjGNpHviozzXKLoqVm"
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
mkdir -p "$LOG_DIR"
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
sleep 1

# ── Start ngrok tunnel ─────────────────────────────────────
if [ "$NO_TUNNEL" = false ]; then
  echo ""
  echo "🔌 Starting ngrok tunnel..."
  TUNNEL_URL=$(python3 - <<PYEOF
import sys
from pyngrok import ngrok, conf

conf.get_default().auth_token = '${NGROK_TOKEN}'
tunnel = ngrok.connect(${PORT}, 'http')
url = tunnel.public_url.replace('http://', 'https://')
print(url)

import pathlib
pathlib.Path('memory/tunnel.txt').write_text(url)
PYEOF
  )
  echo "🌐 Public URL: ${TUNNEL_URL}"
  echo ""

  # Save for use below
  echo "$TUNNEL_URL" > memory/tunnel.txt

  if [ "$NO_QR" = false ]; then
    echo "📱 QR Code (scan with iPhone Camera):"
    echo ""
    python3 -c "
import qrcode, sys
url = open('memory/tunnel.txt').read().strip()
qr = qrcode.QRCode(border=1)
qr.add_data(url)
qr.make(fit=True)
qr.print_ascii(invert=True)
print()
print('URL:', url)
" 2>/dev/null || python3 -c "print('  (pip install qrcode to show QR)')"
  fi
else
  TUNNEL_URL="(туннель отключён)"
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
