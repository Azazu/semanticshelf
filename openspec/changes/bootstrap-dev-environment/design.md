# Design — bootstrap-dev-environment

## Context

See `proposal.md` — Why. Current state: `Makefile`, `docker-compose.yml`, `.env.example` and `ci.yml` came from the scaffold and assume a uv project that does not exist; the CI `python` job self-skips through the `detect` probe on `pyproject.toml`. Constraints: Python 3.12, uv, ruff, mypy strict, pytest (`AGENTS.md` Stack); Python on the host, PostgreSQL in Docker; the host has no Python 3.12 installed (uv downloads it: verified on 2026-09-20, `uv python install 3.12` → 3.12.14); the executor cannot read or write `.env*` files (policy tooling).

## Goals / Non-Goals

**Goals:** a uv project on which `make check` is green and meaningful (one real test, strict mypy, ruff); a Makefile whose application-dependent targets fail loudly-but-green until the scaffold exists; the CI `python` job green on this repository; every check demonstrated with a failing input.

**Non-Goals:** anything under Non-goals in the proposal; performance of the toolchain; a Docker image.

## Decisions

1. **Tooling only, no runtime dependencies.** The dev group holds the four tools of the gate floor; `dependencies = []`. Alternative rejected: adding `fastapi`, `sqlalchemy`, `torch` now "to have the lock ready" — it puts a 200 MB CPU torch download into every CI run of a change that has no code, and the anti-overengineering rule wants each dependency justified by the change that uses it.
2. **The PyTorch CPU index is declared now, the package later.** `[[tool.uv.index]] name = "pytorch-cpu", url = "https://download.pytorch.org/whl/cpu", explicit = true` costs nothing without a package pinned to it; `explicit = true` guarantees no other package is ever resolved from that index. The `[tool.uv.sources] torch = [{ index = "pytorch-cpu" }]` mapping is added together with the dependency in `add-embedder-protocol-and-clip`: whether uv accepts a source for a package that is not a dependency is verified in task 1.2, and if it does the mapping is added here so the later change is a one-line dependency edit.
3. **`hatchling` build backend, package installed editable.** uv treats a project without a build system as virtual (never installed); then `import app` works only through `pythonpath` tricks and `[project.scripts]` (the CLI of change 7, `uv run semanticshelf`) is impossible. hatchling with `packages = ["app"]` is the smallest standard backend. Alternative rejected: `setuptools` (more configuration for the same result).
4. **Makefile guard as a Make-level conditional.** `ifeq ($(wildcard alembic.ini),)` sets `APP_MISSING := 1`; the recipes of `migrate`, `revision`, `run`, `test-integration` are wrapped in `ifdef APP_MISSING … else … endif`, so each recipe is either the single `@echo "[SKIP] no alembic.ini — application not scaffolded yet"` line or the real command, never both. A per-line shell guard with `exit 0` was rejected: Make runs each recipe line in its own shell, so the exit would only end the guard line. `alembic.ini` is the marker because change 2 creates it together with `app/main.py`; `check` is deliberately outside the guard — it is the gate floor and must be real from this change on. The guard is inert by construction the moment `alembic.ini` exists (task 4.2 demonstrates it).
5. **One smoke test instead of tolerating "no tests".** pytest exits 5 when it collects nothing, which would make `make test` red on the empty package. Alternatives rejected: `pytest-custom-exit-code` (a dependency to hide a signal), `|| true` (hides every failure). `tests/unit/test_package.py` asserts `app.__version__ == importlib.metadata.version("semanticshelf")`: it fails when the package is not installed, when the version constant drifts from `pyproject.toml`, and when the tests directory is not on the path — three real regressions.
6. **Ruff rule set literal to `AGENTS.md`**: `select = ["E4", "E7", "E9", "F", "I", "B", "UP"]` (ruff's default set plus isort, bugbear and pyupgrade), `line-length = 100`, `target-version = "py312"`, `known-first-party = ["app"]`. `E501` stays off: the formatter owns line length (`make fmt-check`).
7. **mypy strict on `app/` only** (`[tool.mypy] strict = true, python_version = "3.12", packages = ["app"]`), tests excluded until they exist in volume; `warn_unreachable = true` added because it is free. Specification NFR-QA-1 extends strictness to `ui/` when the UI exists.
8. **pytest**: `testpaths = ["tests"]`, `asyncio_mode = "auto"`, `addopts = "--strict-markers"`, `markers = ["integration: needs the pgvector container"]`; `make test` keeps `-m "not integration"`. `--strict-markers` turns a typo in a marker into a collection error, which is the failing input for the marker registration (task 4.3).
9. **CI unchanged.** The `detect` job already gates the `python` job on `pyproject.toml`; `uv sync --frozen` demands a committed lock (the failing input: a dependency edit without `uv lock`, task 4.4); the integration step turns into the Makefile SKIP. The pushed run on the branch is the acceptance test (D16: the user watches it; the executor lints `ci.yml` with the pinned `actionlint` image beforehand even though the file is not edited, to establish the local floor for future edits).
10. **Python version pinned twice on purpose**: `.python-version` (what uv creates the environment with) and `requires-python >=3.12,<3.13` (what the lock is resolved for). The upper bound keeps the lock and the CI (`setup-uv` with `python-version: "3.12"`) on the same minor; raising it is a reviewed edit.

## Applicability (high tier)

| Question | Applies? | Note |
|---|---|---|
| Crash before/after an external effect | n/a | no runtime effect; every step is a local, re-runnable command |
| Concurrent writers | n/a | no shared mutable state |
| Money rounding | n/a | |
| Empty/zero/null inputs | yes | no `alembic.ini` → the four guarded targets print SKIP and exit 0 (the state until change 2); present → the guard is inert (task 4.2). No tests collected → impossible by construction once the smoke test exists; removing it makes `make test` exit 5 (task 4.1). `.env` missing → `docker compose` fails loudly on `${DB_NAME:?required}`, unchanged from the scaffold |
| Authorization boundary | yes | workflow `permissions: contents: read` retained; no secrets introduced; the PyTorch index is `explicit`, so it can never serve a package that was not pinned to it |
| Deletion/expiry | yes | `.venv/` and the uv cache are disposable; `pg_data` survives `make down`; `docker compose down --volumes` stays a typed-by-hand command (how-to "Reset") |
| Idempotency of retries | yes | `make init`, `uv sync`, `uv lock`, CI re-runs are idempotent |

## Risks / Trade-offs

- [uv rejects a `tool.uv.sources` entry for a package that is not a dependency] → task 1.2 checks; the index alone is declared then and the mapping moves to change 4 (documented in the proposal, decision 2).
- [`uv sync --frozen` in CI fails after a dependency edit without `uv lock`] → the failing input of task 4.4; the how-to already says "run `uv lock` and commit `uv.lock`".
- [First `make init` needs network for the Python 3.12 download and the dev tools] → stated in the how-to; the download is one-time per machine.
- [The executor cannot verify `.env.example` against `docker-compose.yml`] → no variable is added here; the user runs `cp .env.example .env && make up` once (task 5.3) and reports; a mismatch is fixed by the user from a printed diff.
- [GitHub's expression parser is the only oracle for workflow syntax errors] → `ci.yml` is not edited here; the pinned `actionlint` run establishes the local floor anyway.

## Migration Plan

Apply on the branch, `make check` green, push (user), CI green on the exact HEAD, Gate 2, merge. Rollback: revert the merge commit; nothing persistent is created outside `.venv/` and the uv cache.
