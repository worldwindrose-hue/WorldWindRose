"""
ROSA OS — FastAPI application entry point.
Start with: uvicorn core.app:app --reload --port 8000
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.config import get_settings
from core.api.chat import router as chat_router
from core.api.tasks import router as tasks_router
from core.api.memory import router as memory_router
from core.api.self_improve import router as self_improve_router
from core.api.sessions import router as sessions_router
from core.api.folders import router as folders_router
from core.api.files import router as files_router
from core.api.voice import router as voice_router
from core.api.parse_url import router as parse_url_router
from core.api.knowledge import router as knowledge_router
from core.api.models import router as models_router
from core.api.integrations import router as integrations_router
from core.api.metacognition import router as metacognition_router
from core.api.projects import router as projects_router
from core.api.agents import router as agents_router
from core.api.pal import router as pal_router
from core.api.proactive import router as proactive_router
from core.api.vision import router as vision_router
from core.api.status import router as status_router
from core.api.fs import router as fs_router
from core.api.search import router as search_router
from core.api.mac import router as mac_router
from core.api.tunnel import router as tunnel_router
from core.api.notifications import router as notifications_router
from core.api.coding import router as coding_router
from core.api.swarm import router as swarm_auto_router
from core.api.economy import router as economy_router
from core.api.planning import router as planning_router
from core.api.ingest import router as ingest_router
try:
    from core.api.capabilities import router as capabilities_router
except Exception:
    capabilities_router = None

try:
    from core.api.audit import router as audit_router
except Exception:
    audit_router = None

try:
    from core.api.cache import router as cache_router
except Exception:
    cache_router = None

try:
    from core.api.prediction import router as prediction_router
except Exception:
    prediction_router = None

try:
    from core.api.transparency import router as transparency_router
except Exception:
    transparency_router = None

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("memory/rosa.log", mode="a"),
    ],
)
logger = logging.getLogger("rosa")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize resources on startup, clean up on shutdown."""
    settings = get_settings()
    logger.info("ROSA OS v%s starting on %s:%d", settings.app_version, settings.host, settings.port)

    # Initialize DB
    from core.memory.store import init_db
    await init_db()
    logger.info("Memory database initialized at %s", settings.db_path)

    # Ensure upload directory exists
    Path(settings.upload_dir).mkdir(parents=True, exist_ok=True)

    # Start proactive scheduler
    try:
        from core.prediction.proactive import start_scheduler
        start_scheduler()
        logger.info("Proactive scheduler started")
    except Exception as exc:
        logger.warning("Proactive scheduler failed to start: %s", exc)

    # Start offline monitor
    try:
        from core.offline.local_mode import start_offline_monitor
        start_offline_monitor()
        logger.info("Offline monitor started")
    except Exception as exc:
        logger.warning("Offline monitor failed to start: %s", exc)

    # Start backup scheduler
    try:
        from core.memory.backup import start_backup_scheduler
        start_backup_scheduler()
        logger.info("Backup scheduler started")
    except Exception as exc:
        logger.warning("Backup scheduler failed to start: %s", exc)

    # Start ngrok tunnel (non-blocking, optional)
    try:
        from core.tunnel.ngrok_manager import get_tunnel_manager
        import os
        if os.getenv("NGROK_AUTO_START", "false").lower() == "true":
            url = await get_tunnel_manager().start(settings.port)
            if url:
                logger.info("Public tunnel: %s", url)
    except Exception as exc:
        logger.debug("Tunnel start skipped: %s", exc)

    # Start ingest job queue
    try:
        from core.ingest.universal_ingester import register_all_handlers
        from core.ingest.job_queue import get_job_queue
        register_all_handlers()
        await get_job_queue().start()
        logger.info("Ingest job queue started")
    except Exception as exc:
        logger.warning("Ingest queue failed to start: %s", exc)

    # Run startup audit (non-blocking)
    try:
        from core.audit.startup_audit import run_startup_audit
        import asyncio
        asyncio.create_task(run_startup_audit())
        logger.info("Startup audit scheduled")
    except Exception as exc:
        logger.debug("Startup audit skipped: %s", exc)

    # Initialize VAPID keys for push notifications (non-blocking)
    try:
        from core.notifications.web_push import get_or_create_vapid_keys
        get_or_create_vapid_keys()
    except Exception:
        pass

    # Set initial status
    try:
        from core.status.tracker import set_status, RosaStatus
        set_status(RosaStatus.ONLINE, "ROSA OS запущена и готова к работе")
    except Exception:
        pass

    yield

    # Stop proactive scheduler on shutdown
    try:
        from core.prediction.proactive import stop_scheduler
        stop_scheduler()
    except Exception:
        pass

    # Stop ingest queue
    try:
        from core.ingest.job_queue import get_job_queue
        await get_job_queue().stop()
    except Exception:
        pass

    logger.info("ROSA OS shutting down")


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="ROSA OS",
        description="Hybrid AI Assistant Platform powered by Kimi K2.5",
        version=settings.app_version,
        lifespan=lifespan,
    )

    # CORS — allow local desktop clients
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:*", "http://127.0.0.1:*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # API routers
    app.include_router(chat_router)
    app.include_router(tasks_router)
    app.include_router(memory_router)
    app.include_router(self_improve_router)
    app.include_router(sessions_router)
    app.include_router(folders_router)
    app.include_router(files_router)
    app.include_router(voice_router)
    app.include_router(parse_url_router)
    app.include_router(knowledge_router)
    app.include_router(models_router)
    app.include_router(integrations_router)
    app.include_router(metacognition_router)
    app.include_router(projects_router)
    app.include_router(agents_router)
    app.include_router(pal_router)
    app.include_router(proactive_router)
    app.include_router(vision_router)
    app.include_router(status_router)
    app.include_router(fs_router)
    app.include_router(search_router)
    app.include_router(mac_router)
    app.include_router(tunnel_router)
    app.include_router(notifications_router)
    app.include_router(coding_router)
    app.include_router(swarm_auto_router)
    app.include_router(economy_router)
    app.include_router(planning_router)
    app.include_router(ingest_router)
    if capabilities_router:
        app.include_router(capabilities_router)
    if audit_router:
        app.include_router(audit_router)
    if cache_router:
        app.include_router(cache_router)
    if prediction_router:
        app.include_router(prediction_router)
    if transparency_router:
        app.include_router(transparency_router)

    # Health check
    @app.get("/health", tags=["system"])
    async def health() -> JSONResponse:
        return JSONResponse({"status": "ok", "version": settings.app_version})

    # Serve desktop UI as static files
    desktop_path = Path(__file__).parent.parent / "desktop"
    if desktop_path.exists():
        app.mount("/app", StaticFiles(directory=str(desktop_path), html=True), name="desktop")

        @app.get("/", include_in_schema=False)
        async def serve_index() -> FileResponse:
            return FileResponse(str(desktop_path / "index.html"))

        # PWA required files served at root
        @app.get("/manifest.json", include_in_schema=False)
        async def serve_manifest() -> FileResponse:
            return FileResponse(str(desktop_path / "manifest.json"), media_type="application/manifest+json")

        @app.get("/sw.js", include_in_schema=False)
        async def serve_sw() -> FileResponse:
            return FileResponse(str(desktop_path / "sw.js"), media_type="application/javascript",
                                headers={"Service-Worker-Allowed": "/"})

        @app.get("/icons/{filename}", include_in_schema=False)
        async def serve_icon(filename: str) -> FileResponse:
            icon_path = desktop_path / "icons" / filename
            if icon_path.exists():
                return FileResponse(str(icon_path))
            from fastapi import HTTPException
            raise HTTPException(status_code=404)

    return app


app = create_app()
