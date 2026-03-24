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

    yield

    # Stop proactive scheduler on shutdown
    try:
        from core.prediction.proactive import stop_scheduler
        stop_scheduler()
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

    return app


app = create_app()
