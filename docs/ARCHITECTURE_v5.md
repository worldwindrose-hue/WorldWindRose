# ROSA OS v5 — SuperJarvis Architecture

## Overview

ROSA v5 is a fully autonomous AI assistant platform built on FastAPI + SQLAlchemy + Kimi K2.5.
It adds 10 new capability layers on top of v3's chat+memory foundation.

```
┌─────────────────────────────────────────────────────────────────┐
│                    ROSA Desktop v5 (Browser UI)                 │
│   ChatGPT-exact UI: sidebar + bubbles + status bar + markdown   │
│   app.js: WebSocket streaming, all view logic, HyperSearch UI   │
└───────────────────────────┬─────────────────────────────────────┘
                            │ WebSocket + HTTP
┌───────────────────────────▼─────────────────────────────────────┐
│                    FastAPI Application (core/app.py)             │
│   Routers: chat, tasks, memory, status, fs, search, mac,        │
│            telegram, coding, swarm, economy, planning,          │
│            integrations, metacognition, self-improve             │
└───┬───────────────────┬────────────────────────────────────────-┘
    │                   │
┌───▼───────────┐ ┌─────▼──────────────────────────────────────────┐
│  Kimi K2.5   │ │              Module Layers                       │
│  (OpenRouter) │ │                                                  │
│  Brain        │ │  Phase 0: Status Center (RosaStatus + WebSocket) │
└───────────────┘ │  Phase 2: Filesystem (sandboxed R/W)             │
                  │  Phase 3: Persistent Memory (Working+Episodic)   │
                  │  Phase 4: HyperSearch (5 sources + synthesis)    │
                  │  Phase 5: macOS Controller (AppleScript+shell)   │
                  │  Phase 6: 24/7 Mode (offline queue + Telegram)   │
                  │  Phase 7: Self-Coding (executor+git+writer)      │
                  │  Phase 8: Auto-Scaling Swarm (up to 20 agents)   │
                  │  Phase 9: Token Economy (cost tracking+cache)    │
                  │  Phase 10: Mission Planner (Thought→Action)      │
                  └──────────────────────────────────────────────────┘
```

## Module Tree

```
core/
├── app.py                    # FastAPI entry point
├── config.py                 # Pydantic settings
├── router.py                 # RosaRouter (cloud/local routing)
├── policies.py               # Safety policies
│
├── status/                   # Phase 0
│   ├── tracker.py            # RosaStatus enum + tracker + WS broadcast
│   └── __init__.py
│
├── memory/                   # Persistent storage
│   ├── models.py             # SQLAlchemy ORM (Task, Event, Reflection…)
│   ├── store.py              # Async CRUD singleton
│   ├── persistent.py         # WorkingMemory + EpisodicMemory + SemanticMemory
│   └── backup.py             # Auto-backup (hourly, 30 max)
│
├── filesystem/               # Phase 2
│   └── manager.py            # Sandboxed file R/W
│
├── search/                   # Phase 4
│   ├── hypersearch.py        # 5 parallel sources + Kimi synthesis
│   └── live_monitor.py       # Topic subscription + polling
│
├── mac/                      # Phase 5
│   ├── controller.py         # AppleScript, shell, screenshot, clipboard
│   ├── automation.py         # High-level macOS automation
│   └── watcher.py            # CPU/RAM/disk/network monitoring
│
├── offline/                  # Phase 6
│   ├── local_mode.py         # Internet checker + preferred model
│   └── message_queue.py      # Offline message queue (JSON)
│
├── mobile/                   # Phase 6 (Telegram)
│   └── telegram_gateway.py   # Bot webhook, /status /act commands
│
├── coding/                   # Phase 7
│   ├── code_executor.py      # Python/Bash/SQL sandboxed execution
│   ├── self_coder.py         # Module writer + refactorer + auto-test
│   └── git_manager.py        # git diff/log/commit/branch
│
├── swarm/                    # Phase 8
│   └── auto_scaler.py        # classify→decide→run→synthesize
│
├── economy/                  # Phase 9
│   ├── token_optimizer.py    # Cost tracking + cache + compression
│   └── api_extractor.py      # Env scanner + alternatives
│
├── planning/                 # Phase 10
│   └── mission_planner.py    # Intent parsing → step plan → execute
│
├── metacognition/            # Metacognitive evaluator
│   └── evaluator.py          # Fire-and-forget response scoring
│
└── integrations/             # External data sources
    ├── socials/
    │   ├── tiktok.py         # yt-dlp metadata → knowledge graph
    │   └── telegram_user.py  # Telethon → knowledge graph
    └── workspace/
        └── github.py         # GitHub API → knowledge graph
```

## Data Flow: Chat Request

```
User types message
        │
        ▼
WebSocket /api/ws/chat
        │
   chat.py handler
        │
   ┌────▼────────────────────────┐
   │ set_status(THINKING)        │
   │ MemoryInjector.build_ctx()  │  ← working memory + episodic search
   │ RosaRouter.chat()           │  ← Kimi K2.5 via OpenRouter
   │ Streaming tokens → client  │
   │ set_status(ONLINE)          │
   │ asyncio.create_task(        │
   │   evaluate_response()       │  ← fire-and-forget metacognition
   │ )                           │
   └─────────────────────────────┘
```

## Status States

| Status | Meaning | Color |
|--------|---------|-------|
| ОНЛАЙН | Ready for dialog | green |
| ДУМАЕТ | Processing LLM request | yellow |
| ДЕЙСТВУЕТ | Executing task/script | yellow |
| СОВЕЩАЕТСЯ | Agent swarm running | yellow |
| ПОСЕЩАЕТ | RPA browser open | yellow |
| РЕШАЕТ | Active inference | yellow |
| ОБНОВЛЯЕТСЯ | Ouroboros patching | yellow |
| ОФЛАЙН | No internet, local mode | gray |
| ЗАВИСЛА | Watchdog detected problem | red |
| СЛОМАНА | Critical error | red |

## Key Design Decisions

1. **Status DB is separate** (`memory/status.db` via aiosqlite) to avoid lock contention with main SQLAlchemy store.
2. **Metacognition is fire-and-forget** — `asyncio.create_task()` so zero latency for the user.
3. **Missions use in-memory dict** — no DB migration needed; missions are session-scoped.
4. **ChromaDB is optional** — EpisodicMemory falls back to SQLite `search_nodes()` if not installed.
5. **Filesystem sandbox** — checks `_is_allowed()` against module-level `_ALLOWED_ZONES` before every operation.
6. **Code firewall** — blocks dangerous patterns in `execute_python`, `execute_bash`, `run_shell`.
7. **Swarm synthesis** — all agent results merged by a final Kimi call into a single coherent answer.
