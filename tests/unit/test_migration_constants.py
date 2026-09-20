"""The schema migration keeps its own frozen copy of the model registry and the
value domains, because a migration must not follow a constant that changes after
it ran. These tests are what holds the two copies together: extend one without
the other and `make check` fails here.
"""

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

from app.domain import (
    ASSET_SOURCES,
    CONTENT_TYPES,
    EMBEDDING_MODELS,
    FILE_EXTENSIONS,
    JOB_STATUSES,
    vector_index_name,
)
from app.models.embedding import dimension_check

REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATION_PATH = REPO_ROOT / "alembic" / "versions" / "0002_asset_schema.py"


@pytest.fixture(scope="module")
def migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location("migration_0002_asset_schema", MIGRATION_PATH)
    assert spec is not None and spec.loader is not None, MIGRATION_PATH
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_model_registry_matches(migration: ModuleType) -> None:
    assert migration.MODEL_DIMENSIONS == dict(EMBEDDING_MODELS)


def test_value_domains_match(migration: ModuleType) -> None:
    assert migration.CONTENT_TYPES == CONTENT_TYPES
    assert migration.FILE_EXTENSIONS == FILE_EXTENSIONS
    assert migration.ASSET_SOURCES == ASSET_SOURCES
    assert migration.JOB_STATUSES == JOB_STATUSES


def test_the_installed_check_matches_the_one_the_models_describe(migration: ModuleType) -> None:
    # The same SQL text on both sides: the constraint the database carries and
    # the constraint the ORM declares.
    assert migration.dimension_check() == dimension_check()


def test_vector_index_names_match(migration: ModuleType) -> None:
    assert {key: migration.vector_index_name(key) for key in EMBEDDING_MODELS} == {
        key: vector_index_name(key) for key in EMBEDDING_MODELS
    }
