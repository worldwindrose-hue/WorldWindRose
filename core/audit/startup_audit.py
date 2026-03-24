"""ROSA OS — Startup Audit. Checks system health at boot, saves report."""

from __future__ import annotations
import json, logging, shutil, time
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger("rosa.audit.startup")
_AUDIT_LOG = Path("memory/audit_log.json")


@dataclass
class AuditCheck:
    name: str
    status: str  # pass / warn / fail
    message: str
    duration_ms: float = 0.0


@dataclass
class AuditReport:
    timestamp: str
    checks: list[AuditCheck]
    score: float
    passed: int
    warned: int
    failed: int

    def to_dict(self) -> dict:
        d = asdict(self)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "AuditReport":
        checks = [AuditCheck(**c) for c in d.pop("checks", [])]
        return cls(checks=checks, **d)


async def run_startup_audit() -> AuditReport:
    checks: list[AuditCheck] = []

    async def check(name: str, fn):
        t0 = time.monotonic()
        try:
            msg, status = await fn() if hasattr(fn, "__await__") else (lambda: fn())()
            if callable(fn):
                import asyncio
                if asyncio.iscoroutinefunction(fn):
                    msg, status = await fn()
                else:
                    msg, status = fn()
        except Exception as exc:
            msg, status = str(exc)[:100], "fail"
        dur = (time.monotonic() - t0) * 1000
        checks.append(AuditCheck(name=name, status=status, message=msg, duration_ms=round(dur, 1)))

    # 1. API key
    def _check_api_key():
        try:
            from core.config import get_settings
            s = get_settings()
            if s.openrouter_api_key:
                return "OpenRouter key present", "pass"
            return "OpenRouter key missing — set OPENROUTER_API_KEY", "warn"
        except Exception as e:
            return str(e), "fail"
    await check("API Key", _check_api_key)

    # 2. Memory dir
    def _check_memory_dir():
        p = Path("memory")
        p.mkdir(exist_ok=True)
        test = p / ".write_test"
        try:
            test.write_text("ok")
            test.unlink()
            return "memory/ writable", "pass"
        except Exception as e:
            return f"memory/ not writable: {e}", "fail"
    await check("Memory Dir", _check_memory_dir)

    # 3. Disk space
    def _check_disk():
        usage = shutil.disk_usage(".")
        free_gb = usage.free / 1e9
        if free_gb > 2:
            return f"Disk free: {free_gb:.1f} GB", "pass"
        elif free_gb > 0.5:
            return f"Disk low: {free_gb:.1f} GB", "warn"
        return f"Disk critical: {free_gb:.1f} GB", "fail"
    await check("Disk Space", _check_disk)

    # 4. SQLite DB
    async def _check_db():
        try:
            from core.memory.store import get_store
            store = await get_store()
            return "SQLite DB accessible", "pass"
        except Exception as e:
            return f"DB error: {e}", "fail"
    await check("SQLite DB", _check_db)

    # 5. Config
    def _check_config():
        try:
            from core.config import get_settings
            s = get_settings()
            return f"Config OK (v{s.app_version})", "pass"
        except Exception as e:
            return f"Config error: {e}", "fail"
    await check("Config", _check_config)

    # 6. ChromaDB (optional)
    def _check_chromadb():
        try:
            import chromadb
            return "ChromaDB available", "pass"
        except ImportError:
            return "ChromaDB not installed (using SQLite fallback)", "warn"
    await check("ChromaDB", _check_chromadb)

    # Score
    passed = sum(1 for c in checks if c.status == "pass")
    warned = sum(1 for c in checks if c.status == "warn")
    failed = sum(1 for c in checks if c.status == "fail")
    total = len(checks)
    score = round((passed * 1.0 + warned * 0.5) / max(total, 1) * 100, 1)

    report = AuditReport(
        timestamp=datetime.now(timezone.utc).isoformat(),
        checks=checks, score=score,
        passed=passed, warned=warned, failed=failed,
    )

    # Save
    try:
        _AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
        _AUDIT_LOG.write_text(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
    except Exception:
        pass

    logger.info("Startup audit: score=%.0f%% (%d/%d passed)", score, passed, total)
    if failed > 0:
        logger.warning("Audit FAILED checks: %s", [c.name for c in checks if c.status == "fail"])

    return report


def get_last_audit() -> Optional[AuditReport]:
    if not _AUDIT_LOG.exists():
        return None
    try:
        return AuditReport.from_dict(json.loads(_AUDIT_LOG.read_text()))
    except Exception:
        return None
