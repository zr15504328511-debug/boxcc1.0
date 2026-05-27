"""FastAPI application factory and entry point."""

import logging
import sys
from contextlib import AsyncExitStack, asynccontextmanager
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
from config.paths import get_data_dir

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
    logger.info(f"Loaded {len(config.models)} model(s), {len(config.get_enabled_agents())} agent(s)")

    # Wire the delegate workflow's SQLite checkpointer. AsyncSqliteSaver
    # is an async context manager that owns an aiosqlite connection pool,
    # so we keep it alive for the duration of the app via AsyncExitStack.
    # Failure to construct the checkpointer is non-fatal — the workflow
    # falls back to no-checkpoint mode and crash recovery is disabled.
    async with AsyncExitStack() as stack:
        try:
            from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
            from subagents.workflow import set_delegate_checkpointer

            checkpoint_path = get_data_dir() / "checkpoints.db"
            saver = await stack.enter_async_context(
                AsyncSqliteSaver.from_conn_string(str(checkpoint_path))
            )
            set_delegate_checkpointer(saver)
            logger.info("delegate workflow checkpointer attached at %s", checkpoint_path)
        except Exception:
            logger.exception("failed to attach delegate workflow checkpointer; continuing without crash recovery")

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
