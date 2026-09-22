"""The one setting the search has, and the bounds it must keep."""

import pytest
from pydantic import ValidationError

from app.core.settings import Settings
from tests.conftest import UNREACHABLE_DATABASE_URL

VALID_URL = UNREACHABLE_DATABASE_URL


def settings(**overrides: object) -> Settings:
    return Settings(_env_file=None, database_url=VALID_URL, **overrides)  # type: ignore[arg-type]


def test_the_default_effort_is_what_the_requirements_fix() -> None:
    assert settings().hnsw_ef_search == 40


@pytest.mark.parametrize("value", [0, -1, 1001], ids=["zero", "negative", "above the maximum"])
def test_an_effort_outside_the_bounds_is_refused(value: int) -> None:
    with pytest.raises(ValidationError):
        settings(hnsw_ef_search=value)


def test_the_maximum_itself_is_allowed() -> None:
    assert settings(hnsw_ef_search=1000).hnsw_ef_search == 1000


def test_the_effort_is_read_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", VALID_URL)
    monkeypatch.setenv("HNSW_EF_SEARCH", "120")

    assert Settings(_env_file=None).hnsw_ef_search == 120  # type: ignore[call-arg]
