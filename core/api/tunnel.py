"""ROSA OS — Tunnel API (ngrok public URL + QR code)."""

from fastapi import APIRouter
from typing import Optional

router = APIRouter(prefix="/api/tunnel", tags=["tunnel"])


@router.get("/url")
async def get_tunnel_url():
    from core.tunnel.ngrok_manager import get_tunnel_manager
    mgr = get_tunnel_manager()
    url = mgr.url()
    return {"url": url, "active": url is not None}


@router.get("/qr")
async def get_tunnel_qr():
    from core.tunnel.ngrok_manager import get_tunnel_manager
    mgr = get_tunnel_manager()
    url = mgr.url()
    if not url:
        return {"qr": None, "url": None, "message": "Туннель не запущен"}
    qr = mgr.qr_code()
    return {"qr": qr, "url": url}


@router.post("/start")
async def start_tunnel(port: int = 8000):
    from core.tunnel.ngrok_manager import get_tunnel_manager
    mgr = get_tunnel_manager()
    url = await mgr.start(port)
    return {"url": url, "success": url is not None}


@router.post("/stop")
async def stop_tunnel():
    from core.tunnel.ngrok_manager import get_tunnel_manager
    mgr = get_tunnel_manager()
    await mgr.stop()
    return {"success": True}
