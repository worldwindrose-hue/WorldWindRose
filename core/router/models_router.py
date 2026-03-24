"""
ROSA OS v4 — Models Router (Model Pantheon).

Reads config/models.yaml, provides routing strategies:
- fast:         one model (default Kimi K2.5)
- quality:      debate between two models, synthesized by Kimi
- privacy:      prefer local/offline model, fallback to Kimi
- ensemble:     parallel calls to 3 models, synthesized
- task_routing: model chosen by task type
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger("rosa.router.models")

_CONFIG_PATH = Path(__file__).parent.parent.parent / "config" / "models.yaml"


class ModelsRouter:
    """
    Routes a task to one or more LLMs based on the selected strategy.
    Reads model metadata from config/models.yaml.
    """

    def __init__(self, config_path: Path | None = None) -> None:
        self._config_path = config_path or _CONFIG_PATH
        self._config: dict = {}
        self._load()

    def _load(self) -> None:
        try:
            with open(self._config_path, "r", encoding="utf-8") as f:
                self._config = yaml.safe_load(f) or {}
        except FileNotFoundError:
            logger.warning("models.yaml not found at %s — using empty config", self._config_path)
            self._config = {"models": {}, "routing_strategies": {}}

    def reload(self) -> None:
        """Hot-reload the config from disk."""
        self._load()

    # ── Model metadata ────────────────────────────────────────────────────────

    def list_models(self) -> list[dict[str, Any]]:
        """Return all model definitions with their metadata."""
        result = []
        for key, m in self._config.get("models", {}).items():
            result.append({
                "id": key,
                "model_id": m.get("model_id", key),
                "display_name": m.get("display_name", key),
                "icon": m.get("icon", "🤖"),
                "provider": m.get("provider", "openrouter"),
                "strengths": m.get("strengths", []),
                "context_window": m.get("context_window", 0),
                "cost_tier": m.get("cost_tier", "medium"),
                "enabled": m.get("enabled", False),
                "notes": m.get("notes", ""),
            })
        return result

    def get_model(self, key: str) -> dict[str, Any] | None:
        models = self._config.get("models", {})
        if key not in models:
            return None
        m = models[key]
        return {
            "id": key,
            "model_id": m.get("model_id", key),
            "display_name": m.get("display_name", key),
            "provider": m.get("provider", "openrouter"),
            "enabled": m.get("enabled", False),
        }

    def set_enabled(self, key: str, enabled: bool) -> bool:
        """Toggle a model on/off and persist to YAML."""
        models = self._config.get("models", {})
        if key not in models:
            return False
        models[key]["enabled"] = enabled
        try:
            with open(self._config_path, "w", encoding="utf-8") as f:
                yaml.dump(self._config, f, allow_unicode=True, default_flow_style=False)
        except OSError as exc:
            logger.error("Could not write models.yaml: %s", exc)
        return True

    def list_strategies(self) -> list[dict[str, Any]]:
        return [
            {"id": k, "description": v.get("description", k)}
            for k, v in self._config.get("routing_strategies", {}).items()
        ]

    # ── Primary model resolution ─────────────────────────────────────────────

    def _resolve_model_id(self, key: str) -> str | None:
        """Resolve a model key to its actual model_id string."""
        models = self._config.get("models", {})
        if key in models:
            return models[key].get("model_id")
        return None

    def _enabled_model_id(self, key: str) -> str | None:
        models = self._config.get("models", {})
        if key in models and models[key].get("enabled", False):
            return models[key].get("model_id")
        return None

    # ── Routing ──────────────────────────────────────────────────────────────

    async def route(
        self,
        task_text: str,
        strategy: str = "fast",
        session_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Route a task to the appropriate model(s) based on strategy.
        Returns: {response, models_used, strategy, debate_log?}
        """
        strategies = self._config.get("routing_strategies", {})
        strat = strategies.get(strategy, strategies.get("fast", {}))

        if strategy == "quality":
            return await self._quality_route(task_text, strat, session_id)
        elif strategy == "privacy":
            return await self._privacy_route(task_text, strat, session_id)
        elif strategy == "ensemble":
            return await self._ensemble_route(task_text, strat, session_id)
        elif strategy == "task_routing":
            return await self._task_routing(task_text, strat, session_id)
        else:
            return await self._fast_route(task_text, strat, session_id)

    async def _call_model(self, model_key: str, messages: list[dict], max_tokens: int = 2048) -> str:
        """Call a model and return its text response."""
        model = self._config.get("models", {}).get(model_key, {})
        provider = model.get("provider", "openrouter")
        model_id = model.get("model_id", model_key)

        if provider == "ollama":
            return await self._call_ollama(model_id, messages)
        else:
            return await self._call_openrouter(model_id, messages, max_tokens)

    async def _call_openrouter(self, model_id: str, messages: list[dict], max_tokens: int = 2048) -> str:
        import httpx
        from core.config import get_settings
        settings = get_settings()
        if not settings.openrouter_api_key:
            return "[Ошибка: OPENROUTER_API_KEY не задан]"

        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{settings.openrouter_base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.openrouter_api_key}",
                    "Content-Type": "application/json",
                },
                json={"model": model_id, "messages": messages, "max_tokens": max_tokens},
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]

    async def _call_ollama(self, model_id: str, messages: list[dict]) -> str:
        import httpx
        from core.config import get_settings
        settings = get_settings()
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(
                    f"{settings.ollama_base_url}/api/chat",
                    json={"model": model_id, "messages": messages, "stream": False},
                )
                resp.raise_for_status()
                return resp.json()["message"]["content"]
        except Exception as exc:
            logger.warning("Ollama call failed (%s) — falling back to Kimi", exc)
            return await self._call_openrouter(
                self._resolve_model_id("kimi_k2_5") or "moonshotai/kimi-k2.5",
                messages,
            )

    async def _fast_route(self, task: str, strat: dict, session_id: str | None) -> dict:
        primary_key = strat.get("primary", "kimi_k2_5")
        msgs = [{"role": "user", "content": task}]
        try:
            response = await self._call_model(primary_key, msgs)
        except Exception as exc:
            response = f"[Ошибка модели {primary_key}: {exc}]"
        return {
            "response": response,
            "models_used": [primary_key],
            "strategy": "fast",
        }

    async def _quality_route(self, task: str, strat: dict, session_id: str | None) -> dict:
        """Debate: primary and secondary each answer, then synthesizer merges."""
        primary_key = strat.get("primary", "kimi_k2_5")
        secondary_key = strat.get("secondary", "claude_sonnet")
        synth_key = strat.get("synthesizer", primary_key)

        msgs = [{"role": "user", "content": task}]
        debate_log = []

        try:
            resp_a = await self._call_model(primary_key, msgs)
        except Exception as exc:
            resp_a = f"[Ошибка {primary_key}: {exc}]"
        debate_log.append({"model": primary_key, "response": resp_a})

        try:
            resp_b = await self._call_model(secondary_key, msgs)
        except Exception as exc:
            resp_b = f"[Ошибка {secondary_key}: {exc}]"
        debate_log.append({"model": secondary_key, "response": resp_b})

        # Synthesis
        synth_prompt = (
            f"Вот два ответа на задачу:\n\n"
            f"**{primary_key}:** {resp_a}\n\n"
            f"**{secondary_key}:** {resp_b}\n\n"
            "Синтезируй лучший ответ, объединив сильные стороны обоих. "
            "Будь лаконичен и точен."
        )
        try:
            final = await self._call_model(synth_key, [{"role": "user", "content": synth_prompt}])
        except Exception as exc:
            final = resp_a  # fallback to primary
        debate_log.append({"model": synth_key + " (synthesis)", "response": final})

        return {
            "response": final,
            "models_used": [primary_key, secondary_key],
            "strategy": "quality",
            "debate_log": debate_log,
        }

    async def _privacy_route(self, task: str, strat: dict, session_id: str | None) -> dict:
        primary_key = strat.get("primary", "llama3_local")
        fallback_key = strat.get("fallback", "kimi_k2_5")
        msgs = [{"role": "user", "content": task}]
        try:
            response = await self._call_model(primary_key, msgs)
            used = primary_key
        except Exception:
            try:
                response = await self._call_model(fallback_key, msgs)
                used = fallback_key
            except Exception as exc:
                response = f"[Ошибка: {exc}]"
                used = fallback_key
        return {
            "response": response,
            "models_used": [used],
            "strategy": "privacy",
        }

    async def _ensemble_route(self, task: str, strat: dict, session_id: str | None) -> dict:
        """
        Parallel calls to multiple models, then synthesis.
        All enabled models in strat['models'] are called concurrently.
        """
        import asyncio
        model_keys = strat.get("models", ["kimi_k2_5", "claude_sonnet"])
        synth_key = strat.get("synthesizer", "kimi_k2_5")
        msgs = [{"role": "user", "content": task}]

        # Call all models in parallel
        async def call_one(key: str) -> tuple[str, str]:
            try:
                r = await self._call_model(key, msgs)
                return key, r
            except Exception as exc:
                return key, f"[Ошибка {key}: {exc}]"

        results = await asyncio.gather(*[call_one(k) for k in model_keys])
        responses_dict = dict(results)

        # Build synthesis prompt
        parts = "\n\n".join(
            f"**{key}:** {resp}" for key, resp in responses_dict.items()
        )
        synth_prompt = (
            f"Вот ответы от {len(responses_dict)} моделей на один вопрос:\n\n"
            f"{parts}\n\n"
            "Синтезируй лучший финальный ответ: возьми наиболее точные части каждого, "
            "устрани противоречия, будь лаконичен."
        )
        try:
            final = await self._call_model(synth_key, [{"role": "user", "content": synth_prompt}])
        except Exception:
            # Fallback: return best single response
            final = next(iter(responses_dict.values()))

        return {
            "response": final,
            "models_used": list(model_keys),
            "strategy": "ensemble",
            "ensemble_responses": responses_dict,
        }

    async def _task_routing(self, task: str, strat: dict, session_id: str | None) -> dict:
        """
        Route by task type using rules from config.
        Falls back to default model if no match.
        """
        from core.router import get_router
        # Classify task type
        try:
            rosa = get_router()
            task_type = rosa._router.classify_task(task).task_type.value
        except Exception:
            task_type = "SIMPLE_CHAT"

        rules = strat.get("rules", [])
        model_key = "kimi_k2_5"
        fallback_key = "kimi_k2_5"

        for rule in rules:
            rt = rule.get("task_type", "")
            if rt == "default":
                fallback_key = rule.get("model", "kimi_k2_5")
            elif rt == task_type:
                model_key = rule.get("model", "kimi_k2_5")
                fallback_key = rule.get("fallback", model_key)
                break

        msgs = [{"role": "user", "content": task}]
        try:
            response = await self._call_model(model_key, msgs)
            used = model_key
        except Exception:
            try:
                response = await self._call_model(fallback_key, msgs)
                used = fallback_key
            except Exception as exc:
                response = f"[Ошибка: {exc}]"
                used = fallback_key

        return {
            "response": response,
            "models_used": [used],
            "strategy": "task_routing",
            "task_type_detected": task_type,
        }

    def get_model_for_task(self, task_type: str) -> str:
        """Return the best enabled model_id for a given task type."""
        models = self._config.get("models", {})
        for key, m in models.items():
            if not m.get("enabled", False):
                continue
            affinities = m.get("task_affinity", [])
            if task_type in affinities:
                return m.get("model_id", key)
        # Default to Kimi K2.5
        kimi = models.get("kimi_k2_5", {})
        return kimi.get("model_id", "moonshotai/kimi-k2.5")


# Singleton
_router_instance: ModelsRouter | None = None


def get_models_router() -> ModelsRouter:
    global _router_instance
    if _router_instance is None:
        _router_instance = ModelsRouter()
    return _router_instance
