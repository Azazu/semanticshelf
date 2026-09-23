"""The shared vocabulary: immutability, value domains and the model registry."""

import dataclasses
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.domain import (
    ASSET_SOURCES,
    CLIP_VIT_L14,
    CONTENT_TYPES,
    DINOV2_LARGE,
    EMBEDDING_MODELS,
    EXTENSION_BY_CONTENT_TYPE,
    FILE_EXTENSIONS,
    IMPLEMENTED_MODELS,
    JOB_STATUSES,
    MODEL_MODALITIES,
    Asset,
    Embedding,
    IndexingJob,
    Modality,
    NeighbourHit,
    UnknownModelError,
    dimension_of,
    modality_of,
    vector_index_name,
)

DOMAIN_OBJECTS = [Asset, Embedding, IndexingJob, NeighbourHit]


@pytest.mark.parametrize("cls", DOMAIN_OBJECTS, ids=lambda c: c.__name__)
def test_domain_objects_are_frozen(cls: type) -> None:
    assert dataclasses.is_dataclass(cls)
    assert cls.__dataclass_params__.frozen  # type: ignore[attr-defined]


def test_a_frozen_object_refuses_mutation() -> None:
    hit = NeighbourHit(asset_id=uuid4(), distance=0.25)
    with pytest.raises(dataclasses.FrozenInstanceError):
        hit.distance = 0.5  # type: ignore[misc]


def test_value_domains_match_the_specification() -> None:
    assert CONTENT_TYPES == ("image/jpeg", "image/png", "image/webp")
    assert FILE_EXTENSIONS == ("jpg", "png", "webp")
    assert ASSET_SOURCES == ("upload", "folder")
    assert JOB_STATUSES == ("pending", "running", "done", "failed")


def test_every_content_type_has_an_extension() -> None:
    assert set(EXTENSION_BY_CONTENT_TYPE) == set(CONTENT_TYPES)
    assert set(EXTENSION_BY_CONTENT_TYPE.values()) == set(FILE_EXTENSIONS)


def test_model_registry() -> None:
    assert EMBEDDING_MODELS == {"clip-vit-l14": 768, "dinov2-large": 1024}
    assert all(dimension > 0 for dimension in EMBEDDING_MODELS.values())
    assert dimension_of("clip-vit-l14") == 768
    with pytest.raises(KeyError):
        dimension_of("no-such-model")


def test_every_model_says_what_it_can_be_asked() -> None:
    # The table is what the router reads to refuse an impossible pair without
    # loading anything. A model added without an answer here would be refused
    # at the first request instead, which is the drift this test exists against.
    assert set(MODEL_MODALITIES) == set(EMBEDDING_MODELS)
    assert IMPLEMENTED_MODELS <= set(MODEL_MODALITIES)


def test_what_each_model_takes() -> None:
    assert modality_of(CLIP_VIT_L14) == Modality(text=True, images=True)
    assert modality_of(DINOV2_LARGE) == Modality(text=False, images=True)


def test_an_unknown_key_is_reported_the_way_every_layer_reports_one() -> None:
    with pytest.raises(UnknownModelError, match="no-such-model"):
        modality_of("no-such-model")


def test_a_modality_describes_itself_for_a_refusal() -> None:
    assert Modality(text=True, images=True).described == "text and pictures"
    assert Modality(text=False, images=True).described == "pictures"
    assert Modality(text=True, images=False).described == "text"


def test_a_model_that_takes_nothing_is_not_a_model() -> None:
    with pytest.raises(ValueError, match="embeds nothing"):
        Modality(text=False, images=False)


def test_vector_index_names_are_identifiers() -> None:
    names = {vector_index_name(key) for key in EMBEDDING_MODELS}
    assert names == {"ix_embeddings_clip_vit_l14", "ix_embeddings_dinov2_large"}
    assert all(name.replace("_", "").isalnum() for name in names)
    assert len(names) == len(EMBEDDING_MODELS)


def test_asset_carries_what_the_store_keeps() -> None:
    asset = Asset(
        id=uuid4(),
        created_at=datetime.now(UTC),
        sha256="a" * 64,
        content_type="image/png",
        file_ext="png",
        width=10,
        height=20,
        size_bytes=1234,
        original_filename=None,
        source="upload",
        tags=("dragon", "fog"),
        meta={"dataset": "demo"},
    )
    assert asset.tags == ("dragon", "fog")
    assert asset.meta["dataset"] == "demo"


def test_embedding_holds_its_model_and_vector() -> None:
    embedding = Embedding(
        id=uuid4(),
        asset_id=uuid4(),
        model="clip-vit-l14",
        vector=(0.1, 0.2),
        created_at=datetime.now(UTC),
    )
    assert embedding.model in EMBEDDING_MODELS
    assert isinstance(embedding.vector, tuple)
