"""The three steps of a job, decided without a database.

The doubles below stand in for the repositories, not for PostgreSQL. What
these tests fix is the branching: which failure each condition raises, what a
step returns when its conditional update matched nothing, and that a batch
survives one job failing. That the updates really are conditional — that a
lease another runner reclaimed makes an update match nothing — is a property of
the database and belongs to `tests/integration/test_indexing.py`.
"""

import io
from collections.abc import Iterator, Sequence
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import TracebackType
from typing import Any
from uuid import UUID, uuid4

import pytest
from PIL import Image

from app.core.settings import Settings
from app.domain import CLIP_VIT_L14, DINOV2_LARGE, Asset, IndexingJob, dimension_of
from app.ml import registry
from app.ml.fake import FakeEmbedder
from app.repositories.jobs import ClaimedJob
from app.services import indexing
from app.storage import MediaStorage
from tests.fake_models import fake_models

CLIP_WIDTH = dimension_of(CLIP_VIT_L14)
NOW = datetime.now(UTC)


# --- the doubles --------------------------------------------------------------


class StubSession:
    """Enough of a session for the steps: a context manager with a transaction."""

    def __enter__(self) -> "StubSession":  # pragma: no cover - never used
        raise NotImplementedError

    async def __aenter__(self) -> "StubSession":
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False

    def begin(self) -> "StubTransaction":
        return StubTransaction()


class StubTransaction:
    async def __aenter__(self) -> "StubTransaction":
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool:
        return False


def sessions() -> Any:
    """A session factory whose sessions do nothing at all."""
    return StubSession


class StubAssetRepository:
    """Answers with whatever the test put in `rows`."""

    rows: dict[UUID, Asset] = {}

    def __init__(self, session: object) -> None:
        pass

    async def get(self, asset_id: UUID) -> Asset | None:
        return self.rows.get(asset_id)


class StubJobRepository:
    """Records every finishing call and answers as the test told it to."""

    lands = True
    calls: list[tuple[str, dict[str, Any]]] = []

    def __init__(self, session: object) -> None:
        pass

    async def mark_done(self, job_id: UUID, owned_until: datetime) -> bool:
        type(self).calls.append(("mark_done", {"job_id": job_id, "owned_until": owned_until}))
        return type(self).lands

    async def return_to_queue(
        self, job_id: UUID, owned_until: datetime, *, delay_seconds: int, reason: str
    ) -> bool:
        type(self).calls.append(
            ("return_to_queue", {"delay_seconds": delay_seconds, "reason": reason})
        )
        return type(self).lands

    async def mark_failed(self, job_id: UUID, owned_until: datetime, reason: str) -> bool:
        type(self).calls.append(("mark_failed", {"reason": reason}))
        return type(self).lands


class StubEmbeddingRepository:
    calls: list[dict[str, Any]] = []

    def __init__(self, session: object) -> None:
        pass

    async def upsert(self, *, asset_id: UUID, model: str, vector: tuple[float, ...]) -> None:
        type(self).calls.append({"asset_id": asset_id, "model": model, "width": len(vector)})


@pytest.fixture(autouse=True)
def doubles(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    StubAssetRepository.rows = {}
    StubJobRepository.lands = True
    StubJobRepository.calls = []
    StubEmbeddingRepository.calls = []
    monkeypatch.setattr(indexing, "AssetRepository", StubAssetRepository)
    monkeypatch.setattr(indexing, "IndexingJobRepository", StubJobRepository)
    monkeypatch.setattr(indexing, "EmbeddingRepository", StubEmbeddingRepository)
    yield


@pytest.fixture(autouse=True)
def fake_model() -> Iterator[None]:
    with fake_models():
        yield


@pytest.fixture
def settings(test_settings: Settings, tmp_path: Path) -> Settings:
    return test_settings.model_copy(update={"media_root": tmp_path / "media"})


@pytest.fixture
def storage(settings: Settings) -> MediaStorage:
    settings.media_root.mkdir(parents=True, exist_ok=True)
    return MediaStorage.at(settings.media_root)


@pytest.fixture
def pool(settings: Settings) -> Iterator[ThreadPoolExecutor]:
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="test-inference")
    yield executor
    executor.shutdown(wait=True)


# --- the fixtures' subjects ---------------------------------------------------


def claimed_job(*, model: str = CLIP_VIT_L14, attempts: int = 1, asset_id: UUID) -> ClaimedJob:
    owned_until = NOW + timedelta(seconds=600)
    return ClaimedJob(
        job=IndexingJob(
            id=uuid4(),
            asset_id=asset_id,
            model=model,
            status="running",
            attempts=attempts,
            available_at=NOW,
            lease_expires_at=owned_until,
            last_error=None,
            created_at=NOW,
            started_at=NOW,
            finished_at=None,
        ),
        owned_until=owned_until,
    )


def stored(
    storage: MediaStorage, *, mode: str = "RGB", size: tuple[int, int] = (400, 200)
) -> Asset:
    """An asset whose original is really on disk, as a runner will find it."""
    asset_id = uuid4()
    buffer = io.BytesIO()
    Image.new(mode, size, color=128 if mode == "L" else (10, 20, 30)).save(buffer, format="PNG")
    path = storage.original(asset_id, "png")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(buffer.getvalue())
    asset = Asset(
        id=asset_id,
        created_at=NOW,
        sha256="0" * 64,
        content_type="image/png",
        file_ext="png",
        width=size[0],
        height=size[1],
        size_bytes=path.stat().st_size,
        original_filename=None,
        source="upload",
        tags=(),
        meta={},
    )
    StubAssetRepository.rows[asset_id] = asset
    return asset


# --- execution ----------------------------------------------------------------


async def test_a_stored_picture_becomes_a_vector(
    storage: MediaStorage, settings: Settings, pool: ThreadPoolExecutor
) -> None:
    asset = stored(storage)

    executed = await indexing.execute(
        claimed_job(asset_id=asset.id),
        session_factory=sessions(),
        storage=storage,
        settings=settings,
        pool=pool,
    )

    assert len(executed.vector) == CLIP_WIDTH


async def test_a_greyscale_original_is_converted_before_the_model_sees_it(
    storage: MediaStorage, settings: Settings, pool: ThreadPoolExecutor
) -> None:
    """What the model is handed, not merely that the work succeeded: every
    model here expects three channels, and a fake that accepts anything would
    hide a runner that stopped converting."""
    asset = stored(storage, mode="L")
    seen: list[str] = []
    embedder = FakeEmbedder(CLIP_VIT_L14, CLIP_WIDTH)
    real_embed = embedder.embed_images

    def note(images: Sequence[Any]) -> Any:
        seen.extend(image.mode for image in images)
        return real_embed(images)

    embedder.embed_images = note  # type: ignore[method-assign]
    registry.FACTORIES[CLIP_VIT_L14] = lambda settings: embedder
    registry.clear()

    executed = await indexing.execute(
        claimed_job(asset_id=asset.id),
        session_factory=sessions(),
        storage=storage,
        settings=settings,
        pool=pool,
    )

    assert seen == ["RGB"], "the picture was converted before inference"
    assert len(executed.vector) == CLIP_WIDTH


async def test_a_job_naming_a_model_this_build_does_not_run_is_refused(
    storage: MediaStorage, settings: Settings, pool: ThreadPoolExecutor
) -> None:
    # A deployment may run fewer models than the build implements, and a job
    # queued before that narrowing is still in the queue.
    asset = stored(storage)
    only_clip = settings.model_copy(update={"enabled_models": (CLIP_VIT_L14,)})

    with pytest.raises(indexing.ModelNotEnabled, match=DINOV2_LARGE):
        await indexing.execute(
            claimed_job(asset_id=asset.id, model=DINOV2_LARGE),
            session_factory=sessions(),
            storage=storage,
            settings=only_clip,
            pool=pool,
        )


async def test_work_whose_asset_row_is_gone_is_refused(
    storage: MediaStorage, settings: Settings, pool: ThreadPoolExecutor
) -> None:
    with pytest.raises(indexing.StoredFileMissing):
        await indexing.execute(
            claimed_job(asset_id=uuid4()),
            session_factory=sessions(),
            storage=storage,
            settings=settings,
            pool=pool,
        )


async def test_an_original_that_is_not_on_disk_is_refused(
    storage: MediaStorage, settings: Settings, pool: ThreadPoolExecutor
) -> None:
    asset = stored(storage)
    storage.original(asset.id, "png").unlink()

    with pytest.raises(indexing.StoredFileMissing):
        await indexing.execute(
            claimed_job(asset_id=asset.id),
            session_factory=sessions(),
            storage=storage,
            settings=settings,
            pool=pool,
        )


async def test_an_original_that_no_longer_decodes_is_refused(
    storage: MediaStorage, settings: Settings, pool: ThreadPoolExecutor
) -> None:
    asset = stored(storage)
    storage.original(asset.id, "png").write_bytes(b"not a picture any more")

    with pytest.raises(indexing.StoredFileUnusable, match="UndecodableImageError"):
        await indexing.execute(
            claimed_job(asset_id=asset.id),
            session_factory=sessions(),
            storage=storage,
            settings=settings,
            pool=pool,
        )


# --- finishing ----------------------------------------------------------------


async def test_a_finish_writes_the_vector_and_the_state(
    storage: MediaStorage, settings: Settings, pool: ThreadPoolExecutor
) -> None:
    asset = stored(storage)
    claimed = claimed_job(asset_id=asset.id)
    executed = await indexing.execute(
        claimed,
        session_factory=sessions(),
        storage=storage,
        settings=settings,
        pool=pool,
    )

    assert await indexing.finish(executed, session_factory=sessions()) is True

    assert [name for name, _ in StubJobRepository.calls] == ["mark_done"]
    assert StubEmbeddingRepository.calls == [
        {"asset_id": asset.id, "model": CLIP_VIT_L14, "width": CLIP_WIDTH}
    ]


async def test_a_finish_that_matched_nothing_writes_no_vector(
    storage: MediaStorage, settings: Settings, pool: ThreadPoolExecutor
) -> None:
    """The runner is no longer the owner: it discards its result rather than
    raising, and the vector it carried never reaches the store."""
    asset = stored(storage)
    executed = await indexing.execute(
        claimed_job(asset_id=asset.id),
        session_factory=sessions(),
        storage=storage,
        settings=settings,
        pool=pool,
    )
    StubJobRepository.lands = False

    assert await indexing.finish(executed, session_factory=sessions()) is False

    assert StubEmbeddingRepository.calls == []


# --- failing ------------------------------------------------------------------


async def test_a_failure_with_attempts_left_returns_the_job_with_its_backoff(
    settings: Settings,
) -> None:
    claimed = claimed_job(asset_id=uuid4(), attempts=1)

    assert await indexing.fail(
        claimed, RuntimeError("boom"), session_factory=sessions(), settings=settings
    )

    name, arguments = StubJobRepository.calls[0]
    assert name == "return_to_queue"
    assert arguments == {"delay_seconds": indexing.backoff_seconds(1), "reason": "RuntimeError"}


async def test_a_failure_with_no_attempts_left_ends_the_job(settings: Settings) -> None:
    spent = settings.model_copy(update={"job_max_attempts": 2})
    claimed = claimed_job(asset_id=uuid4(), attempts=2)

    assert await indexing.fail(
        claimed,
        indexing.StoredFileUnusable("UnsupportedFormatError: unsupported image format: BMP"),
        session_factory=sessions(),
        settings=spent,
    )

    name, arguments = StubJobRepository.calls[0]
    assert name == "mark_failed"
    assert arguments["reason"].startswith("StoredFileUnusable: UnsupportedFormatError")


async def test_a_failure_that_matched_nothing_is_reported_not_raised(
    settings: Settings,
) -> None:
    StubJobRepository.lands = False

    landed = await indexing.fail(
        claimed_job(asset_id=uuid4()),
        RuntimeError("late"),
        session_factory=sessions(),
        settings=settings,
    )

    assert landed is False


# --- the batch ----------------------------------------------------------------


async def test_a_batch_carries_on_past_a_job_that_failed(
    storage: MediaStorage,
    settings: Settings,
    pool: ThreadPoolExecutor,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    broken = stored(storage)
    storage.original(broken.id, "png").unlink()
    whole = stored(storage)
    batch = [claimed_job(asset_id=broken.id), claimed_job(asset_id=whole.id)]

    async def claim_both(factory: object, settings: Settings, **kwargs: object) -> list[ClaimedJob]:
        return batch

    monkeypatch.setattr(indexing, "claim", claim_both)

    taken = await indexing.run_batch(
        session_factory=sessions(), storage=storage, settings=settings, pool=pool
    )

    assert taken == 2
    assert [name for name, _ in StubJobRepository.calls] == ["return_to_queue", "mark_done"]
    assert [call["asset_id"] for call in StubEmbeddingRepository.calls] == [whole.id]


async def test_the_drain_never_raises_into_the_server(
    storage: MediaStorage,
    settings: Settings,
    pool: ThreadPoolExecutor,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def refuse(factory: object, settings: Settings, **kwargs: object) -> list[ClaimedJob]:
        raise RuntimeError("the database went away mid-claim")

    monkeypatch.setattr(indexing, "claim", refuse)

    await indexing.drain(session_factory=sessions(), storage=storage, settings=settings, pool=pool)
