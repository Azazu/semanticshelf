"""The threads that load models and run inference, away from the event loop.

Both halves of the work belong here. Inference holds the CPU for as long as a
forward pass takes; loading reads gigabytes from disk or the hub. Either one on
the loop would stop the service answering anything else, so the asynchronous
side never calls into a model directly — it goes through this pool.

The pool is deliberately separate from the one Starlette uses for file reads: a
burst of embedding calls must not starve them.
"""

import asyncio
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from typing import TYPE_CHECKING

from app.ml.base import Embedder
from app.ml.registry import get_embedder

if TYPE_CHECKING:  # pragma: no cover - imported for typing only
    from app.core.settings import Settings


def create_pool(settings: "Settings") -> ThreadPoolExecutor:
    return ThreadPoolExecutor(
        max_workers=settings.inference_workers, thread_name_prefix="inference"
    )


async def run_in_pool[**P, T](
    pool: ThreadPoolExecutor, function: Callable[P, T], *args: P.args, **kwargs: P.kwargs
) -> T:
    """Run a blocking call on the inference pool and await its result."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(pool, partial(function, *args, **kwargs))


async def acquire(pool: ThreadPoolExecutor, key: str, settings: "Settings") -> Embedder:
    """The embedder for a key, loading it on the pool if this is its first use."""
    return await run_in_pool(pool, get_embedder, key, settings)


async def warm_up(pool: ThreadPoolExecutor, settings: "Settings") -> tuple[str, ...]:
    """Load the models the configuration names, on the pool. Returns their keys."""
    for key in settings.model_warmup:
        await acquire(pool, key, settings)
    return tuple(settings.model_warmup)
