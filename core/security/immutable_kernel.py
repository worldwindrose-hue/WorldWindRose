"""
ROSA OS — Immutable Kernel Guard.

Computes and stores SHA-256 hashes of core files.
On each startup, verifies hashes match. Any tampering is logged and reported.
The kernel itself NEVER blocks execution — it only reports.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger("rosa.security.kernel")

_KERNEL_MANIFEST = Path("memory/kernel_manifest.json")

# Core files that form the immutable kernel
_KERNEL_FILES: list[str] = [
    "core/config.py",
    "core/memory/models.py",
    "core/memory/store.py",
    "core/api/chat.py",
    "docs/CONSTITUTION.md",
    "config/policies.yaml",
]


@dataclass
class KernelFile:
    path: str
    sha256: str
    size_bytes: int
    recorded_at: str
    status: str = "ok"  # ok / modified / missing / new


@dataclass
class KernelReport:
    timestamp: str
    total_files: int
    ok: int
    modified: int
    missing: int
    new_files: int
    integrity: bool  # True = no unauthorized changes
    violations: list[str]

    def to_dict(self) -> dict:
        return asdict(self)


class ImmutableKernel:
    """
    Hash-based integrity monitor for ROSA OS core files.

    Usage:
        kernel = ImmutableKernel()
        kernel.seal()     # Record current hashes (run once after setup)
        report = kernel.verify()  # Check on each startup
    """

    def __init__(self, files: list[str] | None = None):
        self._files = files or _KERNEL_FILES
        self._manifest: dict[str, KernelFile] = {}
        self._load()

    def _load(self) -> None:
        if not _KERNEL_MANIFEST.exists():
            return
        try:
            data = json.loads(_KERNEL_MANIFEST.read_text())
            for item in data.get("files", []):
                kf = KernelFile(**{k: v for k, v in item.items()
                                   if k in KernelFile.__dataclass_fields__})
                self._manifest[kf.path] = kf
        except Exception as exc:
            logger.debug("Kernel manifest load error: %s", exc)

    def _save(self) -> None:
        try:
            _KERNEL_MANIFEST.parent.mkdir(parents=True, exist_ok=True)
            _KERNEL_MANIFEST.write_text(
                json.dumps(
                    {"files": [asdict(f) for f in self._manifest.values()],
                     "sealed_at": datetime.now(timezone.utc).isoformat()},
                    indent=2, ensure_ascii=False,
                )
            )
        except Exception as exc:
            logger.warning("Kernel manifest save error: %s", exc)

    @staticmethod
    def _hash_file(path: Path) -> tuple[str, int]:
        """Return (sha256_hex, size_bytes) for a file."""
        try:
            data = path.read_bytes()
            return hashlib.sha256(data).hexdigest(), len(data)
        except Exception:
            return "", 0

    def seal(self) -> int:
        """Record current hashes of all kernel files. Returns count sealed."""
        count = 0
        now = datetime.now(timezone.utc).isoformat()
        for rel_path in self._files:
            p = Path(rel_path)
            if p.exists():
                h, size = self._hash_file(p)
                if h:
                    self._manifest[rel_path] = KernelFile(
                        path=rel_path,
                        sha256=h,
                        size_bytes=size,
                        recorded_at=now,
                    )
                    count += 1
        self._save()
        logger.info("Kernel sealed: %d files", count)
        return count

    def verify(self) -> KernelReport:
        """Verify all kernel files against stored hashes."""
        ok = 0
        modified = 0
        missing = 0
        new_files: list[str] = []
        violations: list[str] = []

        for rel_path in self._files:
            p = Path(rel_path)
            stored = self._manifest.get(rel_path)

            if not p.exists():
                missing += 1
                violations.append(f"MISSING: {rel_path}")
                continue

            current_hash, _ = self._hash_file(p)
            if stored is None:
                new_files.append(rel_path)
                # New file since sealing — not necessarily a violation
                continue

            if current_hash != stored.sha256:
                modified += 1
                violations.append(f"MODIFIED: {rel_path}")
            else:
                ok += 1

        integrity = modified == 0 and missing == 0

        report = KernelReport(
            timestamp=datetime.now(timezone.utc).isoformat(),
            total_files=len(self._files),
            ok=ok,
            modified=modified,
            missing=missing,
            new_files=len(new_files),
            integrity=integrity,
            violations=violations,
        )

        if violations:
            logger.warning("Kernel integrity violations: %s", violations)
        else:
            logger.debug("Kernel integrity: OK (%d files)", ok)

        return report

    def get_manifest(self) -> list[KernelFile]:
        return list(self._manifest.values())

    def is_sealed(self) -> bool:
        return len(self._manifest) > 0


_kernel: Optional[ImmutableKernel] = None


def get_immutable_kernel() -> ImmutableKernel:
    global _kernel
    if _kernel is None:
        _kernel = ImmutableKernel()
    return _kernel
