"""FastAPI app factory: CORS, JSON-only error handling, DB init on startup."""
import asyncio
import logging
from collections import defaultdict
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import db
from .config import Settings, get_settings
from .llm import AllProvidersUnavailable, LLMClient
from .routes import router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("app")


class SessionLocks:
    """Lazily created per-session asyncio locks."""

    def __init__(self) -> None:
        self._locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    def get(self, session_id: str) -> asyncio.Lock:
        return self._locks[session_id]


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        db.init_db(settings.database_path)  # schema is created automatically on startup
        yield

    app = FastAPI(title="Lyftr AI Chatbot", lifespan=lifespan)
    app.state.settings = settings
    app.state.llm = LLMClient(settings)
    app.state.session_locks = SessionLocks()

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],  # includes X-Simulate-Failure
    )

    @app.exception_handler(AllProvidersUnavailable)
    async def _all_failed(_: Request, __: AllProvidersUnavailable):
        return JSONResponse(status_code=503, content={"detail": "all providers unavailable"})

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception):
        logger.exception("unhandled error: %s", type(exc).__name__)
        return JSONResponse(status_code=500, content={"detail": "internal server error"})

    app.include_router(router)
    return app


app = create_app()
