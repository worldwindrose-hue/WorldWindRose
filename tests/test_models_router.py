"""
Tests for ROSA OS v3 — ModelsRouter (Pantheon).
"""

import sys
import pytest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture
def router():
    """Create a ModelsRouter with the real config/models.yaml."""
    from core.router.models_router import ModelsRouter
    return ModelsRouter()


def test_list_models_not_empty(router):
    models = router.list_models()
    assert len(models) > 0


def test_list_models_structure(router):
    models = router.list_models()
    for m in models:
        assert "id" in m
        assert "model_id" in m
        assert "display_name" in m
        assert "enabled" in m
        assert "strengths" in m
        assert isinstance(m["strengths"], list)


def test_kimi_enabled_by_default(router):
    models = {m["id"]: m for m in router.list_models()}
    assert "kimi_k2_5" in models
    assert models["kimi_k2_5"]["enabled"] is True


def test_get_model_exists(router):
    m = router.get_model("kimi_k2_5")
    assert m is not None
    assert m["id"] == "kimi_k2_5"


def test_get_model_not_found(router):
    m = router.get_model("nonexistent_model_xyz")
    assert m is None


def test_list_strategies(router):
    strategies = router.list_strategies()
    ids = [s["id"] for s in strategies]
    assert "fast" in ids
    assert "quality" in ids
    assert "privacy" in ids


def test_local_model_configured(router):
    """llama3_local should be present in config."""
    models = {m["id"]: m for m in router.list_models()}
    assert "llama3_local" in models
    assert models["llama3_local"]["provider"] == "ollama"


@pytest.mark.asyncio
async def test_fast_route_returns_response(router):
    """Fast route should call a model and return a response dict."""
    mock_response = "Тестовый ответ от Kimi"

    with patch.object(router, "_call_openrouter", return_value=mock_response):
        result = await router.route("Привет, как дела?", strategy="fast")

    assert "response" in result
    assert result["response"] == mock_response
    assert result["strategy"] == "fast"
    assert len(result["models_used"]) == 1


@pytest.mark.asyncio
async def test_quality_route_uses_two_models(router):
    """Quality route should call primary, secondary, then synthesizer."""
    call_count = {"n": 0}

    async def mock_call(model_key, messages, max_tokens=2048):
        call_count["n"] += 1
        return f"Ответ от модели {model_key} (вызов #{call_count['n']})"

    with patch.object(router, "_call_model", side_effect=mock_call):
        result = await router.route("Сложный вопрос", strategy="quality")

    assert result["strategy"] == "quality"
    assert len(result["models_used"]) == 2
    assert "debate_log" in result
    # 3 calls: primary + secondary + synthesizer
    assert call_count["n"] == 3


@pytest.mark.asyncio
async def test_privacy_route_uses_local(router):
    """Privacy route should prefer local model."""
    mock_response = "Локальный ответ"

    with patch.object(router, "_call_ollama", return_value=mock_response):
        result = await router.route("Личный вопрос", strategy="privacy")

    assert result["strategy"] == "privacy"
    assert mock_response == result["response"]
