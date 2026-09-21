"""Application factory.

`create_app()` builds a configured FastAPI instance; uvicorn starts it with
`--factory app.main:create_app` (see the Makefile), so importing this module
has no side effects and tests can build apps with their own settings.
"""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import __version__
from app.api import health
from app.core.errors import problem_responses, register_exception_handlers
from app.core.logging import configure_logging
from app.core.openapi import install_problem_media_type
from app.core.request_id import RequestIdMiddleware
from app.core.settings import Settings
from app.db.engine import create_engine, create_session_factory
from app.ml.pool import create_pool, warm_up
from app.services.images import configure_decoder_guard

DESCRIPTION = (
    "Semantic search over images: CLIP text→image and DINOv2 image→image embeddings "
    "in PostgreSQL + pgvector."
)


def create_app(settings: Settings | None = None) -> FastAPI:
    # Values come from the environment; mypy cannot see that the required field is read there.
    settings = settings if settings is not None else Settings()  # type: ignore[call-arg]
    configure_logging(settings.log_level, settings.log_json)
    # Pillow's own bomb guard, as the second line behind the upload's explicit
    # check on the header; see `app/services/images.py`.
    configure_decoder_guard(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = create_engine(settings)
        app.state.engine = engine
        app.state.session_factory = create_session_factory(engine)
        # The pool exists from the first moment, empty: it owns the threads, not
        # the models. Only MODEL_WARMUP loads anything here, and it loads it on
        # the pool, so a start that pulls gigabytes still answers other work.
        pool = create_pool(settings)
        app.state.inference_pool = pool
        try:
            await warm_up(pool, settings)
            yield
        finally:
            # `shutdown` waits for a load in flight; waiting for it in a thread
            # keeps even the last moments of the process off the loop.
            await asyncio.to_thread(pool.shutdown, True)
            await engine.dispose()

    app = FastAPI(
        title="SemanticShelf",
        version=__version__,
        description=DESCRIPTION,
        lifespan=lifespan,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        redoc_url=None,
        responses=problem_responses(422, 500),
    )
    app.state.settings = settings
    app.add_middleware(RequestIdMiddleware)
    register_exception_handlers(app)
    app.include_router(health.router)
    install_problem_media_type(app)
    return app
