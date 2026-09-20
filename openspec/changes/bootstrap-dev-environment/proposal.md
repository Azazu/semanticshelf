# Proposal — bootstrap-dev-environment

**Risk-Tier:** high

Tier rationale: the change makes the CI `python` job run for the first time (`.github/workflows/ci.yml` and the `Makefile` are the "verifier/CI infrastructure" trigger of `AGENTS.md`); the size of the edit does not lower the tier. Matches the specification (§7, change 1) and the roadmap.

## Why

The repository has a process, a specification and a CI workflow, but no Python project: `make check` fails at `uv run ruff` because there is no `pyproject.toml`, and the CI `python` job is skipped by the `detect` probe. Every implementing change from `scaffold-fastapi-app` on needs a green `make check` as its gate floor, so the tooling has to exist and be proven on an empty package first, in a change small enough to review on its own.

## What Changes

1. **uv project.** `pyproject.toml` (name `semanticshelf`, version `0.1.0`, `requires-python >=3.12,<3.13`, no runtime dependencies yet, a `dev` dependency group with `ruff`, `mypy`, `pytest`, `pytest-asyncio`), `.python-version` = `3.12`, `uv.lock` committed, a `hatchling` build backend so the package is installed editable and later changes can declare console scripts (specification §2.8). The PyTorch CPU index is declared now (`[[tool.uv.index]]`, `explicit = true`) so `add-embedder-protocol-and-clip` only adds the dependency; the package itself is not added here.
2. **Tool configuration** in `pyproject.toml`: ruff (line length 100, target py312, default rules + `I`, `B`, `UP`, as `AGENTS.md` fixes), mypy (`strict`, python 3.12, on `app/`), pytest (`testpaths = ["tests"]`, `asyncio_mode = "auto"`, `--strict-markers`, the `integration` marker registered).
3. **Empty package and smoke test.** `app/__init__.py` with `__version__` and `tests/unit/test_package.py` asserting it equals the installed distribution version, so `make test` collects one real test instead of failing with pytest's exit code 5 ("no tests collected").
4. **Makefile guard.** While `alembic.ini` is absent (the application scaffold of change 2 brings Alembic and `app/main.py` together), `make migrate`, `make revision`, `make run` and `make test-integration` print `[SKIP] no alembic.ini — application not scaffolded yet` and exit 0, as a Make-level conditional (`ifeq ($(wildcard alembic.ini),)`), never silently. `make check` (lint, format check, types, unit tests) is real from this change on.
5. **CI.** The `python` job activates by construction once `pyproject.toml` exists; its `make migrate && make test-integration` step becomes the loud SKIP until change 2, so the job is green now and needs no edit for change 2. The workflow file is linted locally with a pinned `actionlint` image before the push.
6. **Licence.** `LICENSE` — MIT, the author's name, 2026 (specification NFR-DOC-4).
7. **Docs.** `docs/how-to/local-development.md` (Python 3.12 is downloaded by uv on first `make init`, the SKIP states until change 2, `cp .env.example .env` before `make up`), `docs/reference/commands.md` (the guarded targets).

## Capabilities

### New Capabilities

None — tooling and infrastructure only; no application behavior. `.openspec.yaml` sets `skip_specs: true`.

### Modified Capabilities

None.

## Non-goals

- No application code beyond the empty package: no FastAPI app, settings, engine, Alembic, `app/main.py` — that is `scaffold-fastapi-app` (change 2). `make init` therefore ends with the SKIP line at `make migrate`, and `make run` prints SKIP, both documented as such.
- No runtime dependency (`fastapi`, `sqlalchemy`, `torch`, …): each arrives with the change that first uses it, per the anti-overengineering rule; only the PyTorch index is declared.
- No `.env.example` edit: this change introduces no setting. The scaffold's file already carries the compose and database variables; new variables arrive with the settings module (change 2). Note for that change: the executor's policy tooling blocks reading and writing `.env*` files, so `.env.example` edits are applied by the user from a diff the executor prints.
- No pre-commit configuration, no Dockerfile, no CI image build, no dependency audit job (change 16), no migration round trip (change 3).
- No change to the `workflow` CI job or to the verifier scripts.

## Impact

- New: `pyproject.toml`, `.python-version`, `uv.lock`, `LICENSE`, `app/__init__.py`, `tests/unit/test_package.py`.
- `Makefile` (guard on `migrate`, `revision`, `run`, `test-integration`; `check` unchanged), `docs/how-to/local-development.md`, `docs/reference/commands.md`, `README.md` (licence line).
- `.github/workflows/ci.yml`: no edit expected; the `python` job activates through the existing `detect` probe. If a run proves an edit necessary it is made in this change (tier already `high`).
- New development dependencies (dev group only, pinned in `uv.lock`): `ruff`, `mypy`, `pytest`, `pytest-asyncio` — the tools `AGENTS.md` names as the gate floor; `hatchling` as the build backend (the smallest PEP 517 backend uv recommends; a backend is required for an installable package with console scripts).
- New developer-side OCI input, pinned by tag and digest: `rhysd/actionlint:1.7.12@sha256:b1934ee5f1c509618f2508e6eb47ee0d3520686341fec936f3b79331f9315667` (digest resolved from Docker Hub on 2026-09-20), used only to lint `ci.yml` locally; not part of any image or job.
