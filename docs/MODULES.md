# ROSA OS v4 — Module Registry

## Phase 3 — Core Intelligence

| Module | File | Description |
|--------|------|-------------|
| PAL | `core/reasoning/pal.py` | Program-Aided Learning: math/logic via Kimi→Python→subprocess |
| Firewall | `core/security/firewall.py` | Regex-based dangerous command blocker |
| Holographic Memory | `core/memory/holographic.py` | HRR 512-dim vector store (numpy) |
| Safety Sandbox | `core/self_improvement/safety.py` | Patch sandbox + pytest runner + Human Gate |

## Phase 4 — Prediction

| Module | File | Description |
|--------|------|-------------|
| Habit Graph | `core/prediction/habit_graph.py` | Usage pattern tracking (hour × task_type) |
| Proactive Scheduler | `core/prediction/proactive.py` | Background scheduler: 07:00 briefings, subscriptions |
| Active Inference | `core/prediction/active_inference.py` | FEP belief state, surprise scoring |

## Phase 5 — Vision

| Module | File | Description |
|--------|------|-------------|
| Screenshot | `core/integrations/vision/screenshot.py` | macOS screencapture + vision model analysis |
| PDF Reader | `core/integrations/vision/pdf_reader.py` | pypdf + chunk → knowledge graph |
| Camera | `core/integrations/vision/camera.py` | OpenCV webcam stub |

## Phase 6 — Model Pantheon

| Model | ID | Strengths | Task Affinity |
|-------|----|-----------|---------------|
| Kimi K2.5 | moonshotai/kimi-k2.5 | reasoning, russian, long context | SIMPLE_CHAT, COMPLEX_REASONING |
| Claude 3.5 | anthropic/claude-3.5-sonnet | coding, structured output | CODE_GENERATION, CODE_REVIEW |
| Gemini Flash | google/gemini-flash-1.5 | vision, speed | VISION_ANALYSIS, MULTIMODAL |
| Perplexity Sonar | perplexity/sonar-pro | search, citations | WEB_SEARCH, RESEARCH |
| Llama 3.2 | llama3.2 (Ollama) | privacy, offline | PRIVATE_FILE |

Strategies: `fast` | `quality` (debate) | `privacy` | `ensemble` (parallel) | `task_routing`

## Phase 7 — Agents

| Module | File | Description |
|--------|------|-------------|
| Researcher | `core/agents/researcher.py` | Multi-step web research + knowledge graph ingest |
| Content Pipeline | `core/agents/content_pipeline.py` | Blog/social/email/script generation |
| Agent Factory | `core/agents/factory.py` | Agent registry + lazy instantiation |
| Projects Manager | `core/projects/manager.py` | Project/Task CRUD with progress tracking |

## Phase 8 — Sync & RPA

| Module | File | Description |
|--------|------|-------------|
| Obsidian Sync | `core/integrations/sync/obsidian.py` | Bidirectional .md↔knowledge graph sync |
| Browser RPA | `core/integrations/rpa/browser.py` | Playwright automation stub |
| Cross-Platform | `core/integrations/sync/cross_platform.py` | JSON export/import + clipboard |

## Phase 9 — Self-Improvement

| Module | File | Description |
|--------|------|-------------|
| Ouroboros | `core/self_improvement/ouroboros.py` | 5-step weekly improvement cycle |
| Swarm | `core/agents/swarm.py` | Parallel multi-agent task coordination |

## Phase 10 — Advanced

| Module | File | Description |
|--------|------|-------------|
| Agent Factory | `core/agents/factory.py` | Dynamic agent creation + registration |
| Self-Healer | `core/healing/self_healer.py` | Health checks + auto-recovery |
| Federated Memory | `core/memory/federated.py` | Cross-device memory stub (local JSON) |

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/chat` | POST | Single-turn chat |
| `/api/ws/chat` | WS | Streaming chat |
| `/api/agents/research` | POST | Research agent |
| `/api/agents/content` | POST | Content creation |
| `/api/agents/swarm` | POST | Swarm coordinator |
| `/api/projects` | GET/POST | Project CRUD |
| `/api/projects/{id}/tasks` | GET/POST | Task management |
| `/api/pal/solve` | POST | PAL math solver |
| `/api/proactive/briefing` | GET | Morning briefing |
| `/api/proactive/habits` | GET | Habit summary |
| `/api/metacognition/stats` | GET | Quality metrics |
| `/api/metacognition/quality` | GET | Quality records |
| `/api/integrations/tiktok/analyze` | POST | TikTok metadata |
| `/api/integrations/github/ingest` | POST | GitHub → graph |
| `/api/integrations/telegram/import` | POST | Telegram → graph |
| `/api/integrations/pdf/ingest` | POST | PDF → graph |
| `/api/vision/screenshot/capture` | POST | Screen capture |
| `/api/vision/pdf/ingest` | POST | PDF ingest |
| `/health` | GET | System health |
