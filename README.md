# 🌹 ROSA OS v3 — Гибридный Джарвис

Автономный ИИ-ассистент с памятью, графом знаний, пантеоном моделей и самоулучшением.

**Мозг:** Kimi K2.5 (Moonshot AI) через OpenRouter
**Строитель:** Claude Code
**UI:** Русскоязычный ChatGPT-уровень

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

# 4. Открыть в браузере
open http://localhost:8000

# 5. Запустить тесты
python3 -m pytest tests/ -v
```

---

## Возможности

| Функция | Статус | Как включить |
|---------|--------|-------------|
| Чат с Kimi K2.5 | ✅ | `OPENROUTER_API_KEY` в .env |
| Локальный чат (Ollama) | ✅ | Запустить Ollama + `ollama pull llama3.2` |
| Загрузка файлов (PDF, txt) | ✅ | Кнопка 📎 в интерфейсе |
| Парсинг URL | ✅ | Кнопка 🌐 в интерфейсе |
| Голос (браузерный STT) | ✅ | Кнопка 🎤 (Chrome/Safari) |
| Голос (Whisper + TTS) | ⚙️ | `OPENAI_DIRECT_KEY` в .env |
| Граф знаний | ✅ | Вкладка «Знания» |
| Self-improvement цикл | ✅ | Вкладка «Улучшение» → «Запустить цикл» |
| Навыки и прогресс | ✅ | `POST /api/self-improve/skills` |
| Пантеон моделей | ✅ | `config/models.yaml` + Настройки |
| Telegram | 🔧 | `TELEGRAM_BOT_TOKEN` + python-telegram-bot |
| Discord | 🔧 | `DISCORD_TOKEN` + discord.py |
| Gmail | 🔧 | `GMAIL_CREDENTIALS` + google-api-python-client |
| Google Drive | 🔧 | `GOOGLE_CREDENTIALS` + google-api-python-client |
| Perplexity Computer | 🔮 | Будущее |

✅ Готово · ⚙️ Нужен ключ · 🔧 Требует настройки · 🔮 Планируется

---

## Переменные окружения (.env)

```env
# Обязательно
OPENROUTER_API_KEY=sk-or-...

# Опционально: голос (Whisper STT + TTS)
OPENAI_DIRECT_KEY=sk-...

# Опционально: Telegram
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...

# Опционально: Google (Gmail + Drive)
GMAIL_CREDENTIALS=/path/to/credentials.json
GOOGLE_CREDENTIALS=/path/to/credentials.json
```

---

## Структура проекта

```
rosa-os/
├── core/
│   ├── app.py                    # FastAPI сервер
│   ├── config.py                 # pydantic-settings
│   ├── api/                      # REST + WebSocket эндпоинты
│   │   ├── chat.py, sessions.py, folders.py
│   │   ├── files.py, voice.py, parse_url.py
│   │   ├── tasks.py, memory.py
│   │   ├── self_improve.py       # + Skills API (v3)
│   │   ├── knowledge.py          # Граф знаний (v3)
│   │   └── models.py             # Пантеон моделей (v3)
│   ├── knowledge/
│   │   └── graph.py              # add_insight, query_graph (v3)
│   ├── memory/
│   │   ├── models.py             # SQLAlchemy ORM (+ KnowledgeNode, Skill)
│   │   └── store.py              # Async CRUD
│   ├── router/
│   │   ├── __init__.py           # RosaRouter (HybridRouter wrapper)
│   │   └── models_router.py      # ModelsRouter (Pantheon) (v3)
│   ├── self_improvement/
│   │   ├── collector.py, analyzer.py, patcher.py
│   ├── integrations/
│   │   ├── computer_use.py, vision.py
│   │   ├── socials/              # Telegram, Discord, Twitter (v3)
│   │   ├── mail/                 # Gmail (v3)
│   │   └── workspace/            # Google Drive (v3)
│   └── policies.py
├── desktop/
│   ├── index.html                # Русский UI (v3)
│   ├── style.css
│   └── app.js
├── config/
│   ├── models.yaml               # Пантеон моделей (v3)
│   ├── settings.yaml
│   └── policies.yaml
├── tests/                        # 45 тестов (v3: +25 новых)
├── docs/
│   ├── CONSTITUTION.md           # Неизменяемый
│   ├── PLAN.md
│   └── PLAN_v3.md               # Архитектура v3
├── experimental/                 # Self-improvement sandbox
├── memory/                       # SQLite DB + uploads
└── hybrid_assistant.py           # HybridRouter (агенты)
```

---

## API (основные эндпоинты)

| Метод | Путь | Описание |
|-------|------|---------|
| WS | `/api/ws/chat` | Стриминг чата |
| POST | `/api/chat` | Одиночный запрос |
| GET | `/api/sessions` | Список сессий |
| POST | `/api/files/upload` | Загрузить файл |
| POST | `/api/parse-url` | Парсить URL |
| POST | `/api/knowledge/insights` | Добавить инсайт в граф |
| GET | `/api/knowledge/nodes` | Список узлов знаний |
| GET | `/api/knowledge/graph?query=` | Поиск по графу |
| GET | `/api/models` | Список моделей |
| PATCH | `/api/models/{id}` | Вкл/выкл модель |
| GET | `/api/models/strategies` | Стратегии маршрутизации |
| POST | `/api/self-improve/run` | Запустить цикл улучшения |
| GET | `/api/self-improve/skills` | Навыки Rosa |
| POST | `/api/self-improve/skills` | Создать навык |
| POST | `/api/self-improve/skills/{id}/assess` | Оценить навык |
| GET | `/docs` | Swagger UI |

---

## Горячие клавиши

| Комбинация | Действие |
|-----------|---------|
| Ctrl/Cmd+N | Новый чат |
| Ctrl/Cmd+U | Прикрепить файл |
| Ctrl/Cmd+M | Голосовой ввод |
| Ctrl/Cmd+L | Режим URL |
| Ctrl/Cmd+K | Перейти к «Знаниям» |
| Ctrl/Cmd+Shift+L | Live-режим |
| Escape | Закрыть модал |

---

## Тесты

```bash
python3 -m pytest tests/ -v
# 45 тестов:
# test_api.py           (6)
# test_knowledge.py     (7)  ← v3
# test_memory.py        (6)
# test_models_router.py (9)  ← v3
# test_router.py        (7)
# test_skills.py        (9)  ← v3
```

---

## Принципы (CONSTITUTION.md)

1. **Rosa знает свои границы** — никаких претензий на выполненное без проверки
2. **Одобрение человека** обязательно для файлов, системных изменений, финансов
3. **Все патчи в experimental/** — никакого тихого самоизменения
4. **Память честна** — что хранится, то видно
5. **Внешние данные — недоверенные** — всегда
