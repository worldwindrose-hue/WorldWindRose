"""
ROSA OS — Web Push Notifications.

VAPID-based push notifications so Rosa can reach the owner
on any device that has the PWA installed.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("rosa.notifications")

_VAPID_FILE = Path("memory/vapid_keys.json")
_SUBS_FILE = Path("memory/push_subscriptions.json")


# ── VAPID KEY MANAGEMENT ──────────────────────────────────────────────────

def get_or_create_vapid_keys() -> dict[str, str]:
    """Load VAPID keys or generate new ones on first run."""
    if _VAPID_FILE.exists():
        return json.loads(_VAPID_FILE.read_text())
    try:
        from py_vapid import Vapid
        vp = Vapid()
        vp.generate_keys()
        keys = {
            "private_key": vp.private_pem().decode(),
            "public_key": vp.public_key.public_bytes(
                __import__("cryptography.hazmat.primitives.serialization", fromlist=["Encoding", "PublicFormat"]).Encoding.PEM,
                __import__("cryptography.hazmat.primitives.serialization", fromlist=["Encoding", "PublicFormat"]).PublicFormat.SubjectPublicKeyInfo,
            ).decode(),
        }
        _VAPID_FILE.parent.mkdir(parents=True, exist_ok=True)
        _VAPID_FILE.write_text(json.dumps(keys, indent=2))
        logger.info("VAPID keys generated and saved to %s", _VAPID_FILE)
        return keys
    except ImportError:
        logger.info("py_vapid not installed — push disabled (pip install py_vapid)")
        return {}
    except Exception as exc:
        logger.warning("VAPID key generation failed: %s", exc)
        return {}


def get_vapid_public_key() -> Optional[str]:
    """Return the VAPID public key for frontend subscription."""
    try:
        from py_vapid import Vapid
        import base64
        keys = get_or_create_vapid_keys()
        if not keys:
            return None
        vp = Vapid.from_pem(keys["private_key"].encode())
        raw = vp.public_key.public_bytes(
            __import__("cryptography.hazmat.primitives.serialization", fromlist=["Encoding", "PublicFormat"]).Encoding.X962,
            __import__("cryptography.hazmat.primitives.serialization", fromlist=["Encoding", "PublicFormat"]).PublicFormat.UncompressedPoint,
        )
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()
    except Exception as exc:
        logger.debug("get_vapid_public_key error: %s", exc)
        return None


# ── SUBSCRIPTION STORE ────────────────────────────────────────────────────

def load_subscriptions() -> list[dict[str, Any]]:
    if not _SUBS_FILE.exists():
        return []
    try:
        return json.loads(_SUBS_FILE.read_text())
    except Exception:
        return []


def save_subscriptions(subs: list[dict[str, Any]]) -> None:
    _SUBS_FILE.parent.mkdir(parents=True, exist_ok=True)
    _SUBS_FILE.write_text(json.dumps(subs, indent=2, ensure_ascii=False))


def add_subscription(subscription: dict[str, Any]) -> None:
    subs = load_subscriptions()
    # Avoid duplicates by endpoint
    endpoint = subscription.get("endpoint", "")
    subs = [s for s in subs if s.get("endpoint") != endpoint]
    subs.append(subscription)
    save_subscriptions(subs)
    logger.info("Push subscription added (total: %d)", len(subs))


def remove_subscription(endpoint: str) -> None:
    subs = load_subscriptions()
    subs = [s for s in subs if s.get("endpoint") != endpoint]
    save_subscriptions(subs)


# ── SENDING ───────────────────────────────────────────────────────────────

async def send_push_notification(
    title: str,
    body: str,
    url: str = "/",
    tag: str = "rosa",
) -> dict[str, int]:
    """Send push notification to all subscribers. Returns {sent, failed}."""
    subs = load_subscriptions()
    if not subs:
        return {"sent": 0, "failed": 0, "reason": "no_subscribers"}

    try:
        from pywebpush import webpush, WebPushException
        keys = get_or_create_vapid_keys()
        if not keys:
            return {"sent": 0, "failed": 0, "reason": "no_vapid_keys"}
    except ImportError:
        logger.info("pywebpush not installed — push disabled (pip install pywebpush)")
        return {"sent": 0, "failed": 0, "reason": "not_installed"}

    payload = json.dumps({"title": title, "body": body, "url": url, "tag": tag})
    sent = 0
    failed = 0
    dead_endpoints = []

    for sub in subs:
        try:
            webpush(
                subscription_info=sub,
                data=payload,
                vapid_private_key=keys["private_key"],
                vapid_claims={"sub": "mailto:rosa@rosa.local"},
                content_encoding="aes128gcm",
            )
            sent += 1
        except Exception as exc:
            failed += 1
            err_str = str(exc)
            if "410" in err_str or "404" in err_str:
                dead_endpoints.append(sub.get("endpoint", ""))
            logger.debug("Push failed for endpoint: %s", exc)

    # Clean dead subscriptions
    if dead_endpoints:
        remaining = [s for s in subs if s.get("endpoint") not in dead_endpoints]
        save_subscriptions(remaining)

    return {"sent": sent, "failed": failed}


class WebPushManager:
    """High-level manager for web push notifications."""

    def public_key(self) -> Optional[str]:
        return get_vapid_public_key()

    def subscribe(self, subscription: dict[str, Any]) -> None:
        add_subscription(subscription)

    def unsubscribe(self, endpoint: str) -> None:
        remove_subscription(endpoint)

    def subscribers_count(self) -> int:
        return len(load_subscriptions())

    async def notify(self, title: str, body: str, url: str = "/", tag: str = "rosa") -> dict:
        return await send_push_notification(title, body, url, tag)

    async def notify_task_done(self, task_name: str) -> dict:
        return await self.notify(
            title="🌹 ROSA — Задача выполнена",
            body=f'"{task_name}" завершена',
            tag="task-done",
        )

    async def notify_error(self, error: str) -> dict:
        return await self.notify(
            title="⚠️ ROSA — Ошибка",
            body=error[:120],
            tag="error",
        )

    async def notify_morning_brief(self, summary: str) -> dict:
        return await self.notify(
            title="☀️ ROSA — Утренний брифинг",
            body=summary[:120],
            url="/?view=improve",
            tag="morning-brief",
        )


_push_manager: Optional[WebPushManager] = None


def get_push_manager() -> WebPushManager:
    global _push_manager
    if _push_manager is None:
        _push_manager = WebPushManager()
    return _push_manager
