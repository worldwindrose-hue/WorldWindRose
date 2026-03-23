# ROSA OS — Architecture Overview

## System Layers

```
Browser (ROSA Desktop)
        │ WebSocket + REST
        ▼
FastAPI Backend (core/)
        │
   ┌────┴──────────────────────────────────────┐
   │                                           │
   ▼                                           ▼
RosaRouter                              Memory Store
(cloud + local routing)                 (SQLite via SQLAlchemy)
   │
   ├── Cloud Brain: Kimi K2.5 via OpenRouter
   └── Local Brain: Ollama (local models)
```

## Component Map

| Layer | Files | Purpose |
|-------|-------|---------|
| Entry | `core/app.py` | FastAPI app, lifespan, router registration |
| Config | `core/config.py` | Typed settings from .env (pydantic-settings) |
| Router | `core/router.py` | Wraps HybridRouter; decides cloud vs. local |
| Chat API | `core/api/chat.py` | POST /api/chat + WS /api/ws/chat |
| Sessions | `core/api/sessions.py` | CRUD for named chat sessions |
| Folders | `core/api/folders.py` | Project folder grouping |
| Files | `core/api/files.py` | Multipart upload, text extraction |
| Voice | `core/api/voice.py` | Whisper transcription + TTS (OpenAI backend) |
| URL | `core/api/parse_url.py` | Fetch + extract web page content |
| Self-improve | `core/api/self_improve.py` | Events, proposals, run/apply cycle |
| DB Models | `core/memory/models.py` | SQLAlchemy ORM (tasks, sessions, files, events…) |
| DB Store | `core/memory/store.py` | Async CRUD operations |
| Tools | `tools.py` | WebSearchTool, LocalKBTool, PersistentMemoryTool |
| Security | `security_layer.py` | Prompt injection defense + human-in-the-loop |
| Desktop UI | `desktop/` | HTML/CSS/JS served by FastAPI |
| Integrations | `core/integrations/` | Vision (Kimi-VL) + Computer Use (stubs) |

## Data Flow: Chat Message

```
User types → WebSocket → core/api/chat.py
  → RosaRouter.route(message)
    → classify: cloud / local / tools
    → if tools: run WebSearchTool / LocalKBTool / MemoryTool
    → call LLM (Kimi via OpenRouter OR Ollama)
    → stream tokens back via WebSocket
  → save ConversationTurn to SQLite
  → update ChatSession.updated_at
```

## Data Flow: File Upload

```
User attaches file → POST /api/files/upload
  → save raw file to memory/uploads/
  → extract text:
      .pdf → pypdf (up to 30 pages)
      .txt/.md/.py → read directly
      image → needs_vision: true (stub for Kimi-VL)
  → store UploadedFile record in SQLite
  → return {file_id, filename, extracted_text, needs_vision}
  → Frontend prepends [FILE: name]\n{text} to next message
```

## Self-Improvement Loop

```
POST /api/self-improve/run
  → Collector: query DB for failed tasks + high-severity events + low-rated turns
  → Analyzer: send metrics to Kimi with analysis prompt
  → Patcher: write proposal to experimental/YYYY-MM-DD-{id}.md
  → Return report

POST /api/self-improve/proposals/{id}/apply
  → Owner reviews proposal in UI
  → Explicit confirmation required
  → Apply patch (never auto-applied)
```

## Future Integration Hooks

| Feature | File | Status |
|---------|------|--------|
| Perplexity Computer (screen control) | `core/integrations/computer_use.py` | Stub — raises NotImplementedError |
| Kimi-VL image analysis | `core/integrations/vision.py` | Works when CLOUD_MODEL=moonshotai/kimi-vl |
| OpenAI Whisper STT | `core/api/voice.py` | Works when OPENAI_DIRECT_KEY is set |
| OpenAI TTS | `core/api/voice.py` | Works when OPENAI_DIRECT_KEY is set |
| Live mode (real-time context) | `desktop/app.js` liveMode | Polling hook ready for Computer Use |

## Database Schema

```
folders          → id, name, created_at
chat_sessions    → id, title, folder_id, created_at, updated_at
conversation_turns → id, role, content, model_used, session_id, task_id, created_at
uploaded_files   → id, filename, content_type, size, extracted_text, needs_vision, session_id, created_at
tasks            → id, description, plan, result, status, owner_rating, created_at
events           → id, event_type, description, severity, task_id, created_at
reflections      → id, content, suggestions, applied, created_at
```
