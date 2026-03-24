"""
ROSA OS — Security Firewall.
Pattern-matching firewall for all subprocess/LLM-triggered actions.
Blocks dangerous commands and logs attempts.

Usage:
    from core.security.firewall import check_command, FirewallBlock

    try:
        check_command(cmd)
    except FirewallBlock as e:
        logger.warning("Blocked: %s", e)
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

logger = logging.getLogger("rosa.security.firewall")

# ── Dangerous patterns ────────────────────────────────────────────────────────

_DANGEROUS_PATTERNS: list[tuple[str, str]] = [
    # Filesystem destruction
    (r"\brm\s+-rf?\b", "rm -rf"),
    (r"\brmdir\b", "rmdir"),
    (r"\bformat\b", "format"),
    (r"\bdd\s+if=", "dd disk wipe"),
    # Permission escalation
    (r"\bsudo\b", "sudo"),
    (r"\bchmod\s+[0-7]*7[0-7]*\b", "chmod 7xx"),
    (r"\bchown\b", "chown"),
    # Network exfiltration
    (r"\bcurl\s+.*-X\s+DELETE", "curl DELETE"),
    (r"\bwget\s+.*--post", "wget POST"),
    # Database destruction
    (r"\bDROP\s+TABLE\b", "DROP TABLE"),
    (r"\bDROP\s+DATABASE\b", "DROP DATABASE"),
    (r"\bTRUNCATE\s+TABLE\b", "TRUNCATE TABLE"),
    # Social/financial actions
    (r"\bsend_message\b", "send_message"),
    (r"\bpost_tweet\b", "post_tweet"),
    (r"\btransfer\b.*\bfunds?\b", "transfer funds"),
    (r"\bsend_email\b", "send_email"),
    # Code injection
    (r"\beval\s*\(", "eval()"),
    (r"\bexec\s*\(", "exec()"),
    (r"\b__import__\s*\(", "__import__"),
    (r"\bos\.system\b", "os.system"),
    (r"\bsubprocess\.call\b", "subprocess.call (use run)"),
    # Environment tampering
    (r"\bos\.environ\s*\[", "os.environ write"),
    (r"\bunsetenv\b", "unsetenv"),
]

# Compiled for speed
_COMPILED = [(re.compile(p, re.IGNORECASE), name) for p, name in _DANGEROUS_PATTERNS]

# Whitelist patterns (always allowed)
_WHITELIST: list[re.Pattern] = [
    re.compile(r"^python3?\s+-m\s+pytest\b"),
    re.compile(r"^git\s+(status|log|diff|show)\b"),
]


class FirewallBlock(Exception):
    """Raised when a command or text is blocked by the firewall."""

    def __init__(self, reason: str, matched_rule: str):
        super().__init__(f"BLOCKED [{matched_rule}]: {reason[:200]}")
        self.reason = reason
        self.matched_rule = matched_rule


def check_command(cmd: str) -> None:
    """
    Raise FirewallBlock if cmd matches any dangerous pattern.
    Call this before any subprocess.run() or shell execution.
    """
    # Check whitelist first
    for wl in _WHITELIST:
        if wl.match(cmd.strip()):
            return

    for pattern, rule_name in _COMPILED:
        if pattern.search(cmd):
            _log_block(cmd, rule_name)
            raise FirewallBlock(cmd, rule_name)


def check_text(text: str) -> None:
    """
    Check LLM-generated text for dangerous patterns before execution.
    Less strict than check_command — only blocks the most critical patterns.
    """
    critical = [
        (re.compile(r"\brm\s+-rf\b", re.IGNORECASE), "rm -rf"),
        (re.compile(r"\bDROP\s+DATABASE\b", re.IGNORECASE), "DROP DATABASE"),
        (re.compile(r"\bsudo\b", re.IGNORECASE), "sudo"),
    ]
    for pattern, rule_name in critical:
        if pattern.search(text):
            _log_block(text[:100], rule_name)
            raise FirewallBlock(text[:100], rule_name)


def is_safe_command(cmd: str) -> bool:
    """Return True if command passes firewall checks."""
    try:
        check_command(cmd)
        return True
    except FirewallBlock:
        return False


def _log_block(cmd: str, rule: str) -> None:
    """Append blocked attempt to firewall.log."""
    from datetime import datetime, timezone

    log_path = Path("memory/firewall.log")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).isoformat()
    entry = f"[{ts}] BLOCKED [{rule}]: {cmd[:200]}\n"
    try:
        with open(log_path, "a") as f:
            f.write(entry)
    except OSError:
        pass
    logger.warning("Firewall blocked [%s]: %s", rule, cmd[:100])


def emergency_halt(reason: str) -> None:
    """
    Called when a critical security threat is detected.
    Logs the threat. Does NOT kill the process — owner must decide.
    """
    _log_block(f"EMERGENCY HALT: {reason}", "critical")
    logger.critical("EMERGENCY HALT triggered: %s", reason)
    # Fire an event to the memory store (best-effort)
    try:
        import asyncio
        async def _store_event():
            from core.memory.store import get_store
            store = await get_store()
            await store.save_event(
                event_type="emergency_halt",
                description=f"Emergency halt: {reason}",
                severity="critical",
            )
        asyncio.create_task(_store_event())
    except Exception:
        pass
