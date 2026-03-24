# ROSA OS — Memory Architecture

## Overview

ROSA OS uses a **3-layer hybrid memory** system that combines in-process speed with
persistent storage and optional vector search.

```
┌─────────────────────────────────────────────────────┐
│  Layer 1: Working Memory (in-process, deque/100)    │
│  • Last 100 conversation turns                       │
│  • Auto-compress at ~8k tokens via Kimi K2.5         │
│  • Zero latency — pure Python                        │
├─────────────────────────────────────────────────────┤
│  Layer 2: Episodic Memory (ChromaDB + SQLite)        │
│  • All conversation turns with embeddings            │
│  • Semantic search: "remember when we discussed X"   │
│  • ChromaDB when available; SQLite fallback          │
├─────────────────────────────────────────────────────┤
│  Layer 3: Graph Memory (entity extraction)           │
│  • Named entities extracted from conversations       │
│  • Relationship graph: person↔topic, concept↔source │
│  • Stored in SQLite knowledge_nodes table            │
└─────────────────────────────────────────────────────┘
```

## Memory Injector

`core/memory/memory_injector.py` prepends a `[ПАМЯТЬ РОЗЫ]` block to every LLM
system prompt, giving Rosa context from all 3 layers:

```
[ПАМЯТЬ РОЗЫ]
Краткосрочная: ... (last 5 turns summary)
Эпизодическая: ... (top 3 semantically similar memories)
Граф знаний: ... (relevant entities)
[/ПАМЯТЬ]
```

## Nightly Consolidation

`core/memory/consolidator.py` runs at 03:00 daily (daemon thread):
1. Scans recent conversations for new facts
2. Deduplicates against existing knowledge graph
3. Writes a diary entry for the day
4. Compresses working memory

## Knowledge Indexer & RAG

`core/knowledge/indexer.py` monitors directories for new files:
- MD5 hash comparison — skips unchanged files
- Optional `watchdog` package for real-time file monitoring
- All indexed content flows into the knowledge graph

`core/knowledge/rag_engine.py` augments prompts with relevant context:
- Parallel search: SQLite + ChromaDB episodic memory
- Deduplication by content prefix
- Wrapped in `[КОНТЕКСТ ИЗ БАЗЫ ЗНАНИЙ]` block

## Session Persistence

`core/memory/store.py` persists to SQLite (`memory/rosa.db`):
- `conversation_turns` — full history with session_id
- `knowledge_nodes` — facts, insights, entities
- `response_quality` — metacognition scores
- `tasks`, `events`, `reflections`

## Privacy

All memory is stored locally. No data is sent to external services beyond the
LLM API calls (OpenRouter). The `ImmutableKernel` monitors core files for tampering.
