# 🌹 ROSA OS v6 — Автономная Self-Improving AI

Полностью автономная ИИ-система с 3-слойной памятью, метакогницией,
самоулучшением, локальным роутером и прозрачностью решений.

**Мозг:** Kimi K2.5 (Moonshot AI) через OpenRouter
**Строитель:** Claude Code
**UI:** Русскоязычный ChatGPT-уровень + PWA для iPhone

---

## Быстрый старт

```bash
# 1. Скопировать и заполнить .env
cp .env.example .env
# Обязательно: OPENROUTER_API_KEY=your_key

# 2. Установить зависимости
pip3 install fastapi uvicorn sqlalchemy aiosqlite openai ollama \
             pydantic-settings python-dotenv rich beautifulsoup4 \
             httpx pypdf lxml pyyaml

# 3. Запустить сервер
uvicorn core.app:app --reload --port 8000
# Или со скриптом (ngrok QR для iPhone):
./scripts/start_rosa.sh

# 4. Открыть в браузере
open http://localhost:8000

# 5. Запустить тесты
python3 -m pytest tests/ -v
# → 284 тестов ✅
```

---

## Архитектура v6

```
┌─── 3-Layer Memory ────────────────────────────────────┐
│  Working (100 turns) → Episodic (ChromaDB) → Graph    │
└───────────────────────────────────────────────────────┘
┌─── Local Router ──────────────────────────────────────┐
│  Cache → Kimi K2.5 → Claude → Ollama → Stale Cache    │
└───────────────────────────────────────────────────────┘
┌─── Self-Improvement ──────────────────────────────────┐
│  Metacognition → CapabilityMap → CodeGenesis           │
└───────────────────────────────────────────────────────┘
┌─── Transparency ──────────────────────────────────────┐
│  ChainOfThought → UsageTracker → ImmutableKernel       │
└───────────────────────────────────────────────────────┘
```

---

## Возможности

| Функция | Статус | Блок |
|---------|--------|------|
| Чат с Kimi K2.5 | ✅ | Core |
| 3-слойная память | ✅ | Block 1 |
| Метакогниция + оценка ответов | ✅ | Block 2 |
| CapabilityMap (20 навыков) | ✅ | Block 2 |
| CodeGenesis (Роза пишет код) | ✅ | Block 2 |
| VPS деплой (Docker) | ✅ | Block 3 |
| Cloudflare Tunnel | ✅ | Block 3 |
| KnowledgeIndexer + RAG | ✅ | Block 4 |
| StartupAudit (<10s) | ✅ | Block 5 |
| SelfDebugger | ✅ | Block 5 |
| RegressionTester | ✅ | Block 5 |
| LocalRouter + SemanticCache | ✅ | Block 6 |
| PatternAnalyzer (профиль) | ✅ | Block 7 |
| Утренний брифинг | ✅ | Block 7 |
| ChainOfThought визуализация | ✅ | Block 8 |
| UsageTracker + стоимость | ✅ | Block 8 |
| ImmutableKernel | ✅ | Block 8 |
| TikTok парсинг (yt-dlp) | ✅ | Integrations |
| GitHub → граф знаний | ✅ | Integrations |
| Telegram (Telethon) | ✅ | Integrations |
| Web Push уведомления | ✅ | PWA |
| iPhone PWA + QR код | ✅ | Mobile |

---

## Структура проекта

```
rosa-os/
├── core/
│   ├── app.py                    # FastAPI сервер
│   ├── config.py                 # pydantic-settings
│   ├── api/                      # 30+ REST + WebSocket роутеров
│   ├── memory/
│   │   ├── eternal.py            # 3-layer memory [v6]
│   │   ├── memory_injector.py    # context injection [v6]
│   │   ├── consolidator.py       # nightly consolidation [v6]
│   │   ├── models.py, store.py   # SQLAlchemy ORM + CRUD
│   ├── metacognition/
│   │   ├── evaluator.py          # response quality scoring
│   │   ├── self_reflection.py    # per-response reflection [v6]
│   │   ├── capability_map.py     # 20 skills tracking [v6]
│   │   └── gap_analyzer.py       # weekly learning plan [v6]
│   ├── self_improvement/
│   │   ├── code_genesis.py       # Rosa writes code [v6]
│   │   ├── collector.py, analyzer.py, patcher.py
│   ├── knowledge/
│   │   ├── indexer.py            # MD5 + watchdog [v6]
│   │   ├── rag_engine.py         # RAG retrieval [v6]
│   │   └── graph.py              # knowledge graph
│   ├── audit/
│   │   ├── startup_audit.py      # 6 checks, score [v6]
│   │   ├── self_debugger.py      # error patterns [v6]
│   │   └── regression_tester.py  # pytest runner [v6]
│   ├── router/
│   │   ├── cache_manager.py      # semantic cache [v6]
│   │   ├── local_router.py       # 5-tier routing [v6]
│   │   └── models_router.py      # model pantheon
│   ├── prediction/
│   │   ├── pattern_analyzer.py   # user profiling [v6]
│   │   ├── proactive.py          # morning briefing
│   │   └── habit_graph.py
│   ├── transparency/
│   │   ├── chain_of_thought.py   # CoT visualization [v6]
│   │   └── usage_report.py       # token/cost tracking [v6]
│   ├── security/
│   │   ├── immutable_kernel.py   # file hash guard [v6]
│   │   └── firewall.py
│   └── integrations/
│       ├── socials/tiktok.py     # TikTok via yt-dlp
│       ├── socials/telegram_user.py  # Telethon
│       └── workspace/github.py   # GitHub REST API
├── desktop/
│   ├── index.html, style.css, app.js  # PWA UI
│   ├── manifest.json             # PWA manifest
│   └── sw.js                     # Service Worker
├── scripts/
│   ├── start_rosa.sh             # ngrok + uvicorn
│   ├── deploy_vps.sh             # Docker VPS deploy
│   ├── sync_memory.sh            # rsync memory
│   └── setup_cloudflare_tunnel.sh
├── tests/                        # 284 тестов ✅
├── docs/
│   ├── CONSTITUTION.md
│   ├── MEMORY_ARCHITECTURE.md    # [v6]
│   ├── SELF_IMPROVEMENT.md       # [v6]
│   ├── DEPLOYMENT_VPS.md         # [v6]
│   └── RELEASE_v6.md             # [v6]
├── config/
│   ├── policies.yaml
│   └── models.yaml
└── Dockerfile.production         # [v6]
```

---

## Ключевые API (v6)

| Метод | Путь | Описание |
|-------|------|---------|
| WS | `/api/ws/chat` | Стриминг чата |
| POST | `/api/chat` | Одиночный запрос |
| GET | `/api/audit/startup` | Отчёт о запуске |
| GET | `/api/audit/debug` | Анализ ошибок |
| GET | `/api/cache/stats` | Статистика кэша |
| GET | `/api/prediction/profile` | Профиль пользователя |
| GET | `/api/prediction/morning-brief` | Утренний брифинг |
| GET | `/api/transparency/cot/recent` | Цепочки мысли |
| GET | `/api/transparency/usage/today` | Использование токенов |
| GET | `/api/transparency/kernel/status` | Целостность ядра |
| POST | `/api/integrations/tiktok/analyze` | TikTok анализ |
| POST | `/api/integrations/github/ingest` | GitHub → граф |
| GET | `/docs` | Swagger UI (284 эндпоинта) |

---

## iPhone / Мобильный доступ

```bash
# Запустить с публичным URL и QR-кодом
./scripts/start_rosa.sh

# Или Cloudflare Tunnel (бесплатный, без лимитов)
./scripts/setup_cloudflare_tunnel.sh
cloudflared tunnel run rosa-os
```

Сканируй QR-код iPhone Camera → добавь на Home Screen как PWA →
получай Push-уведомления от Розы.

---

## Принципы (CONSTITUTION.md)

1. **Rosa знает свои границы** — никаких претензий на выполненное без проверки
2. **Одобрение человека** обязательно для файлов, системных изменений, финансов
3. **Все патчи в experimental/** — никакого тихого самоизменения ядра
4. **Память честна** — что хранится, то видно
5. **Внешние данные — недоверенные** — всегда

---

## Документация

- [`docs/MEMORY_ARCHITECTURE.md`](docs/MEMORY_ARCHITECTURE.md) — 3-layer memory
- [`docs/SELF_IMPROVEMENT.md`](docs/SELF_IMPROVEMENT.md) — metacognition cycle
- [`docs/DEPLOYMENT_VPS.md`](docs/DEPLOYMENT_VPS.md) — Docker VPS deploy
- [`docs/RELEASE_v6.md`](docs/RELEASE_v6.md) — release notes
- [`docs/CONSTITUTION.md`](docs/CONSTITUTION.md) — immutable principles
