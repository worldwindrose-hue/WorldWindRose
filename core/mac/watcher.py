"""
ROSA OS — macOS System Watcher (Phase 5).

Monitors CPU, RAM, disk, network.
Sends alerts if thresholds exceeded.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("rosa.mac.watcher")

CPU_ALERT_THRESHOLD = 90
RAM_ALERT_THRESHOLD = 85


def cpu_usage() -> float:
    try:
        import psutil
        return psutil.cpu_percent(interval=0.5)
    except ImportError:
        return -1.0


def ram_usage() -> dict[str, Any]:
    try:
        import psutil
        m = psutil.virtual_memory()
        return {"percent": m.percent, "available_gb": round(m.available / 1e9, 1), "total_gb": round(m.total / 1e9, 1)}
    except ImportError:
        return {"percent": -1.0, "available_gb": 0, "total_gb": 0}


def disk_usage(path: str = "/") -> dict[str, Any]:
    try:
        import psutil
        d = psutil.disk_usage(path)
        return {"percent": d.percent, "free_gb": round(d.free / 1e9, 1), "total_gb": round(d.total / 1e9, 1)}
    except ImportError:
        return {"percent": -1.0, "free_gb": 0, "total_gb": 0}


def network_speed() -> dict[str, float]:
    try:
        import psutil, time
        t1 = psutil.net_io_counters()
        time.sleep(0.5)
        t2 = psutil.net_io_counters()
        up_kbs = (t2.bytes_sent - t1.bytes_sent) / 512
        dn_kbs = (t2.bytes_recv - t1.bytes_recv) / 512
        return {"upload_kbs": round(up_kbs, 1), "download_kbs": round(dn_kbs, 1)}
    except ImportError:
        return {"upload_kbs": -1, "download_kbs": -1}


def running_processes(top_n: int = 10) -> list[dict[str, Any]]:
    try:
        import psutil
        procs = []
        for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]):
            try:
                procs.append(p.info)
            except Exception:
                pass
        procs.sort(key=lambda x: x.get("cpu_percent", 0), reverse=True)
        return procs[:top_n]
    except ImportError:
        return []


async def get_system_status() -> dict[str, Any]:
    """Full system status snapshot."""
    cpu = cpu_usage()
    ram = ram_usage()
    disk = disk_usage()

    alerts = []
    if cpu > CPU_ALERT_THRESHOLD:
        alerts.append(f"CPU перегружен: {cpu:.0f}%")
    if ram.get("percent", 0) > RAM_ALERT_THRESHOLD:
        alerts.append(f"RAM почти заполнена: {ram['percent']:.0f}%")

    return {
        "cpu_percent": cpu,
        "ram": ram,
        "disk": disk,
        "alerts": alerts,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }
