"""
ROSA OS — macOS Controller (Phase 5).

Native macOS API access via AppleScript and subprocess.
All system calls go through the firewall.
"""

from __future__ import annotations

import base64
import logging
import subprocess
from typing import Any

logger = logging.getLogger("rosa.mac.controller")

# Commands always blocked regardless of context
_BLOCKED_COMMANDS = [
    "rm -rf", "sudo rm", "format", "diskutil erase",
    "killall Finder", "shutdown", "reboot",
]


def _firewall_check(cmd: str) -> bool:
    """Return True if command is safe to run."""
    lower = cmd.lower()
    for blocked in _BLOCKED_COMMANDS:
        if blocked in lower:
            logger.warning("Firewall blocked command: %s", cmd[:80])
            return False
    return True


class MacController:
    """macOS system controller."""

    def run_applescript(self, script: str) -> str:
        """Run an AppleScript and return stdout."""
        if not _firewall_check(script):
            raise PermissionError(f"Firewall blocked AppleScript: {script[:80]}")
        try:
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True, text=True, timeout=15,
            )
            return result.stdout.strip() or result.stderr.strip()
        except subprocess.TimeoutExpired:
            return "AppleScript timed out"
        except FileNotFoundError:
            return "osascript not available (not macOS)"

    def run_shell(self, cmd: str, safe: bool = True) -> str:
        """Run a shell command (safe=True enforces firewall)."""
        if safe and not _firewall_check(cmd):
            raise PermissionError(f"Firewall blocked: {cmd[:80]}")
        try:
            result = subprocess.run(
                cmd, shell=True, capture_output=True, text=True, timeout=30,
            )
            return (result.stdout + result.stderr).strip()
        except subprocess.TimeoutExpired:
            return "Command timed out"

    def open_app(self, app_name: str) -> str:
        """Open a macOS application."""
        return self.run_shell(f'open -a "{app_name}"')

    def close_app(self, app_name: str) -> str:
        """Close a running application."""
        script = f'tell application "{app_name}" to quit'
        return self.run_applescript(script)

    def get_running_apps(self) -> list[str]:
        """List currently running applications."""
        script = 'tell application "System Events" to get name of every process where background only is false'
        result = self.run_applescript(script)
        if result:
            return [a.strip() for a in result.split(",")]
        return []

    def take_screenshot(self) -> str:
        """Take screenshot and return as base64 PNG."""
        try:
            import tempfile, os
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
                tmp = f.name
            subprocess.run(["screencapture", "-x", tmp], timeout=10, check=True)
            with open(tmp, "rb") as f:
                data = base64.b64encode(f.read()).decode()
            os.unlink(tmp)
            return data
        except Exception as exc:
            logger.error("Screenshot failed: %s", exc)
            return ""

    def get_clipboard(self) -> str:
        """Get clipboard text."""
        try:
            r = subprocess.run(["pbpaste"], capture_output=True, timeout=5)
            return r.stdout.decode("utf-8", errors="replace")
        except Exception:
            return ""

    def set_clipboard(self, text: str) -> bool:
        """Set clipboard text."""
        try:
            subprocess.run(["pbcopy"], input=text.encode("utf-8"), timeout=5)
            return True
        except Exception:
            return False

    def send_notification(self, title: str, body: str, subtitle: str = "ROSA OS") -> bool:
        """Send a macOS notification."""
        script = f'display notification "{body}" with title "{title}" subtitle "{subtitle}"'
        result = self.run_applescript(script)
        return "error" not in result.lower()

    def get_battery_level(self) -> int:
        """Get battery percentage (0-100, -1 if N/A)."""
        result = self.run_shell("pmset -g batt | grep -Eo '[0-9]+%'")
        try:
            return int(result.replace("%", "").strip().split("\n")[0])
        except Exception:
            return -1

    def get_wifi_status(self) -> dict[str, Any]:
        """Get WiFi connection status."""
        ssid = self.run_shell(
            "/System/Library/PrivateFrameworks/Apple80211.framework/Versions/Current/Resources/airport -I | awk '/ SSID/ {print $2}'"
        )
        return {
            "connected": bool(ssid and ssid != ""),
            "ssid": ssid or "",
        }

    def get_system_info(self) -> dict[str, Any]:
        """Get basic system info."""
        try:
            import psutil
            cpu = psutil.cpu_percent(interval=0.5)
            ram = psutil.virtual_memory()
            disk = psutil.disk_usage("/")
            return {
                "cpu_percent": cpu,
                "ram_percent": ram.percent,
                "ram_available_gb": round(ram.available / 1e9, 1),
                "disk_percent": disk.percent,
                "disk_free_gb": round(disk.free / 1e9, 1),
            }
        except ImportError:
            return {"error": "psutil not installed"}


_controller: MacController | None = None


def get_mac_controller() -> MacController:
    global _controller
    if _controller is None:
        _controller = MacController()
    return _controller
