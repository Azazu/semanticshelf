"""What the images are built from, read from the Dockerfile.

Building an image inside the unit suite would cost a minute a run, so what is
checked here is the instruction rather than the result: the flags that decide
what ends up in the image, and the two that were added because their absence had
already shipped something wrong — a stale wheel, and an interface whose pages
could not import each other. The images themselves are built by CI and by
`make image`, and the stack's smoke runs them.
"""

import re
from pathlib import Path

import pytest

DOCKERFILE = Path(__file__).resolve().parents[2] / "Dockerfile"


@pytest.fixture(scope="module")
def stages() -> dict[str, str]:
    """The Dockerfile split by stage, as `FROM ... AS <name>` divides it."""
    text = DOCKERFILE.read_text(encoding="utf-8")
    found: dict[str, str] = {}
    name = None
    for line in text.splitlines():
        start = re.match(r"^FROM\s+\S+\s+AS\s+(\S+)", line, flags=re.IGNORECASE)
        if start:
            name = start.group(1)
            found[name] = ""
        elif name is not None:
            found[name] += line + "\n"
    return found


def test_every_stage_the_images_are_built_from_is_there(stages: dict[str, str]) -> None:
    assert {"uv", "builder", "ui-builder", "runtime", "ui"} <= set(stages)


def test_the_bases_are_pinned_to_versions(stages: dict[str, str]) -> None:
    """A floating tag makes yesterday's image and today's image two different
    things with one name."""
    text = DOCKERFILE.read_text(encoding="utf-8")
    python_image = re.search(r"ARG PYTHON_IMAGE=(\S+)", text)
    uv_image = re.search(r"ARG UV_IMAGE=(\S+)", text)
    assert python_image and uv_image
    assert re.search(r"python:3\.\d+", python_image.group(1))
    assert ":latest" not in python_image.group(1)
    assert re.search(r":\d+\.\d+\.\d+", uv_image.group(1)), uv_image.group(1)


def test_the_service_environment_is_the_locked_one_without_the_extras(
    stages: dict[str, str],
) -> None:
    sync = [line for line in stages["builder"].splitlines() if "uv sync" in line]
    assert sync, "the builder installs nothing"
    for line in sync:
        assert "--locked" in line, line
        assert "--no-dev" in line, line
    assert "--group ui" not in stages["builder"]


def test_the_project_is_reinstalled_rather_than_taken_from_the_cache(
    stages: dict[str, str],
) -> None:
    """Without this the image ships stale code: uv's cached wheel for this
    project is keyed by a version that does not change when the source does, so
    a rebuild after an edit reinstalled the previous one. Measured in change 15,
    on an image built minutes after the edit it was missing."""
    project_sync = [
        line
        for line in stages["builder"].splitlines()
        if "uv sync" in line and "--no-install-project" not in line
    ]
    assert project_sync, "the builder never installs the project itself"
    assert all("--reinstall-package semanticshelf" in line for line in project_sync)


def test_the_interface_carries_only_its_own_dependencies(stages: dict[str, str]) -> None:
    """`--only-group ui`: no model runtime in the image of a thing that must
    never load a model."""
    sync = [line for line in stages["ui-builder"].splitlines() if "uv sync" in line]
    assert sync
    assert all("--only-group ui" in line and "--no-install-project" in line for line in sync)


def test_the_interface_can_import_its_own_pages(stages: dict[str, str]) -> None:
    """`streamlit run ui/app.py` puts the script's directory on the path and not
    the working directory, so without this every page renders
    "No module named 'ui'" where the corpus should be."""
    assert "PYTHONPATH=/app" in stages["ui"]


@pytest.mark.parametrize("stage", ("runtime", "ui"))
def test_neither_image_runs_as_the_superuser(stages: dict[str, str], stage: str) -> None:
    assert re.search(r"^USER app$", stages[stage], flags=re.MULTILINE), stage


def test_the_service_image_carries_its_migrations(stages: dict[str, str]) -> None:
    """The stack's one-shot `migrate` runs from this image, and the readiness
    probe is pointed at the same directory."""
    assert "alembic.ini" in stages["runtime"]
    assert re.search(r"COPY .*alembic \./alembic", stages["runtime"])


def test_the_volumes_the_stack_mounts_exist_in_the_image_and_belong_to_the_user(
    stages: dict[str, str],
) -> None:
    """A named volume is initialised from the image's own content at that path,
    ownership included — which is what lets an unprivileged process write to it
    on the first start."""
    assert "mkdir -p /data/media /data/models" in stages["runtime"]
    assert "chown -R app:app /data" in stages["runtime"]
