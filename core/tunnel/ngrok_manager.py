"""
ROSA OS — Ngrok Tunnel Manager.

Provides a public HTTPS URL so Rosa is accessible from any device.
Tunnel URL is saved to memory/tunnel.txt for QR code generation.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger("rosa.tunnel")

_TUNNEL_FILE = Path("memory/tunnel.txt")
_public_url: Optional[str] = None
_tunnel_task: Optional[asyncio.Task] = None


async def start_tunnel(port: int = 8000) -> Optional[str]:
    """Start ngrok tunnel. Returns public URL or None if pyngrok not installed."""
    global _public_url
    if _public_url:
        return _public_url
    try:
        from pyngrok import ngrok, conf
        # Use auth token from env if available
        import os
        token = os.getenv("NGROK_AUTH_TOKEN", "")
        if token:
            conf.get_default().auth_token = token

        tunnel = ngrok.connect(port, "http")
        _public_url = tunnel.public_url
        _save_url(_public_url)
        logger.info("Ngrok tunnel started: %s → localhost:%d", _public_url, port)
        return _public_url
    except ImportError:
        logger.info("pyngrok not installed — tunnel disabled (pip install pyngrok)")
    except Exception as exc:
        logger.warning("Ngrok failed to start: %s", exc)
    return None


async def stop_tunnel() -> None:
    """Stop all ngrok tunnels."""
    global _public_url
    try:
        from pyngrok import ngrok
        ngrok.kill()
        _public_url = None
        _TUNNEL_FILE.unlink(missing_ok=True)
        logger.info("Ngrok tunnel stopped")
    except Exception as exc:
        logger.debug("Ngrok stop error: %s", exc)


def get_public_url() -> Optional[str]:
    """Return current public URL (from memory or file)."""
    global _public_url
    if _public_url:
        return _public_url
    if _TUNNEL_FILE.exists():
        url = _TUNNEL_FILE.read_text().strip()
        if url:
            _public_url = url
            return url
    return None


def _save_url(url: str) -> None:
    _TUNNEL_FILE.parent.mkdir(parents=True, exist_ok=True)
    _TUNNEL_FILE.write_text(url)


def generate_qr_code(url: str) -> Optional[str]:
    """Generate QR code as base64 PNG. Returns None if qrcode not installed."""
    try:
        import qrcode
        import io
        import base64
        qr = qrcode.QRCode(version=1, box_size=6, border=2)
        qr.add_data(url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="#10a37f", back_color="#212121")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
    except ImportError:
        logger.debug("qrcode not installed — pip install qrcode[pil]")
        return None
    except Exception as exc:
        logger.debug("QR generation failed: %s", exc)
        return None


class TunnelManager:
    """Manages the ngrok tunnel lifecycle."""

    def __init__(self) -> None:
        self._url: Optional[str] = None

    async def start(self, port: int = 8000) -> Optional[str]:
        self._url = await start_tunnel(port)
        return self._url

    async def stop(self) -> None:
        await stop_tunnel()
        self._url = None

    def url(self) -> Optional[str]:
        return self._url or get_public_url()

    def qr_code(self) -> Optional[str]:
        url = self.url()
        return generate_qr_code(url) if url else None


_manager: Optional[TunnelManager] = None


def get_tunnel_manager() -> TunnelManager:
    global _manager
    if _manager is None:
        _manager = TunnelManager()
    return _manager
