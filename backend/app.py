"""
app.py — FastAPI application factory with CORS, error middleware,
structured logging, and lifespan-managed startup/shutdown.

Run with:  uvicorn app:main --reload --host 0.0.0.0 --port 8000
"""

import asyncio
import logging
import os
import platform
from contextlib import asynccontextmanager

# Set Windows-specific event loop policy for subprocess support
if platform.system() == "Windows":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from config import config
from routes import setup_routes
from llm_client import llm_client

# Import tools so they self-register with the MCP registry
import mcp_registry.tools.code_tools
import mcp_registry.tools.git_tools
import mcp_registry.tools.dev_tools
import mcp_registry.tools.repo_tools
import mcp_registry.tools.fix_tools
import mcp_registry.tools.analysis_tools
import mcp_registry.tools.zip_tools
import mcp_registry.tools.windows_tools
import mcp_registry.tools.gui_tools
import mcp_registry.tools.web_tools
import mcp_registry.tools.terminal_tools  # NEW: Shell execution + package install
import mcp_registry.tools.debug_tools    # NEW: PDB debugging + API client generator
from mcp_registry.resources import workspace_info  # NEW: Hybrid MCP Resource
from services.mcp_host import mcp_host # NEW: Multi-Server Orchestrator


# ─── Structured logging setup ─────────────────────────────────────────────────

class StructuredFormatter(logging.Formatter):
    """Emit structured key=value log lines for easy ingestion into Grafana / Loki."""

    def format(self, record: logging.LogRecord) -> str:
        base = super().format(record)
        extras = {
            k: v
            for k, v in record.__dict__.items()
            if k not in logging.LogRecord.__dict__ and not k.startswith("_")
            and k not in ("message", "asctime", "msg", "args", "exc_info", "exc_text",
                          "stack_info", "lineno", "funcName", "created", "msecs",
                          "relativeCreated", "thread", "threadName", "processName",
                          "process", "pathname", "filename", "module", "levelno",
                          "levelname", "name")
        }
        if extras:
            pairs = " ".join(f"{k}={v!r}" for k, v in extras.items())
            return f"{base} | {pairs}"
        return base


def setup_logging():
    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    handler = logging.StreamHandler()
    handler.setFormatter(StructuredFormatter(fmt))
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.DEBUG if config.DEBUG else logging.INFO)


setup_logging()
logger = logging.getLogger(__name__)


# ─── Background tasks ──────────────────────────────────────────────────────────

async def _session_cleanup_task():
    """Periodically purge expired conversation sessions."""
    from copilot.conversation_manager import conversation_manager
    while True:
        await asyncio.sleep(300)  # every 5 minutes
        conversation_manager.purge_expired()


# ─── Lifespan (startup + shutdown) ────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ──
    workspace = config.ALLOWED_BASE_PATH
    os.makedirs(workspace, exist_ok=True)
    logger.info(
        "app.startup",
        extra={"workspace": workspace, "model": config.LLM_MODEL, "url": config.LLM_BASE_URL},
    )
    cleanup_task = asyncio.create_task(_session_cleanup_task())

    # Trigger background indexing
    from services.embedding_service import embedding_service
    if config.USE_EMBEDDING:
        asyncio.create_task(embedding_service.index_workspace())

    yield  # app is running

    # ── Shutdown ──
    cleanup_task.cancel()
    from services.mcp_host import mcp_host
    await mcp_host.shutdown()
    await llm_client.close()
    logger.info("app.shutdown")


# ─── App factory ──────────────────────────────────────────────────────────────

def create_app() -> FastAPI:
    app = FastAPI(
        title="AI Coding Copilot",
        description="LLM-powered coding assistant with MCP tool support",
        version="1.0.0",
        lifespan=lifespan,
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Global error handler
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        logger.exception("unhandled_error", extra={"path": str(request.url.path)})
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": str(exc)},
        )

    setup_routes(app)

    # Static files for artifacts (screenshots, backups, etc.)
    from fastapi.staticfiles import StaticFiles
    app.mount("/static", StaticFiles(directory=config.ALLOWED_BASE_PATH), name="static")

    return app


# ─── ASGI entry point ──────────────────────────────────────────────────────────
# uvicorn app:main --reload
main = create_app()
