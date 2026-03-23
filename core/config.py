"""
ROSA OS — Centralized configuration via pydantic-settings.
All settings can be overridden with environment variables.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # API keys
    openrouter_api_key: str = ""

    # Models
    cloud_model: str = "moonshotai/kimi-k2.5"
    cloud_fallback_model: str = "anthropic/claude-3.5-sonnet"
    local_model: str = "llama3.2"

    # Endpoints
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    ollama_base_url: str = "http://localhost:11434"

    # Server
    host: str = "127.0.0.1"
    port: int = 8000

    # Memory
    db_path: str = "memory/rosa.db"

    # Security
    require_confirmation: bool = True
    allow_file_operations: bool = False

    # Self-improvement
    self_improvement_enabled: bool = True
    self_improvement_lookback: int = 50
    self_improvement_min_failures: int = 3

    # App
    app_version: str = "1.0.0"
    debug: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
