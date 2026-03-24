# ROSA OS — Self-Improvement System

## Overview

ROSA OS has a multi-layered self-improvement architecture that continuously
analyzes Rosa's responses, identifies weaknesses, and generates improvements.

## Metacognition Layer

After every response, `core/metacognition/evaluator.py` fires a background task
(zero latency for the user) that asks Kimi K2.5 to evaluate the response:

```json
{
  "completeness": 8.5,
  "accuracy": 9.0,
  "helpfulness": 8.0,
  "overall": 8.5,
  "weak_points": ["краткость", "отсутствие примеров"],
  "improvement_hint": "Добавь конкретный пример кода"
}
```

Results stored in `response_quality` table (SQLite).

## Self-Reflection

`core/metacognition/self_reflection.py` runs a heuristic + optional LLM analysis:
- Detects uncertain language ("не уверен", "возможно", "может быть")
- Estimates hallucination risk from response length vs. question complexity
- Logs to `memory/self_reflection.log`

## CapabilityMap

`core/metacognition/capability_map.py` tracks 20 skills across 6 categories:

| Category | Skills |
|----------|--------|
| Coding | python, javascript, debugging, code_review, architecture |
| Analysis | data_analysis, research, summarization, fact_checking |
| Creative | writing, ideation, storytelling, translation |
| Planning | task_planning, project_management, scheduling |
| Knowledge | knowledge_retrieval, web_search, document_analysis |
| Communication | explanation, teaching, empathy |

Each skill has a level (1.0–5.0):
- `record_success(name)` → level += 0.1 (max 5.0)
- `record_failure(name)` → level -= 0.05 (min 1.0)
- Level < 2.5 = "gap" → triggers learning suggestions

## CodeGenesis

`core/self_improvement/code_genesis.py` enables Rosa to write modules for herself:

```
1. analyze_need(task) → requirements
2. generate_module(requirements) → Python code via Kimi
3. sandbox_test(code) → run pytest in isolated /tmp/rosa_sandbox_{uuid}/
4. apply_module(name, code) → write to modules/ ONLY
```

All generated code goes to `modules/` — never to `core/`. Auto git commit on apply.
Max 3 retry attempts per genesis task.

## Self-Debugger

`core/audit/self_debugger.py` scans logs for 7 known error patterns:
- Missing dependencies → suggest `pip install`
- SQLite schema errors → suggest migration
- Network timeouts → suggest retry with backoff
- Permission errors, JSON errors, key errors, connection errors

Fix suggestions saved to `memory/debug_patches/` — never auto-applied.

## Weekly Gap Report

`core/metacognition/gap_analyzer.py` generates weekly learning plans:
- Reads reflection log for recurring weak_points
- Clusters by category
- Generates a structured learning plan via Kimi K2.5

## Cycle

```
User asks question
    ↓
Rosa answers (Kimi K2.5)
    ↓
[Background: evaluate_response()]
    ↓
[Background: reflect_on_response()]
    ↓
[Background: record capability success/failure]
    ↓
Weekly: gap_report() → learning plan
    ↓
Weekly: self-improve run → proposals in experimental/
    ↓
[Human approves] → apply to codebase
```
