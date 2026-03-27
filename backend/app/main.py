"""FastAPI application factory and entry point."""

import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Ensure backend root is on sys.path
backend_root = str(Path(__file__).parent.parent)
if backend_root not in sys.path:
    sys.path.insert(0, backend_root)

from app.routers import agents, chat, health, memory, models as models_router
from config.app_config import get_app_config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown hooks."""
    logger.info("boxcc backend starting up...")
    config = get_app_config()
    logger.info(f"Loaded {len(config.models)} model(s), {len(config.get_enabled_departments())} department(s)")
    yield
    # Flush memory queue on shutdown
    try:
        from agents.memory.queue import get_memory_queue
        get_memory_queue().flush()
    except Exception:
        pass
    logger.info("boxcc backend shutting down...")


def create_app() -> FastAPI:
    app = FastAPI(
        title="boxcc Backend",
        version="0.1.0",
        lifespan=lifespan,
    )

    # CORS - only localhost for desktop app
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register routers
    app.include_router(health.router)
    app.include_router(chat.router, prefix="/api")
    app.include_router(models_router.router, prefix="/api")
    app.include_router(memory.router, prefix="/api")
    app.include_router(agents.router, prefix="/api")

    return app


app = create_app()

if __name__ == "__main__":
    config = get_app_config()
    uvicorn.run(
        "app.main:app",
        host=config.server.host,
        port=config.server.port,
        reload=False,
        log_level="info",
    )
