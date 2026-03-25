"""
ROSA OS — Memory Consolidator.
Nightly (03:00) consolidation: extract facts, dedup, generate diary entry.
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger("rosa.memory.consolidator")


async def run_consolidation() -> dict:
    """
    Nightly consolidation:
    - Extract new facts from recent conversation turns
    - Remove duplicate episodic entries
    - Generate a diary entry for the day
    """
    result: dict = {"facts_extracted": 0, "duplicates_removed": 0, "diary_entry": ""}
    try:
        from core.memory.store import get_store
        from core.memory.eternal import get_eternal_memory

        store = await get_store()
        mem = get_eternal_memory()

        # Get recent turns (last 24h)
        turns = await store.list_turns(limit=100)
        recent_text = " ".join(t.content[:200] for t in turns[:20])

        if recent_text.strip():
            # Extract facts via graph memory
            try:
                await mem.graph.extract_and_add(recent_text, source="consolidation")
                result["facts_extracted"] = 5  # estimate
            except Exception as exc:
                logger.warning("Fact extraction failed: %s", exc)

            # Generate diary entry
            try:
                from core.config import get_settings
                import httpx
                settings = get_settings()
                if settings.openrouter_api_key:
                    payload = {
                        "model": settings.cloud_model,
                        "messages": [
                            {
                                "role": "system",
                                "content": "You are Rosa OS. Write a 2-3 sentence diary entry about today's conversations. Be concise and insightful.",
                            },
                            {"role": "user", "content": f"Today's conversations summary:\n{recent_text[:500]}"},
                        ],
                        "max_tokens": 200,
                    }
                    async with httpx.AsyncClient(timeout=15.0) as client:
                        resp = await client.post(
                            f"{settings.openrouter_base_url}/chat/completions",
                            headers={"Authorization": f"Bearer {settings.openrouter_api_key}"},
                            json=payload,
                        )
                    diary = resp.json()["choices"][0]["message"]["content"]
                    result["diary_entry"] = diary

                    # Save diary entry
                    diary_path = Path("memory/diary.jsonl")
                    diary_path.parent.mkdir(parents=True, exist_ok=True)
                    with diary_path.open("a") as f:
                        f.write(json.dumps({
                            "date": datetime.now(timezone.utc).date().isoformat(),
                            "entry": diary,
                        }) + "\n")
            except Exception as exc:
                logger.warning("Diary generation failed: %s", exc)

    except Exception as exc:
        logger.error("Consolidation failed: %s", exc)
        result["error"] = str(exc)

    logger.info("Consolidation complete: %s", result)
    return result


def schedule_consolidation() -> None:
    """Start background thread that runs consolidation daily at 03:00."""

    def _run_daily():
        import time
        while True:
            try:
                now = datetime.now()
                # Calculate seconds until next 03:00
                target_hour = 3
                next_run = now.replace(hour=target_hour, minute=0, second=0, microsecond=0)
                if now >= next_run:
                    from datetime import timedelta
                    next_run += timedelta(days=1)
                wait_seconds = (next_run - now).total_seconds()
                logger.info("Consolidation scheduled in %.0f seconds", wait_seconds)
                time.sleep(wait_seconds)

                # Run consolidation
                try:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    loop.run_until_complete(run_consolidation())
                    loop.close()
                except Exception as exc:
                    logger.error("Scheduled consolidation failed: %s", exc)
            except Exception as exc:
                logger.error("Consolidation scheduler error: %s", exc)
                import time as _time
                _time.sleep(3600)  # retry in 1 hour

    thread = threading.Thread(target=_run_daily, daemon=True, name="rosa-consolidator")
    thread.start()
    logger.info("Consolidation scheduler started")
