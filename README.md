# ROSA OS

Hybrid AI assistant platform powered by **Kimi K2.5** (cloud) and **Ollama** (local). ChatGPT-level web UI, persistent chat sessions, file/image/URL/voice support, and a self-improvement loop.

## Quick Start

```bash
# 1. Install dependencies
pip install -e ".[dev]"

# 2. Configure environment
cp .env.example .env
# Edit .env — add OPENROUTER_API_KEY at minimum

# 3. Start the server
uvicorn core.app:app --reload --port 8000

# 4. Open the UI
open http://localhost:8000
```

## Feature Matrix

| Feature | How to enable |
|---------|--------------|
| **Cloud chat (Kimi K2.5)** | Set `OPENROUTER_API_KEY` in `.env` |
| **Local chat (Ollama)** | Install [Ollama](https://ollama.ai), run `ollama pull llama3.2`, set `LOCAL_MODEL=llama3.2` |
| **Smart routing (Auto mode)** | Both keys configured; Rosa picks cloud vs. local per task |
| **File upload (PDF/text)** | Built-in — no extra config needed |
| **Image analysis (vision)** | Set `CLOUD_MODEL=moonshotai/kimi-vl` in `.env` |
| **Voice input (STT)** | Built-in via Web Speech API (Chrome/Safari/Edge) |
| **Voice fallback (Whisper)** | Set `OPENAI_DIRECT_KEY` in `.env` |
| **Text-to-speech** | Set `OPENAI_DIRECT_KEY` in `.env` |
| **URL parsing** | Built-in — no extra config needed |
| **Self-improvement loop** | Automatic — runs when you click "Run Cycle" in the Improve tab |
| **Perplexity Computer** | Future — see `core/integrations/computer_use.py` |

## Environment Variables

```env
# Required
OPENROUTER_API_KEY=sk-or-...

# Optional — cloud model (default: moonshotai/kimi-k2.5)
CLOUD_MODEL=moonshotai/kimi-k2.5

# Optional — local model via Ollama
LOCAL_MODEL=llama3.2

# Optional — voice/transcription via OpenAI
OPENAI_DIRECT_KEY=sk-...

# Optional — server config
HOST=0.0.0.0
PORT=8000
```

## Project Structure

```
core/
  app.py            FastAPI entry point
  config.py         Typed settings (pydantic-settings)
  router.py         Cloud/local routing logic
  api/              REST + WebSocket endpoints
  memory/           SQLAlchemy ORM + async CRUD
  self_improvement/ Collector → Analyzer → Patcher
  integrations/     Vision + Computer Use stubs
desktop/
  index.html        Single-page UI
  style.css         Dark/light theme
  app.js            All frontend logic
docs/
  CONSTITUTION.md   ROSA OS immutable principles
  PLAN.md           Architecture overview
config/
  policies.yaml     Red zones + safety rules
experimental/       Self-improvement patch proposals (sandbox)
memory/             Runtime SQLite DB + logs + uploads
tests/              pytest suite
```

## API Endpoints

```
POST /api/chat              — single-turn chat
WS   /api/ws/chat           — streaming chat (WebSocket)
GET  /api/sessions          — list chat sessions
POST /api/sessions          — create session
GET  /api/sessions/{id}     — session + messages
PATCH /api/sessions/{id}    — rename / move to folder
DELETE /api/sessions/{id}   — delete session

GET  /api/folders           — list folders
POST /api/folders           — create folder
PATCH /api/folders/{id}     — rename folder
DELETE /api/folders/{id}    — delete folder

POST /api/files/upload      — upload file (multipart)
POST /api/parse-url         — fetch + extract web page
POST /api/voice/transcribe  — audio → text (Whisper)
POST /api/voice/synthesize  — text → audio (TTS)

POST /api/self-improve/run              — run improvement cycle
GET  /api/self-improve/events           — list events
GET  /api/self-improve/proposals        — list proposals
POST /api/self-improve/proposals/{id}/apply — apply a proposal

GET  /health                — health check
GET  /api/docs              — Swagger UI
```

## Running Tests

```bash
python3 -m pytest tests/ -v
```

## Architecture

See [docs/PLAN.md](docs/PLAN.md) for full architecture diagrams.

See [docs/CONSTITUTION.md](docs/CONSTITUTION.md) for ROSA OS safety principles.
