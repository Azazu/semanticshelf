## 1. Project files

- [ ] 1.1 Create `pyproject.toml` (project metadata, `requires-python = ">=3.12,<3.13"`, empty `dependencies`, `dev` group with `ruff`, `mypy`, `pytest`, `pytest-asyncio`, hatchling backend with `packages = ["app"]`, the ruff/mypy/pytest tables of the design, the `pytorch-cpu` explicit index), `.python-version` (`3.12`), `app/__init__.py` (`__version__ = "0.1.0"`), `LICENSE` (MIT, 2026, the author's name). Verify: `uv sync` succeeds, creates `.venv/` on Python 3.12.x (`uv run python -V`), and installs the project editable (`uv run python -c 'import app, importlib.metadata as m; print(app.__version__, m.version("semanticshelf"))'` prints `0.1.0 0.1.0`).
- [ ] 1.2 Decide the torch source mapping: add `[tool.uv.sources] torch = [{ index = "pytorch-cpu" }]` and run `uv lock`; if uv refuses a source for a package that is not a dependency, remove the mapping, keep the index, and record the exact error in the commit body. Verify: `uv lock` exits 0 and `uv.lock` is committed.
- [ ] 1.3 Create `tests/unit/test_package.py` asserting `app.__version__ == importlib.metadata.version("semanticshelf")`. Verify: `make test` collects and passes exactly 1 test.

## 2. Makefile guard

- [ ] 2.1 Add the Make-level conditional to `Makefile` (`ifeq ($(wildcard alembic.ini),)` → `APP_MISSING`; `ifdef APP_MISSING … else … endif` around the recipes of `migrate`, `revision`, `run`, `test-integration`, each SKIP recipe being the single `@echo "[SKIP] no alembic.ini — application not scaffolded yet"` line). Verify: `make migrate`, `make revision MSG=x`, `make run`, `make test-integration` each print the SKIP line and exit 0; `make help` still lists every target.

## 3. Quality floor

- [ ] 3.1 `make check` green on the empty package: `make lint`, `make fmt-check`, `make types`, `make test` each exit 0 individually and `make check` prints `check: all green`. Verify: the four outputs recorded in the commit body.
- [ ] 3.2 Lint the workflow file locally: `docker run --rm -v "$PWD":/repo -w /repo rhysd/actionlint:1.7.12@sha256:b1934ee5f1c509618f2508e6eb47ee0d3520686341fec936f3b79331f9315667 -color` exits 0 (the file is not edited in this change; the run establishes the local floor). Verify: exit code recorded in the commit body.

## 4. Failing inputs (high tier: one per new or changed check)

- [ ] 4.1 Smoke test: with `tests/unit/test_package.py` temporarily moved away, `make test` exits 5 ("no tests collected"); with `app/__init__.py` reading `__version__ = "0.0.0"`, `make test` fails on the assertion. Verify: both outputs recorded in the commit body, files restored, `git status --short` clean afterwards.
- [ ] 4.2 Guard inertness: `touch alembic.ini`, then `make migrate` no longer prints SKIP and fails on the missing `alembic` executable; `rm alembic.ini`. Verify: output recorded in the commit body.
- [ ] 4.3 Strict markers: a temporary test decorated with `@pytest.mark.integratoin` (typo) makes `make test` fail at collection with "'integratoin' not found in `markers` configuration option". Verify: output recorded, file removed.
- [ ] 4.4 Frozen lock: with a temporary extra dev dependency in `pyproject.toml` and no `uv lock`, `uv sync --frozen` (the CI command) fails with the lock mismatch error; revert. Verify: output recorded, `git status --short` clean.
- [ ] 4.5 mypy strict and ruff: a temporary `app/_probe.py` with an unannotated function and an unused import makes `make types` and `make lint` fail; remove it. Verify: both outputs recorded.

## 5. Documentation and acceptance

- [ ] 5.1 Update `docs/how-to/local-development.md` (Python 3.12 downloaded by uv on first `make init`, one-time network need; `cp .env.example .env` before `make up`; the SKIP states of `migrate`, `run`, `test-integration` until change 2; `uv lock` after dependency edits) and `docs/reference/commands.md` (the guarded targets and their SKIP line). Add the licence line to `README.md`. Verify: re-read all three whole; every command in them was run in its exact form during tasks 1–4.
- [ ] 5.2 Sweep sibling artifacts: `rg -n 'no tests|exit code 5|alembic.ini|SKIP' AGENTS.md docs/ openspec/ROADMAP.md` shows only statements consistent with the guard. Verify: output reviewed, discrepancies fixed.
- [ ] 5.3 Acceptance with the database (user action, once): `cp .env.example .env && make init` on the user's machine ends with the SKIP line of `make migrate` after a healthy `db` container (`make ps`). Verify: the user reports the outcome; a `.env.example` mismatch is fixed from a diff the executor prints.
- [ ] 5.4 Acceptance on GitHub (user pushes the branch): the run on `change/bootstrap-dev-environment` shows the `workflow` job green and the `python` job green (unit tests, then SKIP for the integration step). Verify: the user reports the run; its URL goes into `handoff.md`.

## 6. Wrap-up

- [ ] 6.1 Commit per block (`chore(uv):` for 1–2, `test:` for 3–4, `docs:` for 5) without any agent trailer, each body naming the verification outputs. Verify: `git log --format=%B main..HEAD | grep -c '^Co-Authored-By'` prints `0`.
- [ ] 6.2 `openspec validate bootstrap-dev-environment --strict` and `scripts/pregate-verify.sh gate2 bootstrap-dev-environment` pass; request Gate 2 with `/gate-review bootstrap-dev-environment 2`.
