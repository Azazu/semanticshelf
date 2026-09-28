"""The embedding-model settings: their defaults, the way a list is written in
the environment, and the guard that keeps a configuration from naming a model
this build cannot run."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core import settings as settings_module
from app.core.settings import Settings
from app.domain import (
    CLIP_VIT_L14,
    DINOV2_LARGE,
    IMPLEMENTED_MODELS,
    MCLIP_XLMR_L14,
    QUERY_ENCODERS,
)

VALID_URL = "postgresql+asyncpg://localhost/semanticshelf"


def settings(**overrides: object) -> Settings:
    return Settings(_env_file=None, database_url=VALID_URL, **overrides)  # type: ignore[arg-type]


def test_defaults_are_exactly_what_the_proposal_states() -> None:
    s = settings()
    # Both implemented keys, in sorted order: FR-IDX-1 makes every model this
    # build can run enabled by default, which is why an upload queues two.
    assert s.enabled_models == (CLIP_VIT_L14, DINOV2_LARGE)
    assert s.model_warmup == ()
    assert s.model_cache == Path(".data/models")
    assert s.clip_model_name == "openai/clip-vit-large-patch14"
    assert s.dinov2_model_name == "facebook/dinov2-large"
    assert s.torch_num_threads == 0
    assert s.embed_batch_size == 8
    assert s.inference_workers == 2


def test_the_default_configuration_only_enables_what_this_build_implements() -> None:
    assert set(settings().enabled_models) <= IMPLEMENTED_MODELS


def test_a_model_without_an_adapter_is_refused_by_name(monkeypatch: pytest.MonkeyPatch) -> None:
    # Every key the schema declares has an adapter today, so the guard is shown
    # against its own rule rather than against an accident of the table: with
    # only CLIP implemented, naming the other key is refused by name.
    monkeypatch.setattr(settings_module, "IMPLEMENTED_MODELS", frozenset({CLIP_VIT_L14}))
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


def test_a_key_named_twice_is_kept_once() -> None:
    # Two entries would mean two indexing jobs per asset for one model.
    assert settings(enabled_models=f"{CLIP_VIT_L14},{CLIP_VIT_L14}").enabled_models == (
        CLIP_VIT_L14,
    )


@pytest.mark.parametrize(
    "overrides",
    [{"torch_num_threads": -1}, {"embed_batch_size": 0}, {"inference_workers": 0}],
    ids=["threads", "batch", "workers"],
)
def test_numbers_outside_their_range_are_refused(overrides: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        settings(**overrides)


# --- the forms an operator actually writes ------------------------------------
#
# The tests above hand the value to the constructor, which is not the path a
# deployment takes. A list setting is a complex type, and the environment source
# would read it as JSON before any validator ran, so the documented form has to
# be tested through the environment itself — where it once failed outright.


def environment_settings(monkeypatch: pytest.MonkeyPatch, **variables: str) -> Settings:
    monkeypatch.setenv("DATABASE_URL", VALID_URL)
    for name, value in variables.items():
        monkeypatch.setenv(name, value)
    return Settings(_env_file=None)  # type: ignore[call-arg]


def test_the_documented_environment_form_is_read(monkeypatch: pytest.MonkeyPatch) -> None:
    s = environment_settings(monkeypatch, ENABLED_MODELS=CLIP_VIT_L14, MODEL_WARMUP=CLIP_VIT_L14)
    assert s.enabled_models == (CLIP_VIT_L14,)
    assert s.model_warmup == (CLIP_VIT_L14,)


def test_an_empty_variable_means_an_empty_list(monkeypatch: pytest.MonkeyPatch) -> None:
    # The documented template line is `MODEL_WARMUP=`.
    assert environment_settings(monkeypatch, MODEL_WARMUP="").model_warmup == ()


def test_several_keys_are_separated_by_commas_in_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A JSON-decoded value would have failed outright rather than split, which
    # is what this form once did.
    s = environment_settings(monkeypatch, ENABLED_MODELS=f"{CLIP_VIT_L14},{DINOV2_LARGE}")
    assert s.enabled_models == (CLIP_VIT_L14, DINOV2_LARGE)


def test_a_checkpoint_may_be_pointed_elsewhere(monkeypatch: pytest.MonkeyPatch) -> None:
    # A mirror, an air-gapped copy or a compatible fine-tune. A checkpoint of
    # the wrong width is refused at load, not here.
    s = environment_settings(monkeypatch, DINOV2_MODEL_NAME="mirror/dinov2-large")
    assert s.dinov2_model_name == "mirror/dinov2-large"


def test_the_same_forms_are_read_from_a_dotenv_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("ENABLED_MODELS", raising=False)
    monkeypatch.delenv("MODEL_WARMUP", raising=False)
    config = tmp_path / ".env"
    config.write_text(
        f"DATABASE_URL={VALID_URL}\nENABLED_MODELS={CLIP_VIT_L14}\nMODEL_WARMUP=\n",
        encoding="utf-8",
    )

    s = Settings(_env_file=config)  # type: ignore[call-arg]

    assert s.enabled_models == (CLIP_VIT_L14,)
    assert s.model_warmup == ()


# --- query encoders -----------------------------------------------------------


def test_no_encoder_is_enabled_by_default() -> None:
    # Unlike the models: an encoder is gigabytes of weights for a question most
    # deployments never ask, so enabling one is a decision somebody took.
    assert settings().enabled_query_encoders == ()


def test_an_encoder_is_enabled_beside_the_model_it_answers_in() -> None:
    s = settings(enabled_query_encoders=(MCLIP_XLMR_L14,))

    assert s.enabled_query_encoders == (MCLIP_XLMR_L14,)
    assert QUERY_ENCODERS[MCLIP_XLMR_L14] in s.enabled_models


def test_an_encoder_this_build_does_not_implement_is_refused() -> None:
    with pytest.raises(ValidationError) as refusal:
        settings(enabled_query_encoders=("mclip-of-the-future",))

    assert "does not implement" in str(refusal.value)
    assert "mclip-of-the-future" in str(refusal.value)


def test_an_encoder_whose_space_is_not_enabled_is_refused() -> None:
    # Its vectors would have nothing to be compared with, and a search would
    # answer an empty page as if the corpus were empty.
    with pytest.raises(ValidationError) as refusal:
        settings(enabled_query_encoders=(MCLIP_XLMR_L14,), enabled_models=(DINOV2_LARGE,))

    message = str(refusal.value)
    assert MCLIP_XLMR_L14 in message and CLIP_VIT_L14 in message


def test_the_encoder_list_is_written_the_same_way_as_the_models(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    s = environment_settings(monkeypatch, ENABLED_QUERY_ENCODERS=MCLIP_XLMR_L14)

    assert s.enabled_query_encoders == (MCLIP_XLMR_L14,)


def test_the_encoder_cannot_be_pointed_at_other_weights() -> None:
    """There is no setting for it, and that is the point.

    A model's checkpoint is a setting because a mirror or a compatible
    fine-tune is an operator's choice and the width check keeps it honest. The
    encoder's key carries a claim about another model's space that no runtime
    check can verify and that ADR-005 backs with a measurement of *these*
    bytes, so other weights are another encoder rather than this one.
    """
    fields = set(Settings.model_fields)

    assert not [name for name in fields if "mclip" in name]


def test_warming_may_name_an_enabled_encoder() -> None:
    # The largest download this service has: leaving it out of the warm-up
    # would make the first query in another language wait for all of it.
    s = settings(enabled_query_encoders=(MCLIP_XLMR_L14,), model_warmup=(MCLIP_XLMR_L14,))

    assert s.model_warmup == (MCLIP_XLMR_L14,)


def test_warming_an_encoder_that_is_not_enabled_is_refused() -> None:
    with pytest.raises(ValidationError) as refusal:
        settings(model_warmup=(MCLIP_XLMR_L14,))

    assert "not enabled" in str(refusal.value)
