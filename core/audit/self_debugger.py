"""
ROSA OS — Self Debugger.

Monitors logs for error patterns and suggests (or applies simple) auto-fixes.
All fixes go to memory/debug_patches/ — never auto-applied to core code.
"""

from __future__ import annotations

import json
import logging
import re
import time
from collections import defaultdict
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger("rosa.audit.debugger")

_ERROR_LOG = Path("memory/error_patterns.json")
_PATCHES_DIR = Path("memory/debug_patches")

# Known recoverable patterns and their suggested fixes
_KNOWN_PATTERNS: list[dict] = [
    {
        "pattern": r"ModuleNotFoundError: No module named '(\w+)'",
        "category": "missing_dependency",
        "fix_template": "pip install {match_1}",
        "severity": "warn",
    },
    {
        "pattern": r"sqlite3\.OperationalError: no such table: (\w+)",
        "category": "db_schema",
        "fix_template": "Run DB migration for table {match_1}",
        "severity": "error",
    },
    {
        "pattern": r"ConnectionRefusedError|aiohttp\.ClientConnectorError",
        "category": "network",
        "fix_template": "Check external service availability",
        "severity": "warn",
    },
    {
        "pattern": r"TimeoutError|asyncio\.TimeoutError",
        "category": "timeout",
        "fix_template": "Increase timeout or retry with backoff",
        "severity": "warn",
    },
    {
        "pattern": r"PermissionError: \[Errno 13\]",
        "category": "permissions",
        "fix_template": "Check file/directory permissions",
        "severity": "error",
    },
    {
        "pattern": r"KeyError: '(\w+)'",
        "category": "missing_key",
        "fix_template": "Add .get('{match_1}') with default value",
        "severity": "warn",
    },
    {
        "pattern": r"json\.JSONDecodeError",
        "category": "json_parse",
        "fix_template": "Validate JSON input before parsing",
        "severity": "warn",
    },
]


@dataclass
class ErrorOccurrence:
    pattern: str
    category: str
    count: int
    first_seen: str
    last_seen: str
    fix_suggestion: str
    severity: str
    example: str = ""


@dataclass
class DebugReport:
    timestamp: str
    total_errors: int
    patterns_found: int
    occurrences: list[ErrorOccurrence]
    top_category: Optional[str]
    action_items: list[str]


class SelfDebugger:
    """Scans log files for error patterns and generates debug reports."""

    def __init__(self):
        self._log_dirs = [Path("memory/logs"), Path("memory")]
        self._error_counts: dict[str, ErrorOccurrence] = {}

    def scan_log_text(self, text: str) -> dict[str, ErrorOccurrence]:
        """Scan a block of log text for known error patterns."""
        found: dict[str, ErrorOccurrence] = {}
        lines = text.splitlines()

        for line in lines:
            for pattern_def in _KNOWN_PATTERNS:
                m = re.search(pattern_def["pattern"], line)
                if m:
                    cat = pattern_def["category"]
                    fix = pattern_def["fix_template"]
                    # Replace match groups in fix template
                    for i, g in enumerate(m.groups(), 1):
                        fix = fix.replace(f"{{match_{i}}}", g or "")

                    now = datetime.now(timezone.utc).isoformat()
                    if cat not in found:
                        found[cat] = ErrorOccurrence(
                            pattern=pattern_def["pattern"],
                            category=cat,
                            count=1,
                            first_seen=now,
                            last_seen=now,
                            fix_suggestion=fix,
                            severity=pattern_def["severity"],
                            example=line[:200],
                        )
                    else:
                        found[cat].count += 1
                        found[cat].last_seen = now

        return found

    def scan_log_files(self) -> dict[str, ErrorOccurrence]:
        """Scan all log files in known directories."""
        all_found: dict[str, ErrorOccurrence] = {}

        for log_dir in self._log_dirs:
            if not log_dir.exists():
                continue
            for log_file in log_dir.glob("*.log"):
                try:
                    text = log_file.read_text(errors="replace")
                    found = self.scan_log_text(text)
                    for cat, occ in found.items():
                        if cat not in all_found:
                            all_found[cat] = occ
                        else:
                            all_found[cat].count += occ.count
                            all_found[cat].last_seen = occ.last_seen
                except Exception as exc:
                    logger.debug("Could not scan %s: %s", log_file, exc)

        return all_found

    def generate_report(self, occurrences: dict[str, ErrorOccurrence]) -> DebugReport:
        """Generate a structured debug report from occurrences."""
        total = sum(o.count for o in occurrences.values())
        top_cat = None
        if occurrences:
            top_cat = max(occurrences.values(), key=lambda o: o.count).category

        # Build action items
        actions: list[str] = []
        for occ in sorted(occurrences.values(), key=lambda o: o.count, reverse=True)[:5]:
            actions.append(f"[{occ.severity.upper()}] {occ.category}: {occ.fix_suggestion} (×{occ.count})")

        report = DebugReport(
            timestamp=datetime.now(timezone.utc).isoformat(),
            total_errors=total,
            patterns_found=len(occurrences),
            occurrences=list(occurrences.values()),
            top_category=top_cat,
            action_items=actions,
        )
        return report

    def run(self) -> DebugReport:
        """Full debug scan cycle."""
        t0 = time.monotonic()
        occurrences = self.scan_log_files()
        report = self.generate_report(occurrences)

        # Save
        try:
            _ERROR_LOG.parent.mkdir(parents=True, exist_ok=True)
            _ERROR_LOG.write_text(
                json.dumps(
                    {"report": asdict(report)},
                    indent=2,
                    ensure_ascii=False,
                    default=str,
                )
            )
        except Exception:
            pass

        elapsed = (time.monotonic() - t0) * 1000
        logger.info(
            "SelfDebugger: %d error patterns in %.0f ms, top=%s",
            report.patterns_found,
            elapsed,
            report.top_category,
        )
        return report

    def save_patch_suggestion(self, category: str, suggestion: str) -> Path:
        """Save a fix suggestion to memory/debug_patches/ (never auto-applied)."""
        _PATCHES_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        path = _PATCHES_DIR / f"{ts}_{category}.txt"
        path.write_text(f"Category: {category}\nSuggestion: {suggestion}\n")
        return path


_debugger: Optional[SelfDebugger] = None


def get_self_debugger() -> SelfDebugger:
    global _debugger
    if _debugger is None:
        _debugger = SelfDebugger()
    return _debugger
