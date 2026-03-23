# ROSA OS v3 — Архитектура Гибридного Джарвиса

## Что это

ROSA OS v3 — эволюция автономного ИИ-ассистента с:
- **Графом знаний** — Rosa запоминает и связывает знания
- **Пантеоном моделей** — несколько LLM как команда экспертов
- **Эволюционным self-improvement** — навыки, оценки, прогресс
- **Русским UI** — полностью локализованный интерфейс
- **Архитектурой интеграций** — заготовки для Telegram, Gmail, Discord, Google Drive

---

## Слои системы

```
Браузер (ROSA Desktop)
    ↓  WebSocket / REST
FastAPI (core/app.py)
    ├── Chat API (/api/chat, /api/ws/chat)
    ├── Sessions API (/api/sessions)
    ├── Knowledge API (/api/knowledge)      ← NEW v3
    ├── Models API (/api/models)            ← NEW v3
    ├── Self-Improve API (/api/self-improve)
    │     └── Skills (/skills)             ← NEW v3
    ├── Files, Voice, URL Parser
    └── Tasks, Memory, Folders
         ↓
SQLite Memory (memory/rosa.db)
    ├── Tasks, Events, Reflections
    ├── ChatSessions, Folders, ConversationTurns
    ├── KnowledgeNode, KnowledgeEdge      ← NEW v3
    ├── Skill, SkillProgress              ← NEW v3
    └── UploadedFile
         ↓
LLM Routing
    ├── HybridRouter (cloud/local)
    │     ├── Cloud: Kimi K2.5 (OpenRouter)
    │     └── Local: Ollama (llama3.2)
    └── ModelsRouter (Pantheon)            ← NEW v3
          ├── fast: одна модель
          ├── quality: debate + синтез
          └── privacy: local-first
```

---

## Новые модули v3

### core/knowledge/graph.py
Три функции:
- `add_insight(text, metadata)` — LLM разбирает текст на узлы/связи и сохраняет в БД
- `add_from_dialog(turn, session_id)` — извлекает сущности из реплик
- `query_graph(query, limit)` — поиск по узлам + связанные рёбра

### core/router/models_router.py
`ModelsRouter`:
- Читает `config/models.yaml`
- `route(task, strategy)` — вызывает нужные модели
- Стратегии: `fast`, `quality` (дебаты), `privacy` (локально)

### core/api/knowledge.py
- `POST /api/knowledge/insights` — добавить инсайт
- `GET /api/knowledge/graph?query=` — поиск по графу
- `GET /api/knowledge/nodes?type=` — список узлов

### core/api/models.py
- `GET /api/models` — список моделей
- `PATCH /api/models/{id}` — вкл/выкл
- `GET /api/models/strategies` — стратегии

### Skills в core/api/self_improve.py
- `GET /api/self-improve/skills`
- `POST /api/self-improve/skills`
- `POST /api/self-improve/skills/{id}/assess`

### core/integrations/socials/
- `base.py` — `BaseSocialConnector` ABC
- `telegram.py`, `discord.py`, `twitter.py` — заглушки

### core/integrations/mail/gmail.py
Заглушка с интерфейсом `read/send/label`.

### core/integrations/workspace/google_drive.py
Заглушка с интерфейсом `list_files/read_file/upload_file`.

---

## База данных (новые таблицы v3)

```sql
knowledge_nodes:
  id, type (insight|entity|concept|fact), title, summary,
  source_type (manual|dialog|file|url), source_id,
  created_at, updated_at

knowledge_edges:
  id, from_node_id → knowledge_nodes,
  to_node_id → knowledge_nodes,
  relation_type, weight, created_at

skills:
  id, name (unique), description, created_at

skill_progress:
  id, skill_id → skills,
  level (1.0–5.0), goal (1.0–5.0), notes,
  assessed_at, assessed_by (auto|owner)
```

---

## Конфигурация моделей (config/models.yaml)

| Модель | Провайдер | По умолчанию |
|--------|-----------|--------------|
| kimi_k2_5 | openrouter | ✅ включена |
| claude_sonnet | openrouter | ✅ включена |
| llama3_local | ollama | ✅ включена |
| gemini_flash | openrouter | ❌ нет ключа |
| gpt_4o | openrouter | ❌ нет ключа |
| grok_3 | openrouter | ❌ нет ключа |
| perplexity_sonar | openrouter | ❌ нет ключа |

---

## Статус тестов

```
45/45 тестов проходят:
- tests/test_api.py        (6 тестов)
- tests/test_knowledge.py  (7 тестов)  ← NEW
- tests/test_memory.py     (6 тестов)
- tests/test_models_router.py (9 тестов) ← NEW
- tests/test_router.py     (7 тестов)
- tests/test_skills.py     (9 тестов)  ← NEW
```

---

## Горячие клавиши (UI)

| Комбинация | Действие |
|-----------|---------|
| Ctrl+N / Cmd+N | Новый чат |
| Ctrl+U / Cmd+U | Прикрепить файл |
| Ctrl+M / Cmd+M | Голосовой ввод |
| Ctrl+L / Cmd+L | Режим URL |
| Ctrl+K / Cmd+K | Перейти к Знаниям |
| Ctrl+Shift+L | Live-режим |
| Escape | Закрыть модал / выйти из URL-режима |

---

## Инварианты (нельзя нарушать)

- `docs/CONSTITUTION.md` — неизменяем, никакой автоматизации
- Self-improvement патчи только в `experimental/` — никакого авто-применения
- Все новые таблицы создаются через `Base.metadata.create_all` (alembic-ready)
- Интеграции всегда `raise NotImplementedError` пока ключи не настроены
