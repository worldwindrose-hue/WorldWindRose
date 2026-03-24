# ROSA OS v5 — API Reference

Base URL: `http://localhost:8000`

---

## Core

### `GET /health`
Returns server health.
```json
{"status": "ok", "version": "5.0.0"}
```

### `POST /api/chat`
Send a chat message (HTTP fallback).
```json
// Request
{"message": "Hello Rosa", "session_id": "abc123"}
// Response
{"response": "Hi! How can I help?", "session_id": "abc123"}
```

### `WS /api/ws/chat`
WebSocket streaming chat.
```json
// Send
{"message": "Hello", "session_id": "abc123"}
// Receive (streaming)
{"type": "token", "token": "Hi"}
// Receive (final)
{"type": "response", "response": "Hi! How can I help?"}
```

---

## Status (Phase 0)

### `GET /api/status/current`
```json
{"status": "ОНЛАЙН", "color": "green", "detail": "Готова к работе", "ts": "..."}
```

### `GET /api/status/history?limit=50`
```json
[{"status": "ДУМАЕТ", "color": "yellow", "detail": "...", "ts": "..."}]
```

### `WS /api/ws/status`
Real-time status stream. Sends current status immediately, then updates.

---

## Filesystem (Phase 2)

### `GET /api/fs/list?path=/path/to/dir`
### `GET /api/fs/read?path=/path/to/file`
### `POST /api/fs/write`
```json
{"path": "/path/to/file", "content": "..."}
```
### `GET /api/fs/search?q=query&root=/path&ext=.py`
### `GET /api/fs/tree?root=/path&depth=3`
### `GET /api/fs/zones`
Returns list of allowed access zones.

---

## Search (Phase 4)

### `POST /api/search`
```json
// Request
{"query": "What is Kimi K2.5?", "sources": ["duckduckgo", "wikipedia"], "synthesize": true}
// Response
{"results": [...], "synthesis": "Kimi K2.5 is..."}
```

### `POST /api/search/subscribe`
```json
{"topic": "AI news", "interval_minutes": 60}
```

### `GET /api/search/subscriptions`
### `DELETE /api/search/subscribe/{topic}`

---

## macOS (Phase 5)

### `POST /api/mac/run`
```json
{"script_type": "shell", "command": "echo hello"}
// or
{"script_type": "applescript", "command": "tell application \"Finder\" to get name of front window"}
```

### `GET /api/mac/status` — CPU/RAM/disk/network
### `GET /api/mac/screenshot` — base64 PNG
### `GET /api/mac/apps` — running applications
### `GET /api/mac/system` — full system info
### `POST /api/mac/notify`
```json
{"title": "Rosa", "message": "Done!", "sound": "default"}
```

---

## Telegram (Phase 6)

### `POST /api/telegram/webhook`
Receives updates from Telegram Bot API.

### `POST /api/telegram/send`
```json
{"chat_id": "123456", "text": "Hello from Rosa"}
```

### `POST /api/telegram/webhook/set`
```json
{"webhook_url": "https://your-tunnel.ngrok.io/api/telegram/webhook"}
```

---

## Coding (Phase 7)

### `POST /api/coding/execute`
```json
{"language": "python", "code": "print(42)", "timeout": 30}
// Response
{"success": true, "output": "42\n"}
```

### `POST /api/coding/execute/explain`
```json
{"language": "python", "code": "...", "timeout": 30}
// Response
{"success": true, "output": "...", "explanation": "This code..."}
```

### `POST /api/coding/write`
```json
{"path": "core/new_module.py", "task": "Create a class that..."}
// Response
{"success": true, "path": "...", "test_result": "passed"}
```

### `POST /api/coding/refactor`
```json
{"path": "core/old.py", "instruction": "Make it async"}
```

### `GET /api/coding/git/log`
### `GET /api/coding/git/diff`
### `GET /api/coding/git/status`

---

## Swarm (Phase 8)

### `POST /api/swarm/auto`
```json
// Request
{"task": "Analyze this codebase and find performance issues", "max_agents": 8}
// Response
{"agents": [...], "synthesis": "Found 3 bottlenecks: ...", "complexity": "complex"}
```

### `GET /api/swarm/roles` — Available agent roles
### `POST /api/swarm/complexity`
```json
{"task": "hello"} → {"complexity": "simple", "agent_count": 1}
```

---

## Token Economy (Phase 9)

### `GET /api/economy/stats`
```json
{"today_cost": 0.0042, "month_cost": 0.12, "cache_hits": 15, "cache_misses": 83}
```

### `GET /api/economy/alternatives?model=gpt-4o`
### `GET /api/economy/estimate?daily=100&tokens=500`
### `GET /api/economy/env` — Configured/missing API keys

---

## Mission Planner (Phase 10)

### `POST /api/planning/missions`
```json
{"message": "Create a Python script that monitors my CPU every 5 seconds"}
// Response: Mission object with steps requiring approval
```

### `GET /api/planning/missions`
### `GET /api/planning/missions/{id}`
### `POST /api/planning/missions/{id}/approve`
```json
{"approved_step_ids": ["step-1", "step-2"]}
```
### `POST /api/planning/missions/{id}/execute`
### `POST /api/planning/missions/{id}/cancel`

---

## Integrations

### `POST /api/integrations/tiktok/analyze`
```json
{"url": "https://tiktok.com/@user/video/123"}
// Response
{"nodes_added": 1, "title": "...", "tags": [...]}
```

### `POST /api/integrations/github/ingest`
```json
{"url": "https://github.com/tiangolo/fastapi", "max_files": 10}
// Response
{"files_processed": 8, "nodes_added": 8}
```

### `POST /api/integrations/telegram/auth/start`
```json
{"api_id": "12345", "api_hash": "abc...", "phone": "+79001234567"}
// Response
{"phone_code_hash": "xxx"}
```

### `POST /api/integrations/telegram/auth/verify`
```json
{"code": "12345", "phone_code_hash": "xxx"}
```

### `POST /api/integrations/telegram/import`
```json
{"chat_id": "@username", "limit": 100}
// Response
{"messages_imported": 100, "nodes_added": 23}
```

---

## Metacognition

### `GET /api/metacognition/quality?session_id=&limit=20`
### `GET /api/metacognition/stats`
```json
{
  "completeness_avg": 7.8, "accuracy_avg": 8.1,
  "helpfulness_avg": 7.5, "overall_avg": 7.8,
  "total_evaluated": 42, "top_weak_points": ["brevity", "examples"]
}
```

---

## Self-Improvement

### `POST /api/self-improve/run`
### `GET /api/self-improve/proposals`
### `POST /api/self-improve/proposals/{id}/apply`

---

## Memory

### `GET /api/memory/reflections`
### `GET /api/memory/turns?session_id=&limit=100`
### `GET /api/memory/events`
### `GET /api/memory/knowledge?query=&limit=20`
### `GET /api/memory/knowledge/stats`
### `POST /api/memory/backup`
