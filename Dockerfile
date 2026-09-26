# syntax=docker/dockerfile:1
#
# Two images from one file: the service (`runtime`) and the demo interface
# (`ui`). They share this file rather than having one each, because two files
# that must stay in step is the defect this repository has already paid for
# twice (a copied test harness in change 13, a copied guard in change 14).
#
# Bases are pinned to a version, never to a floating tag: the Python image the
# environment is built on is the image it runs on, so the virtual environment's
# interpreter is the one that is there, and uv arrives as a binary copied from
# its own published image — the pattern uv's documentation puts first.

ARG PYTHON_IMAGE=python:3.12-slim-trixie
ARG UV_IMAGE=ghcr.io/astral-sh/uv:0.12.19

FROM ${UV_IMAGE} AS uv

# --- the service's environment ---------------------------------------------------

FROM ${PYTHON_IMAGE} AS builder
COPY --from=uv /uv /uvx /bin/

# `UV_COMPILE_BYTECODE`: pay the compilation once here rather than on every
# container's first request. `UV_LINK_MODE=copy`: the cache mount and the
# virtual environment are on different filesystems, where hard links cannot
# reach. `UV_PYTHON_DOWNLOADS=never`: the interpreter is the base image's, and a
# build that silently downloads another one is a build whose image is a guess.
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Dependencies first, from the lock alone: this layer is rebuilt when the lock
# changes and not when the application does. `--locked` fails the build on a
# stale lock, which is `make lock-check` inside the image.
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project --no-dev --no-editable

COPY pyproject.toml uv.lock README.md LICENSE alembic.ini ./
COPY app ./app
COPY alembic ./alembic

# `--no-editable`: the application is installed *into* the environment, so the
# runtime stage needs the environment and no source tree.
#
# `--reinstall-package`: without it this build ships stale code, silently. The
# cache mount above keeps the wheel uv built for this project, and the project's
# version does not change when its source does — so a rebuild after an edit
# reinstalled the *previous* wheel and the image ran code that was no longer in
# the repository. Measured while containerising change 15: a setting added to
# `app/core/settings.py` was missing from an image built after it.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable --reinstall-package semanticshelf

# --- the interface's environment, from the same lock ------------------------------

FROM ${PYTHON_IMAGE} AS ui-builder
COPY --from=uv /uv /uvx /bin/
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never
WORKDIR /app

# `--only-group ui`: the interface's own dependencies and nothing else. It
# imports no module of the service (a unit test proves it), so its image carries
# no model runtime — which also makes "the interface never loads a model" true
# of the image and not only of the code.
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project --only-group ui --no-editable

# --- the service ------------------------------------------------------------------

FROM ${PYTHON_IMAGE} AS runtime

# The paths the stack's volumes are mounted at, created here and owned by the
# user the process runs as: Docker initialises a *named* volume from the image's
# content at that path, ownership included, so an unprivileged process can write
# to it on the first start. (A bind mount arrives with the host's ownership and
# does not work this way; the how-to says so.)
RUN groupadd --system app \
    && useradd --system --gid app --home-dir /app --shell /usr/sbin/nologin app \
    && mkdir -p /data/media /data/models \
    && chown -R app:app /data

WORKDIR /app
COPY --from=builder --chown=app:app /app/.venv /app/.venv
# The migrations travel with the service: the stack's one-shot `migrate` runs
# `alembic upgrade head` from this image, and Alembic reads its configuration
# and its revisions from the working directory, not from the environment.
COPY --from=builder --chown=app:app /app/alembic.ini ./alembic.ini
COPY --from=builder --chown=app:app /app/alembic ./alembic

ENV PATH="/app/.venv/bin:${PATH}" \
    MEDIA_ROOT=/data/media \
    MODEL_CACHE=/data/models \
    PYTHONUNBUFFERED=1

USER app
EXPOSE 8000
CMD ["uvicorn", "--factory", "app.main:create_app", "--host", "0.0.0.0", "--port", "8000"]

# --- the demo interface -----------------------------------------------------------

FROM ${PYTHON_IMAGE} AS ui

RUN groupadd --system app \
    && useradd --system --gid app --home-dir /app --shell /usr/sbin/nologin app

WORKDIR /app
COPY --from=ui-builder --chown=app:app /app/.venv /app/.venv
COPY --chown=app:app ui ./ui

# `PYTHONPATH`: the interface's pages import each other as `ui.client` and
# `ui.shell`, and `streamlit run ui/app.py` puts the *script's* directory on the
# path, not the working directory — so without this the pages render
# "No module named 'ui'" where the corpus should be. On the host `uv run` adds
# the project root and hides the question; in an image nothing does.
ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONPATH=/app \
    PYTHONUNBUFFERED=1

USER app
EXPOSE 8501
CMD ["streamlit", "run", "ui/app.py", \
     "--server.port=8501", "--server.address=0.0.0.0", \
     "--server.headless=true", "--browser.gatherUsageStats=false"]
