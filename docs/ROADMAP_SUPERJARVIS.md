# ROSA OS — SuperJarvis Roadmap (Phases 1–10)

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        ROSA OS Core                             │
├──────────┬──────────┬──────────┬──────────┬────────────────────┤
│  Agents  │ Memory   │ Predict  │ Security │  Integrations      │
│ Swarm    │ Holograph│ Habit    │ Firewall │  TikTok / GitHub   │
│ Research │ Vector   │ Proactive│ Safety   │  Telegram / Obsid. │
│ Content  │ Quality  │ ActiveInf│ Ouroboros│  Vision / Browser  │
├──────────┴──────────┴──────────┴──────────┴────────────────────┤
│                    Kimi K2.5 Brain (OpenRouter)                 │
│                    + Pantheon: Claude / Gemini / GPT-4o / Grok  │
└─────────────────────────────────────────────────────────────────┘
```

## Phase Map

| Phase | Name | Modules | Status |
|-------|------|---------|--------|
| 1 | Connectivity | Swarm, Cron, VectorStore, Telegram | ✅ |
| 2 | Knowledge | TikTok, GitHub, Metacognition, Telegram-import | ✅ |
| 3 | Neuro-Symbolic | PAL, Firewall, HolographicMemory, Safety | ✅ |
| 4 | Predictive | HabitGraph, Proactive, ActiveInference | ✅ |
| 5 | Multimodal | Screenshot, PDF, Camera (stub) | ✅ |
| 6 | Model Pantheon | Enhanced routing, ENSEMBLE strategy | ✅ |
| 7 | Business | Projects, Researcher, ContentPipeline | ✅ |
| 8 | Ubiquity | Obsidian, BrowserRPA (stub), CrossPlatform | ✅ |
| 9 | Ouroboros | Self-improvement cycle, enhanced metacognition | ✅ |
| 10 | Singularity | AgentFactory, SelfHealer, FederatedMemory | ✅ |

## Module Registry

### Phase 1
- `core/agents/swarm.py` — Async task dispatcher for parallel agents
- `core/memory/vector_store.py` — Numpy-based cosine similarity vector store
- `core/integrations/socials/telegram_user.py` — Telethon MTProto reader

### Phase 2
- `core/integrations/socials/tiktok.py` — yt-dlp metadata extractor
- `core/integrations/workspace/github.py` — GitHub API repo ingestion
- `core/metacognition/evaluator.py` — Post-response quality scoring
- `core/api/integrations.py` — Unified integrations API router
- `core/api/metacognition.py` — Quality stats endpoints

### Phase 3
- `core/reasoning/pal.py` — Program-Aided Learning (Python subprocess executor)
- `core/security/firewall.py` — Pattern-matching firewall for subprocess/LLM actions
- `core/memory/holographic.py` — Context encoding/decoding with numpy HRR approx
- `core/self_improvement/safety.py` — Patch safety checks + test runner

### Phase 4
- `core/prediction/habit_graph.py` — Behavioral pattern analysis
- `core/prediction/proactive.py` — Asyncio-based proactive scheduler
- `core/prediction/active_inference.py` — Surprise scoring + belief updates

### Phase 5
- `core/integrations/vision/screenshot.py` — macOS screencapture + Kimi Vision
- `core/integrations/vision/pdf_reader.py` — PyPDF + knowledge graph ingestion
- `core/integrations/vision/camera.py` — Stub (requires OpenCV)

### Phase 6
- `config/models.yaml` — Enhanced model config with cost/speed/context
- `core/router/models_router.py` — ENSEMBLE strategy added

### Phase 7
- `core/projects/manager.py` — Project + Task ORM + CRUD
- `core/agents/researcher.py` — Multi-step research chain
- `core/agents/content_pipeline.py` — Idea → Draft → Publish flow

### Phase 8
- `core/integrations/sync/obsidian.py` — Bidirectional .md sync
- `core/integrations/rpa/browser.py` — Playwright stub
- `core/integrations/sync/cross_platform.py` — Unified message format

### Phase 9
- `core/self_improvement/ouroboros.py` — Weekly self-improvement cycle
- Enhanced `core/metacognition/evaluator.py` with pattern accumulation

### Phase 10
- `core/agents/factory.py` — Dynamic agent template system
- `core/healing/self_healer.py` — Exception interceptor + hotfix generator
- `core/memory/federated.py` — Multi-device sync stub

## Safety Invariants

1. **Human Gate** — no patch applied without explicit UI approval
2. **Firewall** — all subprocess.run() calls checked before execution
3. **Sandbox** — new patches written to `sandbox/patches/`, never auto-applied
4. **Ouroboros RULE** — never modifies code without owner confirmation
5. **Secrets** — only in `.env`, never logged or transmitted
6. **skip_download** — yt-dlp always `skip_download=True`

## API Endpoints (new in v4)

| Method | Path | Description |
|--------|------|-------------|
| POST | /api/integrations/tiktok/analyze | TikTok URL → knowledge nodes |
| POST | /api/integrations/github/ingest | GitHub repo → knowledge graph |
| POST | /api/integrations/telegram/import | Telegram chat → knowledge graph |
| POST | /api/integrations/telegram/auth/start | Initiate Telethon auth |
| POST | /api/integrations/telegram/auth/verify | Confirm OTP |
| POST | /api/integrations/pdf/ingest | PDF file → knowledge graph |
| GET  | /api/metacognition/quality | List response quality scores |
| GET  | /api/metacognition/stats | Aggregate quality stats |
| POST | /api/pal/execute | Execute math/logic via PAL |
| GET  | /api/projects | List projects |
| POST | /api/projects | Create project |
| GET  | /api/projects/{id}/tasks | Project tasks |
| POST | /api/research/start | Start research agent |
| POST | /api/content/create | Generate content |
| GET  | /api/proactive/schedule | Scheduled tasks list |
| POST | /api/proactive/subscribe | Add subscription |
| POST | /api/agents/create | Spawn agent from template |
| GET  | /api/agents | List active agents |
| GET  | /api/vision/screenshot | Capture + describe screen |
