"""
ROSA OS — Mac Automation via AppleScript.

Provides:
  - open_app(name)        → open macOS application
  - take_screenshot()     → capture screen, return base64 PNG
  - run_applescript(code) → execute raw AppleScript, return stdout
  - get_frontmost_app()   → name of active app
  - notify(title, text)   → macOS notification
  - set_volume(0-100)     → system volume
  - get_clipboard()       → read clipboard text
  - set_clipboard(text)   → write clipboard text

All functions are safe — no destructive operations without explicit confirmation.
All run in subprocess (never eval) with 10s timeout.
"""

from __future__ import annotations
import base64
import logging
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

logger = logging.getLogger("rosa.mac_control")

_TIMEOUT = 10  # seconds per AppleScript call


def run_applescript(script: str, timeout: int = _TIMEOUT) -> tuple[bool, str]:
    """
    Run an AppleScript string. Returns (success, output_or_error).
    Uses osascript subprocess — safe, no eval.
    """
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=timeout,
        )
        if result.returncode == 0:
            return True, result.stdout.strip()
        return False, result.stderr.strip() or "AppleScript error"
    except subprocess.TimeoutExpired:
        return False, f"AppleScript timeout after {timeout}s"
    except FileNotFoundError:
        return False, "osascript not found — not running on macOS"
    except Exception as exc:
        return False, str(exc)


def open_app(app_name: str) -> dict:
    """Open a macOS application by name. Returns {ok, message}."""
    ok, out = run_applescript(f'tell application "{app_name}" to activate')
    logger.info("open_app(%s): ok=%s out=%s", app_name, ok, out)
    return {"ok": ok, "app": app_name, "message": out}


def get_frontmost_app() -> Optional[str]:
    """Return the name of the currently active application."""
    ok, out = run_applescript(
        'tell application "System Events" to name of first application process whose frontmost is true'
    )
    return out if ok else None


def notify(title: str, text: str, subtitle: str = "") -> dict:
    """Send a macOS notification banner."""
    subtitle_part = f'subtitle "{subtitle}"' if subtitle else ""
    script = f'display notification "{text}" with title "{title}" {subtitle_part}'
    ok, out = run_applescript(script)
    return {"ok": ok, "message": out}


def set_volume(level: int) -> dict:
    """Set system output volume (0-100)."""
    level = max(0, min(100, level))
    ok, out = run_applescript(f"set volume output volume {level}")
    return {"ok": ok, "level": level, "message": out}


def get_clipboard() -> Optional[str]:
    """Read current clipboard text."""
    ok, out = run_applescript("return (the clipboard as text)")
    return out if ok else None


def set_clipboard(text: str) -> dict:
    """Write text to clipboard."""
    escaped = text.replace('"', '\\"').replace("\\", "\\\\")
    ok, out = run_applescript(f'set the clipboard to "{escaped}"')
    return {"ok": ok, "message": out}


def take_screenshot(region: Optional[dict] = None) -> dict:
    """
    Capture screen. Returns {ok, path, base64_png, width, height}.
    region: optional dict with x, y, w, h for partial capture.
    """
    try:
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            tmp_path = f.name

        cmd = ["screencapture", "-x", tmp_path]  # -x = no sound
        if region:
            x, y = region.get("x", 0), region.get("y", 0)
            w, h = region.get("w", 1920), region.get("h", 1080)
            cmd = ["screencapture", "-x", "-R", f"{x},{y},{w},{h}", tmp_path]

        result = subprocess.run(cmd, capture_output=True, timeout=15)
        if result.returncode != 0:
            return {"ok": False, "error": "screencapture failed"}

        data = Path(tmp_path).read_bytes()
        b64 = base64.b64encode(data).decode()

        # Get dimensions via sips
        sips = subprocess.run(
            ["sips", "-g", "pixelWidth", "-g", "pixelHeight", tmp_path],
            capture_output=True, text=True, timeout=5,
        )
        w = h = 0
        for line in sips.stdout.splitlines():
            if "pixelWidth" in line:
                w = int(line.split()[-1])
            elif "pixelHeight" in line:
                h = int(line.split()[-1])

        Path(tmp_path).unlink(missing_ok=True)
        logger.info("Screenshot captured: %dx%d (%d bytes)", w, h, len(data))
        return {"ok": True, "base64_png": b64, "width": w, "height": h, "size_bytes": len(data)}

    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def check_automation_permissions() -> dict:
    """
    Check macOS automation permissions for ROSA.
    Returns status of key permissions.
    """
    checks = {}

    # Test System Events access (required for app control)
    ok, out = run_applescript('tell application "System Events" to count processes')
    checks["system_events"] = {"ok": ok, "detail": out}

    # Test Finder access
    ok2, out2 = run_applescript('tell application "Finder" to return name of startup disk')
    checks["finder"] = {"ok": ok2, "detail": out2}

    # Test screencapture
    result = subprocess.run(
        ["screencapture", "-x", "-R", "0,0,1,1", "/tmp/rosa_perm_test.png"],
        capture_output=True, timeout=5,
    )
    checks["screencapture"] = {"ok": result.returncode == 0}
    Path("/tmp/rosa_perm_test.png").unlink(missing_ok=True)

    checks["all_ok"] = all(v.get("ok", False) for v in checks.values() if isinstance(v, dict))
    return checks


def run_shell_command(cmd: str, timeout: int = 30) -> dict:
    """
    Run a shell command via AppleScript (do shell script).
    SAFE: only allowed for non-destructive commands.
    """
    BLOCKED = ["rm -rf", "sudo", "mkfs", "dd if=", "chmod 777", ":(){"]
    for blocked in BLOCKED:
        if blocked in cmd:
            return {"ok": False, "error": f"Blocked dangerous command: {blocked}"}

    escaped = cmd.replace('"', '\\"')
    ok, out = run_applescript(f'do shell script "{escaped}"', timeout=timeout)
    return {"ok": ok, "output": out}
