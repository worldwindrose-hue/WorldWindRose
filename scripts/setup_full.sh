#!/usr/bin/env bash
# ============================================================
# ROSA OS v5 — Full Setup Script (SuperJarvis)
# ============================================================
set -euo pipefail

ROSA_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROSA_DIR"

echo "🌹 ROSA OS v5 — SuperJarvis Setup"
echo "======================================"
echo "Directory: $ROSA_DIR"
echo ""

# ── Python check ──────────────────────────────────────────────────────────
if ! command -v python3 &>/dev/null; then
    echo "❌ Python 3 not found. Install from https://python.org"
    exit 1
fi

PY_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo "✅ Python $PY_VERSION found"

# ── pip check ─────────────────────────────────────────────────────────────
python3 -m pip install --upgrade pip -q

# ── Core dependencies ─────────────────────────────────────────────────────
echo ""
echo "📦 Installing core dependencies..."
python3 -m pip install -q \
    fastapi \
    "uvicorn[standard]" \
    sqlalchemy \
    aiosqlite \
    "openai>=1.0" \
    pydantic-settings \
    python-dotenv \
    rich \
    beautifulsoup4 \
    httpx \
    aiofiles \
    python-multipart

# ── Optional dependencies ─────────────────────────────────────────────────
echo "📦 Installing optional dependencies..."

python3 -m pip install -q yt-dlp 2>/dev/null && echo "  ✅ yt-dlp (TikTok)" || echo "  ⚠️  yt-dlp skipped"
python3 -m pip install -q psutil 2>/dev/null && echo "  ✅ psutil (system stats)" || echo "  ⚠️  psutil skipped"
python3 -m pip install -q telethon 2>/dev/null && echo "  ✅ telethon (Telegram)" || echo "  ⚠️  telethon skipped"
python3 -m pip install -q chromadb 2>/dev/null && echo "  ✅ chromadb (vector memory)" || echo "  ⚠️  chromadb skipped (using SQLite fallback)"
python3 -m pip install -q ollama 2>/dev/null && echo "  ✅ ollama (local models)" || echo "  ⚠️  ollama skipped"

# ── .env setup ────────────────────────────────────────────────────────────
echo ""
echo "⚙️  Environment setup..."
if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then
        cp .env.example .env
        echo "  📋 Created .env from .env.example"
        echo "  ⚠️  Edit .env and add your OPENROUTER_API_KEY!"
    else
        cat > .env << 'ENVEOF'
# ROSA OS v5 — Environment Configuration
OPENROUTER_API_KEY=your_key_here
CLOUD_MODEL=moonshotai/kimi-k2.5
LOCAL_MODEL=llama3.2

# Optional integrations
GITHUB_TOKEN=
TELEGRAM_BOT_TOKEN=
TELEGRAM_OWNER_CHAT_ID=
TELEGRAM_API_ID=
TELEGRAM_API_HASH=
TELEGRAM_PHONE=
ENVEOF
        echo "  📋 Created default .env"
        echo "  ⚠️  Edit .env and add your OPENROUTER_API_KEY!"
    fi
else
    echo "  ✅ .env already exists"
fi

# ── Directory structure ───────────────────────────────────────────────────
echo ""
echo "📁 Creating directory structure..."
mkdir -p memory/backups memory/chroma experimental scripts/logs
echo "  ✅ memory/, experimental/ created"

# ── Run tests ─────────────────────────────────────────────────────────────
echo ""
echo "🧪 Running tests..."
if python3 -m pytest tests/ -q --tb=short 2>&1 | tail -5; then
    echo "  ✅ All tests passed"
else
    echo "  ⚠️  Some tests failed — check above"
fi

# ── LaunchDaemon (macOS 24/7) ─────────────────────────────────────────────
if [[ "$OSTYPE" == "darwin"* ]]; then
    PLIST_PATH="$HOME/Library/LaunchAgents/com.rosa.os.plist"
    if [ ! -f "$PLIST_PATH" ]; then
        cat > "$PLIST_PATH" << PLISTEOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.rosa.os</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/local/bin/python3</string>
        <string>-m</string>
        <string>uvicorn</string>
        <string>core.app:app</string>
        <string>--host</string>
        <string>127.0.0.1</string>
        <string>--port</string>
        <string>8000</string>
    </array>
    <key>WorkingDirectory</key>
    <string>$ROSA_DIR</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>$ROSA_DIR/scripts/logs/rosa.log</string>
    <key>StandardErrorPath</key>
    <string>$ROSA_DIR/scripts/logs/rosa_error.log</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin</string>
    </dict>
</dict>
</plist>
PLISTEOF
        echo ""
        echo "🚀 LaunchAgent created: $PLIST_PATH"
        echo "   To enable 24/7 mode: launchctl load $PLIST_PATH"
    fi
fi

# ── Final summary ─────────────────────────────────────────────────────────
echo ""
echo "======================================"
echo "🎉 ROSA OS v5 setup complete!"
echo ""
echo "Next steps:"
echo "  1. Edit .env and add OPENROUTER_API_KEY"
echo "  2. Start server:"
echo "     uvicorn core.app:app --reload --port 8000"
echo "  3. Open http://localhost:8000"
echo ""
echo "  Optional — 24/7 LaunchAgent (macOS):"
echo "     launchctl load ~/Library/LaunchAgents/com.rosa.os.plist"
echo ""
