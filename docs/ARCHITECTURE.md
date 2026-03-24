# ROSA OS v4 — Architecture Overview

## System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        UI Layer (v4)                         │
│  Чат | Рой | Знания | Проекты | Улучшение | Настройки       │
│  desktop/index.html + app.js + style.css                    │
└─────────────────────┬───────────────────────────────────────┘
                      │ WebSocket + REST API
┌─────────────────────▼───────────────────────────────────────┐
│                   FastAPI (core/app.py)                      │
│  /api/chat  /api/ws/chat  /api/agents  /api/projects  ...  │
└──────────┬────────────────────────────────────┬─────────────┘
           │                                    │
┌──────────▼──────────┐              ┌──────────▼──────────┐
│   ROSA Router        │              │   Memory Layer       │
│  core/router/        │              │  core/memory/        │
│  - RosaRouter        │              │  - SQLite (ORM)      │
│  - ModelsRouter      │              │  - Knowledge Graph   │
│  - Task classifier   │              │  - Holographic Store │
│  - Ensemble mode     │              │  - Federated Memory  │
└──────────┬──────────┘              └─────────────────────┘
           │
┌──────────▼──────────────────────────────────────────────────┐
│                    LLM Backends                              │
│  OpenRouter (Kimi K2.5, Claude, Gemini, Perplexity, Grok)  │
│  Ollama (Llama 3.2 — local/private)                        │
└─────────────────────────────────────────────────────────────┘
```

## Core Modules

### Routing
- `core/router/__init__.py` — `RosaRouter`: main chat router, auto-routes to Kimi K2.5
- `core/router/models_router.py` — `ModelsRouter`: strategy-based model selection (fast/quality/privacy/ensemble/task_routing)

### Memory
- `core/memory/models.py` — SQLAlchemy ORM (Task, Event, Reflection, ConversationTurn, ResponseQuality, Project, ProjectTask, HabitEvent, ProactiveSubscription)
- `core/memory/store.py` — async CRUD over SQLite
- `core/memory/holographic.py` — HRR-based 512-dim vector memory (numpy)
- `core/memory/federated.py` — cross-device memory stub

### Prediction
- `core/prediction/habit_graph.py` — temporal usage patterns (hour × task_type)
- `core/prediction/proactive.py` — background scheduler (07:00 briefings, subscriptions)
- `core/prediction/active_inference.py` — Free Energy Principle belief state

### Reasoning
- `core/reasoning/pal.py` — Program-Aided Learning (Kimi → Python → subprocess)
- `core/security/firewall.py` — regex-based command firewall

### Agents
- `core/agents/researcher.py` — multi-step web research pipeline
- `core/agents/content_pipeline.py` — blog/social/email content creator
- `core/agents/swarm.py` — parallel multi-agent coordinator
- `core/agents/factory.py` — agent registry and factory

### Self-Improvement
- `core/self_improvement/safety.py` — sandbox patches/, pytest runner, rollback, Human Gate
- `core/self_improvement/ouroboros.py` — 5-step weekly improvement cycle
- `core/self_improvement/collector.py` — metrics collector
- `core/self_improvement/analyzer.py` — Kimi-based analysis
- `core/self_improvement/patcher.py` — proposal writer

### Metacognition
- `core/metacognition/evaluator.py` — fire-and-forget quality evaluation (Kimi → scores)

### Integrations
- `core/integrations/socials/tiktok.py` — yt-dlp metadata extraction
- `core/integrations/socials/telegram_user.py` — Telethon MTProto
- `core/integrations/workspace/github.py` — GitHub REST API
- `core/integrations/vision/screenshot.py` — macOS screencapture
- `core/integrations/vision/pdf_reader.py` — pypdf + knowledge graph
- `core/integrations/vision/camera.py` — OpenCV stub
- `core/integrations/sync/obsidian.py` — bidirectional .md sync
- `core/integrations/sync/cross_platform.py` — JSON export/import
- `core/integrations/rpa/browser.py` — Playwright browser automation stub

### Projects
- `core/projects/manager.py` — Project/Task CRUD

### Healing
- `core/healing/self_healer.py` — health checks + auto-recovery

### Knowledge
- `core/knowledge/graph.py` — KnowledgeNode/KnowledgeEdge with LLM extraction

## Data Flow

### Chat Request
```
Client → WS /api/ws/chat → RosaRouter.chat()
  → classify_task() → cloud (Kimi K2.5)
  → send type:"response"
  → asyncio.create_task(evaluate_response())  ← metacognition
  → asyncio.create_task(record_usage())       ← habit graph
```

### Self-Improvement Cycle (Ouroboros)
```
Trigger → step1_profile() → collect quality metrics + weak points
  → step2_generate() → Kimi proposes code changes
  → step3_test() → write to sandbox/ → run pytest
  → step4_propose() → save to proposals DB
  → Human Gate → apply via UI only
```

## Configuration
- `core/config.py` — pydantic-settings, reads from .env
- `config/models.yaml` — model pantheon + routing strategies
- `config/policies.yaml` — safety policies
- `config/settings.yaml` — default settings

## Safety Invariants
- Metacognition: fire-and-forget only, zero latency impact
- PAL: subprocess with timeout=10s, firewall pre-check
- Patches: sandbox first, Human Gate before apply
- Telethon: StringSession in TELEGRAM_SESSION env var
- yt-dlp: skip_download=True always
- GitHub: works without token (60 req/h), token optional
