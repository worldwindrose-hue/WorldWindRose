"""
ROSA OS — Agent Factory.

Creates and manages specialized agents on demand.
Each agent is a context-aware wrapper around a model call with a specific role.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

logger = logging.getLogger("rosa.agents.factory")

# Registry of available agent types
_AGENT_REGISTRY: dict[str, dict[str, Any]] = {
    "researcher": {
        "description": "Research agent — searches web and knowledge graph",
        "module": "core.agents.researcher",
        "entrypoint": "research",
    },
    "content": {
        "description": "Content pipeline agent — creates blog posts, social posts, etc.",
        "module": "core.agents.content_pipeline",
        "entrypoint": "create_content",
    },
    "swarm": {
        "description": "Swarm coordinator — runs multiple agents in parallel",
        "module": "core.agents.swarm",
        "entrypoint": "run_swarm",
    },
    "pal": {
        "description": "PAL agent — solves math/logic problems with code",
        "module": "core.reasoning.pal",
        "entrypoint": "solve",
    },
}


class AgentInstance:
    """Wrapper around a callable agent with metadata."""

    def __init__(self, agent_type: str, config: dict[str, Any]) -> None:
        self.agent_type = agent_type
        self.config = config
        self._fn: Callable | None = None

    async def _load(self) -> None:
        """Lazy-load the agent entrypoint."""
        if self._fn is not None:
            return
        import importlib
        module = importlib.import_module(self.config["module"])
        self._fn = getattr(module, self.config["entrypoint"])

    async def run(self, *args: Any, **kwargs: Any) -> Any:
        """Run the agent with given arguments."""
        await self._load()
        assert self._fn is not None
        return await self._fn(*args, **kwargs)

    def __repr__(self) -> str:
        return f"AgentInstance(type={self.agent_type})"


class AgentFactory:
    """Creates and tracks agent instances."""

    def __init__(self) -> None:
        self._instances: dict[str, AgentInstance] = {}

    def create(self, agent_type: str) -> AgentInstance:
        """Create a new agent instance (not cached)."""
        config = _AGENT_REGISTRY.get(agent_type)
        if not config:
            raise ValueError(f"Unknown agent type: {agent_type}. Available: {list(_AGENT_REGISTRY)}")
        return AgentInstance(agent_type, config)

    def get_or_create(self, agent_type: str) -> AgentInstance:
        """Get existing instance or create new one (singleton per type)."""
        if agent_type not in self._instances:
            self._instances[agent_type] = self.create(agent_type)
        return self._instances[agent_type]

    def list_agents(self) -> list[dict[str, Any]]:
        """List all registered agent types."""
        return [
            {
                "type": k,
                "description": v["description"],
                "module": v["module"],
            }
            for k, v in _AGENT_REGISTRY.items()
        ]

    def register(
        self,
        agent_type: str,
        description: str,
        module: str,
        entrypoint: str,
    ) -> None:
        """Register a new agent type at runtime."""
        _AGENT_REGISTRY[agent_type] = {
            "description": description,
            "module": module,
            "entrypoint": entrypoint,
        }
        logger.info("Registered agent type: %s", agent_type)


# Singleton
_factory: AgentFactory | None = None


def get_factory() -> AgentFactory:
    global _factory
    if _factory is None:
        _factory = AgentFactory()
    return _factory
