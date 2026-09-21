"""One loaded model per key per process, loaded the first time it is needed.

Weights are large and slow to read, so a model is loaded once and shared. The
cache stores only successes: a download that failed because the network was
down must not turn into a permanent failure for the life of the process.
"""

import threading
from collections.abc import Callable
from typing import TYPE_CHECKING

from app.domain import CLIP_VIT_L14, UnknownModelError
from app.ml.base import Embedder

if TYPE_CHECKING:  # pragma: no cover - imported for typing only
    from app.core.settings import Settings

Factory = Callable[["Settings"], Embedder]


def load_clip(settings: "Settings") -> Embedder:
    """Import the adapter here, not at module level: `torch` costs a few hundred
    megabytes and must not be dragged into a test run that never uses it."""
    from app.ml.clip import ClipEmbedder

    return ClipEmbedder.load(settings)


#: The models this build can actually run. `app.domain.IMPLEMENTED_MODELS`
#: declares the same set for configuration validation; a unit test holds them
#: together, so adding an adapter without enabling it — or the reverse — fails.
FACTORIES: dict[str, Factory] = {CLIP_VIT_L14: load_clip}

_registry_lock = threading.Lock()
_key_locks: dict[str, threading.Lock] = {}
_loaded: dict[str, Embedder] = {}


def _lock_for(key: str) -> threading.Lock:
    """One lock per key, so loading one model does not queue behind another."""
    with _registry_lock:
        return _key_locks.setdefault(key, threading.Lock())


def get_embedder(key: str, settings: "Settings") -> Embedder:
    """The embedder for a key, loading it on first use.

    Synchronous on purpose: the worker process calls it directly, and the
    asynchronous side reaches it through the inference pool (`app.ml.pool`), so
    a multi-gigabyte load never sits on the event loop.
    """
    cached = _loaded.get(key)
    if cached is not None:
        return cached
    if key not in settings.enabled_models:
        raise UnknownModelError(
            f"model {key!r} is not enabled; enabled: {', '.join(settings.enabled_models) or 'none'}"
        )
    factory = FACTORIES.get(key)
    if factory is None:
        raise UnknownModelError(f"model {key!r} has no adapter in this build")

    with _lock_for(key):
        cached = _loaded.get(key)
        if cached is not None:  # another caller won the race while we waited
            return cached
        embedder = factory(settings)  # may raise; deliberately not cached
        _loaded[key] = embedder
        return embedder


def loaded_keys() -> frozenset[str]:
    """Which models this process has loaded. Used by tests and by warm-up."""
    return frozenset(_loaded)


def clear() -> None:
    """Forget every loaded model. For tests; nothing in the service calls it."""
    with _registry_lock:
        _loaded.clear()
        _key_locks.clear()
