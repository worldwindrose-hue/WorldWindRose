# ROSA OS v6 — Release Notes

## Overview

ROSA OS v6 transforms Rosa from a passive AI assistant into a **fully autonomous
self-improving system** running 24/7. This release adds 8 major architectural blocks:

## What's New

### Block 1 — Eternal Hybrid Memory
- **3-layer memory**: Working (deque/100) → Episodic (ChromaDB+SQLite) → Graph (entity extraction)
- **Memory Injector**: every LLM call gets `[ПАМЯТЬ РОЗЫ]` context block
- **Nightly Consolidator**: fact extraction + dedup + diary at 03:00

### Block 2 — Meta-cognition
- **Self-Reflection**: heuristic + LLM analysis after every response
- **CapabilityMap**: 20 skills tracked with level 1.0–5.0, success/failure recording
- **GapAnalyzer**: weekly learning plan from response quality patterns
- **CodeGenesis**: Rosa writes code for herself → sandbox tests → `modules/` only

### Block 3 — VPS Deployment
- **Dockerfile.production**: non-root, HEALTHCHECK, production-ready
- **docker-compose.production.yml**: rosa + nginx + certbot stack
- **sync_memory.sh**: rsync push/pull/auto for memory sync
- **setup_cloudflare_tunnel.sh**: free public URL alternative to ngrok

### Block 4 — Knowledge Indexer + RAG Engine
- **KnowledgeIndexer**: MD5 hash, watchdog real-time monitoring, skip unchanged
- **RAGEngine**: parallel SQLite+ChromaDB retrieval, dedup, `[КОНТЕКСТ]` injection

### Block 5 — Startup Audit + Self-Debugger + Regression Tester
- **StartupAudit**: 6 checks in <10s, score 0–100, JSON report
- **SelfDebugger**: 7 error patterns, patch suggestions to `memory/debug_patches/`
- **RegressionTester**: async pytest runner, 50-run trend history

### Block 6 — Local Router + Cache Manager
- **CacheManager**: SHA-256 semantic cache (500 entries, 1h TTL, JSON persist)
- **LocalRouter**: 5-tier hierarchy: cache → Kimi → Claude → Ollama → stale cache

### Block 7 — Pattern Analyzer + Prediction
- **PatternAnalyzer**: active hours/days, language detection, topic extraction (6 categories)
- **Morning briefing context** and **weekly summary** generators
- User profile persisted to `memory/user_profile.json`

### Block 8 — Transparency Layer
- **ChainOfThought**: extracts `<think>...</think>` from Kimi K2.5, heuristic fallback
- **UsageTracker**: per-day token/cost tracking, weekly reports
- **ImmutableKernel**: SHA-256 manifest for core files, detects tampering

## Stats

| Metric | v5 | v6 |
|--------|-----|-----|
| Tests | 188 | 284 |
| Core modules | ~45 | ~65 |
| API endpoints | ~80 | ~100 |
| Memory layers | 1 (SQLite) | 3 (Working + Episodic + Graph) |
| Autonomy | Passive | 24/7 self-improving |

## API Additions

```
GET  /api/audit/startup          — startup audit report
POST /api/audit/startup/run      — fresh audit
GET  /api/audit/debug            — error pattern scan
POST /api/audit/regression/run   — trigger regression tests
GET  /api/cache/stats            — cache hit rate
GET  /api/cache/router/stats     — routing statistics
GET  /api/prediction/profile     — user behavioral profile
GET  /api/prediction/morning-brief
GET  /api/prediction/weekly-report
GET  /api/transparency/cot/recent  — chain-of-thought traces
GET  /api/transparency/usage/today
GET  /api/transparency/kernel/status
POST /api/transparency/kernel/seal
```

## Upgrade Notes

1. No breaking changes to existing API
2. New deps: `telethon` (optional), `watchdog` (optional)
3. Run `POST /api/transparency/kernel/seal` after upgrading to record new hashes
4. New memory files created on first run: `user_profile.json`, `kernel_manifest.json`, etc.

## Contributors

Built by Claude Code (Sonnet 4.6) under direction of @makbuk.
ROSA's brain: Kimi K2.5 (moonshotai/kimi-k2.5 via OpenRouter).
