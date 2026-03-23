"""
ROSA OS — Policy enforcement.
Loads policies from config/policies.yaml and checks operations against them.
"""

from __future__ import annotations

import yaml
from pathlib import Path
from dataclasses import dataclass


@dataclass
class PolicyResult:
    allowed: bool
    requires_confirmation: bool
    reason: str


class PolicyEngine:
    """Enforces ROSA OS safety policies from config/policies.yaml."""

    def __init__(self, policy_path: str = "config/policies.yaml"):
        self._path = Path(policy_path)
        self._policies: dict = {}
        self._load()

    def _load(self) -> None:
        if self._path.exists():
            with open(self._path) as f:
                self._policies = yaml.safe_load(f) or {}

    def check_command(self, command: str) -> PolicyResult:
        """Check if a shell command is allowed."""
        forbidden = self._policies.get("forbidden", {}).get("commands", [])
        for pattern in forbidden:
            if pattern in command:
                return PolicyResult(
                    allowed=False,
                    requires_confirmation=False,
                    reason=f"Command matches forbidden pattern: '{pattern}'",
                )

        # Check red zones
        red_zone_ops = ["sudo", "rm -rf", "chmod", "chown", "mkfs", "dd ", "systemctl"]
        for op in red_zone_ops:
            if op in command:
                return PolicyResult(
                    allowed=True,
                    requires_confirmation=True,
                    reason=f"Command contains red-zone operation: '{op}'",
                )

        return PolicyResult(allowed=True, requires_confirmation=False, reason="OK")

    def check_file_operation(self, operation: str, path: str) -> PolicyResult:
        """Check if a file operation is allowed."""
        dangerous_ops = self._policies.get("red_zones", {}).get("file_operations", [])
        if operation.lower() in dangerous_ops:
            return PolicyResult(
                allowed=True,
                requires_confirmation=True,
                reason=f"File operation '{operation}' on '{path}' requires confirmation",
            )
        return PolicyResult(allowed=True, requires_confirmation=False, reason="OK")

    def check_operation_type(self, operation_type: str) -> PolicyResult:
        """Check an abstract operation type (e.g. 'mass_email', 'payment')."""
        forbidden_ops = self._policies.get("forbidden", {}).get("operations", [])
        if operation_type in forbidden_ops:
            return PolicyResult(
                allowed=False,
                requires_confirmation=False,
                reason=f"Operation '{operation_type}' is forbidden by policy",
            )

        # Flatten all red-zone lists
        red_zones_all: list[str] = []
        for zone_list in self._policies.get("red_zones", {}).values():
            red_zones_all.extend(zone_list)

        if operation_type in red_zones_all:
            return PolicyResult(
                allowed=True,
                requires_confirmation=True,
                reason=f"Operation '{operation_type}' is in a red zone",
            )

        return PolicyResult(allowed=True, requires_confirmation=False, reason="OK")
