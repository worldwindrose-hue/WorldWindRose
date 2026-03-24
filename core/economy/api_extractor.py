"""
ROSA OS — API Key Scanner (Phase 9).

Safely scans local .env files and suggests free alternatives.
NEVER auto-extracts — only reports what exists locally.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger("rosa.economy.api_extractor")

_FREE_ALTERNATIVES: dict[str, list[str]] = {
    "openai": ["google/gemini-flash-1.5 (free tier)", "ollama/llama3.2 (local, free)"],
    "anthropic": ["moonshotai/kimi-k2.5 (cheaper)", "google/gemini-flash-1.5"],
    "perplexity": ["DuckDuckGo search (free)", "Wikipedia API (free)"],
    "cohere": ["moonshotai/kimi-k2.5"],
}


def scan_env_files() -> dict[str, Any]:
    """
    Scan local .env files and report which API keys are configured.
    Returns key names only — never the actual values.
    IMPORTANT: This only reads .env in the project directory.
    """
    project_root = Path(__file__).parent.parent.parent
    env_file = project_root / ".env"

    configured = []
    missing = []

    standard_keys = [
        "OPENROUTER_API_KEY",
        "GITHUB_TOKEN",
        "TELEGRAM_BOT_TOKEN",
        "TELEGRAM_API_ID",
        "TELEGRAM_API_HASH",
        "NGROK_TOKEN",
    ]

    for key in standard_keys:
        if os.environ.get(key) or (env_file.exists() and key in env_file.read_text()):
            configured.append(key)
        else:
            missing.append(key)

    return {
        "configured": configured,
        "missing": missing,
        "env_file_exists": env_file.exists(),
    }


def suggest_free_alternatives(model: str) -> list[str]:
    """Suggest free alternatives for a given model provider."""
    model_lower = model.lower()
    for provider, alternatives in _FREE_ALTERNATIVES.items():
        if provider in model_lower:
            return alternatives
    return ["moonshotai/kimi-k2.5 (cost-effective)", "google/gemini-flash-1.5 (cheapest)"]


def estimate_monthly_cost(daily_messages: int = 100, avg_tokens: int = 500) -> dict[str, float]:
    """Estimate monthly API cost based on usage patterns."""
    monthly_messages = daily_messages * 30
    monthly_tokens = monthly_messages * avg_tokens

    estimates: dict[str, float] = {}
    from core.economy.token_optimizer import _MODEL_COSTS
    for model, costs in _MODEL_COSTS.items():
        monthly_cost = (monthly_tokens / 1_000_000) * (costs["input"] + costs["output"]) / 2
        estimates[model] = round(monthly_cost, 2)

    return estimates
