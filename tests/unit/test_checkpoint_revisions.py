"""Which weights a model key names, and what the service does when it cannot say.

A key is part of an embedding's identity, so what it names has to be fixed. A
checkpoint *name* is not fixed — it points at whatever a repository holds today
— so the service reads a commit. These are the rules around that: what counts as
a revision, which checkpoint a default revision belongs to, and that the one
deliberately unpinned case is passed no revision at all rather than a `None`
that happens to mean the same thing.
"""

from typing import Any

import numpy as np
import pytest
import torch
from structlog.testing import capture_logs

from app.core.settings import (
    DEFAULT_CLIP_CHECKPOINT,
    DEFAULT_CLIP_REVISION,
    DEFAULT_DINOV2_CHECKPOINT,
    DEFAULT_DINOV2_REVISION,
    Settings,
)

UNREACHABLE_DATABASE_URL = "postgresql+asyncpg://127.0.0.1:1/nowhere"
#: A full commit that is not either default, for "the operator configured one".
OTHER_COMMIT = "0123456789abcdef0123456789abcdef01234567"


def configured(**overrides: object) -> Settings:
    return Settings(  # type: ignore[call-arg]
        _env_file=None, database_url=UNREACHABLE_DATABASE_URL, **overrides
    )


# --- what the defaults are -----------------------------------------------------


@pytest.mark.parametrize(
    ("default", "name"),
    [(DEFAULT_CLIP_REVISION, "CLIP_REVISION"), (DEFAULT_DINOV2_REVISION, "DINOV2_REVISION")],
)
def test_each_default_revision_is_a_full_commit(default: str, name: str) -> None:
    """A default that were a branch would pin nothing while reading as pinned."""
    assert len(default) == 40, name
    assert set(default) <= set("0123456789abcdef"), name


@pytest.mark.parametrize(
    ("variable", "field"),
    [("CLIP_REVISION", "clip_revision"), ("DINOV2_REVISION", "dinov2_revision")],
)
def test_each_revision_is_read_from_its_documented_variable(
    monkeypatch: pytest.MonkeyPatch, variable: str, field: str
) -> None:
    monkeypatch.setenv(variable, OTHER_COMMIT)

    assert getattr(configured(), field) == OTHER_COMMIT


# --- what a revision may be ----------------------------------------------------


@pytest.mark.parametrize("field", ["clip_revision", "dinov2_revision"])
@pytest.mark.parametrize(
    "refused",
    [
        "main",
        "refs/heads/main",
        "v1.0",
        "32bd642",
        "32bd64288804d66eefd0ccbe215aa642df71ccZZ",
        "32BD64288804D66EEFD0CCBE215AA642DF71CC41",
        "",
        "   ",
        "32bd64288804d66eefd0ccbe215aa642df71cc41 ",
        "32bd64288804d66eefd0ccbe215aa642df71cc41\n",
        "\n32bd64288804d66eefd0ccbe215aa642df71cc41",
        "32bd64288804d66eefd0ccbe215aa642df71cc41\n32bd64288804d66eefd0ccbe215aa642df71cc41",
    ],
    ids=[
        "branch",
        "ref",
        "tag",
        "abbreviated",
        "not-hex",
        "uppercase",
        "empty",
        "whitespace",
        "trailing-space",
        "trailing-newline",
        "leading-newline",
        "two-lines",
    ],
)
def test_a_revision_that_is_not_a_commit_is_refused(field: str, refused: str) -> None:
    """Each of these is accepted by the model hub and resolves at load time,
    which is the defect pinning exists to remove.

    The newline cases are not decoration. Python's `$` also matches immediately
    before a final newline, so an anchored pattern accepts a 41-character value
    ending in one — and a revision read from a file or pasted with its line
    ending is exactly how that arrives. It then reaches the hub as `%0A` in a
    URL and fails at the first load instead of at startup.
    """
    with pytest.raises(ValueError, match=field.upper()):
        configured(**{field: refused})


@pytest.mark.parametrize(
    ("field", "accepted"),
    [
        ("clip_revision", DEFAULT_CLIP_REVISION),
        ("clip_revision", OTHER_COMMIT),
        ("dinov2_revision", DEFAULT_DINOV2_REVISION),
        ("dinov2_revision", OTHER_COMMIT),
    ],
)
def test_a_full_commit_is_accepted(field: str, accepted: str) -> None:
    assert getattr(configured(**{field: accepted}), field) == accepted


# --- which checkpoint a default revision belongs to ----------------------------


def test_a_default_checkpoint_is_read_at_its_default_revision() -> None:
    settings = configured()

    assert settings.clip_revision_in_effect == DEFAULT_CLIP_REVISION
    assert settings.dinov2_revision_in_effect == DEFAULT_DINOV2_REVISION


def test_a_configured_revision_is_used_whatever_the_name_says() -> None:
    settings = configured(
        clip_model_name="someone/clip-fine-tune",
        clip_revision=OTHER_COMMIT,
        dinov2_revision=OTHER_COMMIT,
    )

    assert settings.clip_revision_in_effect == OTHER_COMMIT
    assert settings.dinov2_revision_in_effect == OTHER_COMMIT


@pytest.mark.parametrize(
    ("name_field", "substituted", "effect"),
    [
        ("clip_model_name", "someone/clip-fine-tune", "clip_revision_in_effect"),
        ("dinov2_model_name", "someone/dinov2-mirror", "dinov2_revision_in_effect"),
    ],
)
def test_a_substituted_name_inherits_no_revision(
    name_field: str, substituted: str, effect: str
) -> None:
    """The default commit belongs to the repository that was replaced."""
    settings = configured(**{name_field: substituted})

    assert getattr(settings, effect) is None


@pytest.mark.parametrize(
    ("name_field", "substituted"),
    [("clip_model_name", "someone/clip-fine-tune"), ("dinov2_model_name", "someone/dinov2-mirror")],
)
def test_a_substituted_name_without_a_revision_still_starts(
    name_field: str, substituted: str
) -> None:
    """The shape of a deployment that worked before this change. It has to keep
    working: a refinement that refuses what was accepted yesterday is not one."""
    settings = configured(**{name_field: substituted})

    assert getattr(settings, name_field) == substituted


def test_naming_the_default_checkpoint_explicitly_is_not_a_substitution() -> None:
    settings = configured(
        clip_model_name=DEFAULT_CLIP_CHECKPOINT, dinov2_model_name=DEFAULT_DINOV2_CHECKPOINT
    )

    assert settings.clip_revision_in_effect == DEFAULT_CLIP_REVISION
    assert settings.dinov2_revision_in_effect == DEFAULT_DINOV2_REVISION


# --- what the adapters do with it ----------------------------------------------


class Recorder:
    """A stand-in for `from_pretrained` that remembers how it was called."""

    def __init__(self, answer: object) -> None:
        self.answer = answer
        self.calls: list[dict[str, Any]] = []

    def __call__(self, name: str, **keywords: Any) -> object:
        self.calls.append(keywords)
        return self.answer


class StubSplitter:
    """What `_truncation_flags` asks the processor for."""

    model_max_length = 77

    def __call__(self, texts: object, **keywords: Any) -> dict[str, list[list[int]]]:
        return {"input_ids": [[0]] * len(list(texts))}


class StubProcessor:
    """Enough of a processor for the width probe both adapters run at load."""

    @property
    def tokenizer(self) -> "StubSplitter":
        """A property rather than an attribute, which the repository's secret
        scanner reads as a credential assignment (change 17 hit the same)."""
        return StubSplitter()

    def __call__(self, **keywords: Any) -> dict[str, torch.Tensor]:
        return {"input_ids": torch.zeros(1, 1, dtype=torch.long)}


class StubModel:
    def __init__(self, width: int) -> None:
        self.width = width

    def eval(self) -> "StubModel":
        return self

    def get_text_features(self, **keywords: Any) -> torch.Tensor:
        return torch.ones(1, self.width)

    def __call__(self, **keywords: Any) -> object:
        """What `Dinov2Model.forward` returns: the normalised CLS token."""
        return type("Output", (), {"pooler_output": torch.ones(1, self.width)})()


def load_clip(monkeypatch: pytest.MonkeyPatch, settings: Settings) -> tuple[Recorder, Recorder]:
    import transformers

    from app.ml.clip import ClipEmbedder

    processor = Recorder(StubProcessor())
    model = Recorder(StubModel(768))
    monkeypatch.setattr(transformers.AutoProcessor, "from_pretrained", processor)
    monkeypatch.setattr(transformers.CLIPModel, "from_pretrained", model)
    monkeypatch.setattr(np, "concatenate", lambda rows: np.ones((1, 768), dtype=np.float32))

    ClipEmbedder.load(settings)
    return processor, model


def test_a_pinned_load_hands_one_revision_to_both_reads(
    monkeypatch: pytest.MonkeyPatch, tmp_path: object
) -> None:
    processor, model = load_clip(monkeypatch, configured(model_cache=tmp_path))

    assert processor.calls[0]["revision"] == DEFAULT_CLIP_REVISION
    assert model.calls[0]["revision"] == DEFAULT_CLIP_REVISION


def test_an_unpinned_load_hands_neither_read_a_revision(
    monkeypatch: pytest.MonkeyPatch, tmp_path: object
) -> None:
    """Not `revision=None` — no `revision` at all, so the call is the one this
    adapter made before revisions existed."""
    settings = configured(clip_model_name="someone/clip-fine-tune", model_cache=tmp_path)

    processor, model = load_clip(monkeypatch, settings)

    assert "revision" not in processor.calls[0]
    assert "revision" not in model.calls[0]


def load_dinov2(monkeypatch: pytest.MonkeyPatch, settings: Settings) -> tuple[Recorder, Recorder]:
    import transformers

    from app.ml.dinov2 import Dinov2Embedder

    processor = Recorder(StubProcessor())
    model = Recorder(StubModel(1024))
    monkeypatch.setattr(transformers.AutoProcessor, "from_pretrained", processor)
    monkeypatch.setattr(transformers.AutoModel, "from_pretrained", model)
    monkeypatch.setattr(np, "concatenate", lambda rows: np.ones((1, 1024), dtype=np.float32))

    Dinov2Embedder.load(settings)
    return processor, model


def test_the_picture_model_pinned_hands_one_revision_to_both_reads(
    monkeypatch: pytest.MonkeyPatch, tmp_path: object
) -> None:
    processor, model = load_dinov2(monkeypatch, configured(model_cache=tmp_path))

    assert processor.calls[0]["revision"] == DEFAULT_DINOV2_REVISION
    assert model.calls[0]["revision"] == DEFAULT_DINOV2_REVISION


def test_the_picture_model_unpinned_hands_neither_read_a_revision(
    monkeypatch: pytest.MonkeyPatch, tmp_path: object
) -> None:
    settings = configured(dinov2_model_name="someone/dinov2-mirror", model_cache=tmp_path)

    processor, model = load_dinov2(monkeypatch, settings)

    assert "revision" not in processor.calls[0]
    assert "revision" not in model.calls[0]


def test_an_unpinned_load_says_so(monkeypatch: pytest.MonkeyPatch, tmp_path: object) -> None:
    """An operator should not have to infer it from the absence of something."""
    settings = configured(clip_model_name="someone/clip-fine-tune", model_cache=tmp_path)

    with capture_logs() as recorded:
        load_clip(monkeypatch, settings)

    said = [line for line in recorded if line["event"] == "checkpoint is unpinned"]
    assert said, recorded
    assert said[0]["checkpoint"] == "someone/clip-fine-tune"
    assert said[0]["log_level"] == "warning"


def test_a_pinned_load_says_nothing_of_the_kind(
    monkeypatch: pytest.MonkeyPatch, tmp_path: object
) -> None:
    with capture_logs() as recorded:
        load_clip(monkeypatch, configured(model_cache=tmp_path))

    assert [line for line in recorded if "unpinned" in line["event"]] == []


def test_a_revision_read_from_the_environment_with_its_line_ending_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The path the value actually travels: a variable set from a file keeps the
    newline, and the environment source hands it over unchanged."""
    monkeypatch.setenv("CLIP_REVISION", DEFAULT_CLIP_REVISION + "\n")

    with pytest.raises(ValueError, match="CLIP_REVISION"):
        configured()


def test_the_picture_models_revision_too(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DINOV2_REVISION", DEFAULT_DINOV2_REVISION + "\n")

    with pytest.raises(ValueError, match="DINOV2_REVISION"):
        configured()
