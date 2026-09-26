"""The stack's definition says what the design says it says.

`docker-compose.yml` is where four promises of `openspec/specs/deployment` are
actually kept: health decides the order, the database is addressed inside the
stack rather than through the host's published port, the process serving
requests does not extract vectors, and nothing is published beyond loopback.
None of that is visible in the application's code, and a run of the stack is too
slow for the unit suite — so it is read here, from the file, as structure rather
than as text.
"""

from pathlib import Path
from typing import Any

import pytest
import yaml

COMPOSE = Path(__file__).resolve().parents[2] / "docker-compose.yml"
SERVICES = ("db", "migrate", "api", "worker", "ui")
#: The services that talk to the database. `ui` does not: it speaks HTTP only.
DATABASE_USERS = ("migrate", "api", "worker")


@pytest.fixture(scope="module")
def stack() -> dict[str, Any]:
    parsed: dict[str, Any] = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
    return parsed


def service(stack: dict[str, Any], name: str) -> dict[str, Any]:
    found: dict[str, Any] = stack["services"][name]
    return found


def test_the_stack_is_the_five_services_the_documentation_names(stack: dict[str, Any]) -> None:
    assert tuple(stack["services"]) == SERVICES


@pytest.mark.parametrize("name", DATABASE_USERS)
def test_the_database_is_addressed_inside_the_stack(stack: dict[str, Any], name: str) -> None:
    """Not through the port the host publishes: inside a container that address
    is the container's own loopback, and the migration would never connect."""
    url = service(stack, name)["environment"]["DATABASE_URL"]
    assert "@db:5432/" in url
    assert "127.0.0.1" not in url and "FORWARD_DB_PORT" not in url


def test_the_schema_is_brought_to_head_before_the_api_serves(stack: dict[str, Any]) -> None:
    assert service(stack, "migrate")["command"] == ["alembic", "upgrade", "head"]
    assert service(stack, "migrate")["restart"] == "no"
    depends = service(stack, "api")["depends_on"]
    assert depends["db"]["condition"] == "service_healthy"
    assert depends["migrate"]["condition"] == "service_completed_successfully"


@pytest.mark.parametrize("name", ("worker", "ui"))
def test_what_needs_the_api_waits_for_it_to_be_ready(stack: dict[str, Any], name: str) -> None:
    assert service(stack, name)["depends_on"]["api"]["condition"] == "service_healthy"


def test_readiness_is_what_the_api_s_healthcheck_asks(stack: dict[str, Any]) -> None:
    test = service(stack, "api")["healthcheck"]["test"]
    assert test[0] == "CMD"
    assert "/ready" in " ".join(test)


def test_the_worker_has_no_healthcheck_rather_than_a_pretend_one(stack: dict[str, Any]) -> None:
    """A command that greps a process list would call a runner stuck on a lease
    healthy. Where a stuck worker shows is the queue."""
    assert "healthcheck" not in service(stack, "worker")


def test_in_the_stack_the_runner_is_the_worker(stack: dict[str, Any]) -> None:
    assert service(stack, "api")["environment"]["INDEXING_RUNNER"] == "worker"
    assert "INDEXING_RUNNER" not in service(stack, "worker")["environment"]


def test_every_published_port_binds_through_one_setting(stack: dict[str, Any]) -> None:
    published = [port for name in SERVICES for port in service(stack, name).get("ports", [])]
    assert published, "a stack that publishes nothing would pass every other check here"
    for port in published:
        assert port.startswith("${BIND_ADDRESS:-127.0.0.1}:"), port


def test_the_media_root_and_the_model_cache_are_shared_named_volumes(
    stack: dict[str, Any],
) -> None:
    for name in ("api", "worker"):
        mounted = service(stack, name)["volumes"]
        assert "media:/data/media" in mounted
        assert "models:/data/models" in mounted
    for name in SERVICES:
        for mount in service(stack, name).get("volumes", []):
            source = mount.split(":", 1)[0]
            # A bind mount arrives with the host's ownership, which an
            # unprivileged container cannot write to; a named volume is
            # initialised from the image, ownership included.
            assert not source.startswith(("/", ".", "~")), mount
    assert set(stack["volumes"]) == {"pg_data", "media", "models"}


def test_the_interface_is_told_both_addresses(stack: dict[str, Any]) -> None:
    """One for its own calls inside the stack, one for the browser on the host —
    a browser handed the first renders every picture as a broken image."""
    environment = service(stack, "ui")["environment"]
    assert environment["API_BASE_URL"] == "http://api:8000"
    assert "APP_PORT" in environment["API_PUBLIC_URL"]
    assert "api:8000" not in environment["API_PUBLIC_URL"]


@pytest.mark.parametrize("name", ("api", "worker"))
def test_the_offline_switch_reaches_the_containers_that_load_models(
    stack: dict[str, Any], name: str
) -> None:
    """The how-to says setting it stops them asking the Hub. Nothing of the
    environment file reaches a container unless the compose file names it, so
    that sentence is true only while this passes."""
    assert service(stack, name)["environment"]["HF_HUB_OFFLINE"] == "${HF_HUB_OFFLINE:-}"


def test_the_probe_is_told_where_the_migrations_are(stack: dict[str, Any]) -> None:
    """In an image the package's neighbour is site-packages, where `alembic` is
    the library and not this project's revisions."""
    assert service(stack, "api")["environment"]["ALEMBIC_DIR"] == "/app/alembic"
