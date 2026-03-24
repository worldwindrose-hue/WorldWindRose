"""
ROSA OS — macOS Automation Scenarios (Phase 5).

High-level automation built on MacController.
All actions logged. Dangerous actions require explicit human approval.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("rosa.mac.automation")


class MacAutomation:
    """High-level macOS automation scenarios."""

    def __init__(self) -> None:
        from core.mac.controller import get_mac_controller
        self._ctrl = get_mac_controller()

    def open_url_in_browser(self, url: str) -> dict[str, Any]:
        """Open URL in default browser."""
        result = self._ctrl.run_shell(f'open "{url}"')
        logger.info("Opened URL: %s", url)
        return {"success": True, "url": url, "result": result}

    def create_reminder(self, text: str, date: str = "") -> dict[str, Any]:
        """Create a macOS Reminder."""
        if date:
            script = f"""
            tell application "Reminders"
                make new reminder with properties {{name:"{text}", due date: date "{date}"}}
            end tell
            """
        else:
            script = f"""
            tell application "Reminders"
                make new reminder with properties {{name:"{text}"}}
            end tell
            """
        result = self._ctrl.run_applescript(script)
        return {"success": "error" not in result.lower(), "text": text, "result": result}

    def play_pause_spotify(self) -> dict[str, Any]:
        """Toggle play/pause in Spotify."""
        script = 'tell application "Spotify" to playpause'
        result = self._ctrl.run_applescript(script)
        return {"success": True, "result": result}

    def set_volume(self, level: int) -> dict[str, Any]:
        """Set system volume (0-100)."""
        level = max(0, min(100, level))
        result = self._ctrl.run_shell(f"osascript -e 'set volume output volume {level}'")
        return {"success": True, "level": level, "result": result}

    def lock_screen(self) -> dict[str, Any]:
        """Lock the macOS screen."""
        script = 'tell application "System Events" to keystroke "q" using {command down, control down}'
        result = self._ctrl.run_applescript(script)
        return {"success": True, "result": result}

    def send_notification(self, title: str, body: str) -> dict[str, Any]:
        """Send system notification."""
        ok = self._ctrl.send_notification(title=title, body=body)
        return {"success": ok, "title": title, "body": body}

    def get_frontmost_app(self) -> str:
        """Get the name of the frontmost application."""
        script = 'tell application "System Events" to get name of first application process whose frontmost is true'
        return self._ctrl.run_applescript(script)


_automation: MacAutomation | None = None


def get_mac_automation() -> MacAutomation:
    global _automation
    if _automation is None:
        _automation = MacAutomation()
    return _automation
