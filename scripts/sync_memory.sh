#!/usr/bin/env bash
# ============================================================
# ROSA OS — Memory Sync between Mac and VPS
# Usage: ./scripts/sync_memory.sh [push|pull|auto]
#
# Env vars:
#   ROSA_VPS=user@your-vps.example.com
#   ROSA_REMOTE_PATH=/opt/rosa/memory (default)
# ============================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOCAL_PATH="$(dirname "$SCRIPT_DIR")/memory"
VPS="${ROSA_VPS:-}"
REMOTE_PATH="${ROSA_REMOTE_PATH:-/opt/rosa/memory}"
MODE="${1:-auto}"

if [ -z "$VPS" ]; then
    echo "⚠️  ROSA_VPS not set. Add to .env: ROSA_VPS=user@your-vps.example.com"
    exit 1
fi

RSYNC_OPTS="-avz --exclude '*.log' --exclude '*.pid' --exclude 'uploads/' --exclude '*.tmp'"

push() {
    echo "📤 Pushing memory to $VPS:$REMOTE_PATH..."
    eval rsync $RSYNC_OPTS "$LOCAL_PATH/" "$VPS:$REMOTE_PATH/"
    echo "✅ Push complete: $(date)"
}

pull() {
    echo "📥 Pulling memory from $VPS:$REMOTE_PATH..."
    eval rsync $RSYNC_OPTS "$VPS:$REMOTE_PATH/" "$LOCAL_PATH/"
    echo "✅ Pull complete: $(date)"
}

auto() {
    echo "🔄 Auto-sync memory with $VPS..."
    pull 2>/dev/null || echo "  ↳ Pull skipped (VPS unreachable)"
    push 2>/dev/null || echo "  ↳ Push skipped (VPS unreachable)"
}

case "$MODE" in
    push) push ;;
    pull) pull ;;
    auto) auto ;;
    *)    echo "Usage: $0 [push|pull|auto]"; exit 1 ;;
esac
