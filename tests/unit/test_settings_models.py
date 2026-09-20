"""The embedding-model settings: their defaults, and the guard that keeps a
configuration from naming a model this build cannot run."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.settings import Settings
from app.domain import CLIP_VIT_L14, DINOV2_LARGE, IMPLEMENTED_MODELS

VALID_URL = "postgresql+asyncpg://localhost/semanticshelf"


def settings(**overrides: object) -> Settings:
    return Settings(_env_file=None, database_url=VALID_URL, **overrides)  # type: ignore[arg-type]


def test_defaults_are_exactly_what_the_proposal_states() -> None:
    s = settings()
    assert s.enabled_models == (CLIP_VIT_L14,)
    assert s.model_warmup == ()
    assert s.model_cache == Path(".data/models")
    assert s.clip_model_name == "openai/clip-vit-large-patch14"
    assert s.torch_num_threads == 0
    assert s.embed_batch_size == 8
    assert s.inference_workers == 2


def test_the_default_configuration_only_enables_what_this_build_implements() -> None:
    assert set(settings().enabled_models) <= IMPLEMENTED_MODELS


def test_a_model_without_an_adapter_is_refused_by_name() -> None:
    with pytest.raises(ValidationError, match=DINOV2_LARGE):
        settings(enabled_models=(CLIP_VIT_L14, DINOV2_LARGE))


def test_an_invented_key_is_refused() -> None:
    with pytest.raises(ValidationError, match="clip-vit-l14-v2"):
        settings(enabled_models=("clip-vit-l14-v2",))


def test_warming_up_a_model_that_is_not_enabled_is_refused() -> None:
    with pytest.raises(ValidationError, match="not enabled"):
        settings(enabled_models=(), model_warmup=(CLIP_VIT_L14,))


def test_a_comma_separated_list_is_accepted() -> None:
    assert settings(enabled_models=f" {CLIP_VIT_L14} , ").enabled_models == (CLIP_VIT_L14,)
    assert settings(enabled_models="").enabled_models == ()


@pytest.mark.parametrize(
    "overrides",
    [{"torch_num_threads": -1}, {"embed_batch_size": 0}, {"inference_workers": 0}],
    ids=["threads", "batch", "workers"],
)
def test_numbers_outside_their_range_are_refused(overrides: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        settings(**overrides)
