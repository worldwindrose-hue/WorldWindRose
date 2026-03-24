# ROSA OS v4 — API Reference

Base URL: `http://localhost:8000`
Interactive docs: `/api/docs` (Swagger UI)

---

## Chat

### POST /api/chat
Single-turn chat request.

```json
// Request
{"message": "Привет!", "mode": null, "session_id": null}

// Response
{
  "response": "Привет! Чем могу помочь?",
  "brain_used": "cloud",
  "model": "moonshotai/kimi-k2.5",
  "task_type": "SIMPLE_CHAT",
  "confidence": 0.9,
  "session_id": "uuid"
}
```

### WS /api/ws/chat
WebSocket streaming chat.

```json
// Client sends
{"message": "Расскажи про Python", "mode": "cloud"}

// Server sends (sequence)
{"type": "thinking", "session_id": "uuid"}
{"type": "response", "response": "...", "brain_used": "cloud", "model": "...", "task_type": "...", "confidence": 0.9}
// OR on error:
{"type": "error", "message": "..."}
```

---

## Agents

### POST /api/agents/research
Multi-step research pipeline.
```json
// Request
{"question": "What is quantum computing?", "session_id": "research"}

// Response
{"question": "...", "report": "...", "facts": [...], "nodes_created": 5, "queries_run": 3}
```

### POST /api/agents/content
Content creation pipeline.
```json
// Request
{"topic": "AI trends 2025", "content_type": "blog_post", "audience": "developers", "research": true}

// Response
{"topic": "...", "outline": "...", "draft": "...", "final": "...", "facts_used": 8}
```

### POST /api/agents/swarm
Run multiple agents in parallel.
```json
// Request
{"task": "Analyze competitors", "roles": ["researcher", "analyst", "writer"]}

// Response
{"task": "...", "synthesis": "...", "agent_results": [...], "agents_succeeded": 3}
```

---

## Projects

### GET /api/projects
List all projects. Optional: `?status=active`

### POST /api/projects
```json
{"name": "My Project", "goal": "Build something great", "deadline": "2025-12-31"}
```

### GET /api/projects/{id}
Returns project with tasks and progress percentage.

### PATCH /api/projects/{id}
```json
{"status": "completed", "goal": "Updated goal"}
```

### POST /api/projects/{id}/tasks
```json
{"description": "Implement feature X", "priority": 1}
```

### PATCH /api/projects/tasks/{id}/complete
Mark task as done.

---

## PAL (Math Solver)

### POST /api/pal/solve
```json
// Request
{"question": "Сколько будет 15% от 240?"}

// Response
{"answer": "36", "code": "result = 240 * 0.15\nprint('Answer:', result)", "method": "code_execution", "success": true}
```

---

## Proactive

### GET /api/proactive/briefing
On-demand morning briefing.
```json
{"type": "morning_briefing", "predictions": [...], "pending_tasks": [...], "message": "Доброе утро!..."}
```

### GET /api/proactive/habits
Habit graph summary.

### GET /api/proactive/inference
Active inference belief state.
```json
{"beliefs": {"code": 0.35, "math": 0.12, ...}, "observations": 42, "free_energy": 1.8}
```

### POST /api/proactive/subscriptions
```json
{"name": "HN Feed", "source_type": "rss", "source_url": "https://news.ycombinator.com/rss", "keywords": ["AI", "Python"]}
```

---

## Metacognition

### GET /api/metacognition/stats
```json
{
  "completeness_avg": 7.8,
  "accuracy_avg": 8.1,
  "helpfulness_avg": 7.5,
  "overall_avg": 7.8,
  "total_assessments": 42,
  "top_weak_points": ["краткость", "примеры", "структура"]
}
```

### GET /api/metacognition/quality?session_id=&limit=20
List quality assessments.

---

## Integrations

### POST /api/integrations/tiktok/analyze
```json
{"url": "https://www.tiktok.com/@user/video/123"}
// Response: {"nodes_created": 3, "items_found": 1, ...}
```

### POST /api/integrations/github/ingest
```json
{"url": "https://github.com/tiangolo/fastapi", "max_files": 10}
// Response: {"nodes_created": 12, "files_processed": 8, ...}
```

### POST /api/integrations/telegram/auth/start
```json
{}
// Response: {"status": "code_sent", "phone": "+7999..."}
```

### POST /api/integrations/telegram/auth/verify
```json
{"code": "12345"}
// Response: {"status": "authenticated", "session_length": 256}
```

### POST /api/integrations/telegram/import
```json
{"chat_id": "@username", "limit": 100}
```

### POST /api/integrations/pdf/ingest
```json
{"path": "/Users/me/docs/report.pdf"}
```

---

## Vision

### POST /api/vision/screenshot/capture
Returns `{"success": true, "base64": "...", "width": 2560, "height": 1600}`

### POST /api/vision/screenshot/analyze
```json
{"prompt": "What application is open on screen?"}
// Response: {"success": true, "description": "...", "model": "google/gemini-flash-1.5"}
```

### POST /api/vision/pdf/ingest
```json
{"path": "/path/to/file.pdf", "session_id": "pdf"}
```

---

## Self-Improvement

### POST /api/self-improve/run
Trigger the Ouroboros improvement cycle.

### GET /api/self-improve/proposals
List pending improvement proposals.

### POST /api/self-improve/proposals/{id}/apply
Apply a patch (Human Gate — requires explicit click).

---

## System

### GET /health
```json
{"status": "ok", "version": "4.0.0"}
```
