# Tasks — harden-quality-and-docs

## 1. The rules that were prose

- [x] 1.1 Write `tests/unit/test_layering.py`: the import graph of `app/` read
  whole (module level **and** inside functions), checked against the table of
  forbidden edges in design decision 3 — routers reach no SQL and no model
  layer, `app.ml` reaches no storage, repositories reach no API schema, services
  reach no router, `app.domain` reaches nothing but the standard library.
  Verify: the suite passes on the repository as it stands, and the test names
  the offending module and the import it found when it fails.
- [x] 1.2 A planted violation for **every** row of that table: add the import,
  run the test, record the failure, remove it. Each case appends one import to a
  real module — an import at the end of a file is as legal as one at the top,
  and the test reads them wherever they are. The results are one table for the
  whole change, in §6.5, so that the nine layering plants and the checks added
  at Gate 2 cannot drift apart from each other. Verify: every file restored
  afterwards (`git status` clean of them). Two further guards of the test
  itself: the walker is checked against a sample with an import inside a
  function — in both import forms — and every rule is checked to be about
  modules that exist, since a rule over a layer nobody wrote passes without
  looking at code.
- [ ] 1.3 `make audit` runs `uv audit --locked` with its preview feature named,
  and the existing CI `python` job runs the same command (design decision 4).
  Verify: `make audit` passes locally and its output is recorded (done: no known
  vulnerabilities in 91 packages); `make help` and `docs/reference/commands.md`
  list it (done); the workflow parses and the step is green on the commit Gate 2
  reviews — **open**: green on `bc06c2b`, whose step is identical but for its
  comment, and this branch has moved since. Closes when the user pushes this
  head and reports the run.
- [x] 1.4 The audit fails when there is something to fail on. Verified against a
  throwaway project in the scratchpad (never this repository's lock) pinned to
  `requests==2.19.1`: the same command exits **1** and names what it found —
  `idna 2.7 has 4 known vulnerabilities`, each with its advisory and the release
  it was fixed in. On this repository's own lock it reports no known
  vulnerabilities in 91 packages.

## 2. The examples the API owes

- [x] 2.1 Add an example to each operation that answers with a body and has
  none: `GET /health`, `GET /ready`, `POST /api/v1/assets`, `GET /api/v1/assets`,
  `GET /api/v1/assets/{id}`, `PATCH /api/v1/assets/{id}`,
  `GET /api/v1/assets/{id}/jobs`, `POST /api/v1/assets/{id}/reindex` — as
  constants beside the schema they illustrate, referenced from the route
  (design decision 5). Verify: the OpenAPI document carries each one.
- [x] 2.2 Invert `tests/api/test_openapi_examples.py`: it reads every operation
  out of the document and requires an example unless the operation is in a
  table of exemptions with a reason — 204 with no body, and the two that answer
  with image bytes. Demonstrated by breaking it seven ways, recorded with every
  other plant of this change in §6.5. Verify: every file restored afterwards.
  Worth recording: the first attempt at
  the last two put `"finished-ish"` in a job's `status`, and **nothing failed** —
  that field is a plain `str` in the schema, so the model accepts it. The
  validation catches what the model constrains and no more, which is the honest
  scope of "the example parses as the answer it illustrates".
- [x] 2.3 Every example parses as the answer it illustrates, by the model the
  service answers with. Verify: the test validates each example through its
  model; an example with a wrong field fails it (demonstrated on one).

## 3. What the project looks like

- [x] 3.1 Rebuild the demo corpus (`make demo`) — the development database was
  truncated by integration runs — and extend `scripts/screenshots.py` to the two
  pages it does not visit (Find similar, Upload), filling the Upload form before
  it shoots (design decision 2). Verify: `make screenshots` produces five files
  under `docs/images/`, and each is of the page it is named after.
- [x] 3.1a Choose what the front page shows: `scripts/screenshot_corpus.py`
  copies the slice of the demo corpus worth showing into `.data/demo-shopfront`,
  which is imported with `index-folder` and searched for `people playing tennis
  on a sunny court` (design decision 2). Record the recipe in
  `docs/how-to/demo-ui.md`, whose screenshot section still described three pages
  and named Find similar and Upload as deliberately absent. Verify: the five
  files were re-captured from that corpus and each was looked at; the how-to's
  commands were run in the exact form it prints.
- [x] 3.2 Rewrite `README.md` (NFR-DOC-1): what it is, the five screenshots, the
  Mermaid architecture diagram (request path, job path, storage), both quick
  starts (`make stack` and the host), the `make` surface, "what this shows", the
  three boundaries of design decision 6 (no authentication, CPU latencies, the
  English-query limit), and links to the ADRs, the benchmarks and the
  specification. Verify: re-read whole after the last edit; every command in it
  was run in its exact form; the Mermaid block renders — the user reported it
  does on the pushed page (`bc06c2b`), and `README.md` has not changed since, so
  that evidence still stands.
- [x] 3.3 Write `docs/explanation/architecture.md` — the diagram's long form:
  the request path, the job path, what each process owns, what is deliberately
  absent (no broker, no second store, no authentication) — citing the ADRs
  rather than restating them. Verify: re-read whole; `rg` finds no claim it
  duplicates from the requirements.
- [x] 3.4 Refresh `docs/README.md`: the three pages it does not list
  (`docs/how-to/demo-ui.md`, `docs/how-to/running-the-stack.md`,
  `docs/reference/demo-dataset.md`), the architecture page, and the benchmarks entry
  which still describes only its first half. Verify: every file under `docs/` is
  either listed or deliberately not (tutorials), checked by `ls` against the
  index.

## 4. Reconciling what this change touches

- [x] 4.1 The ADR index is complete and current. Verify: every file matching
  `docs/adr/ADR-*.md` has a row in `docs/adr/README.md` and every row points at
  a file that exists.
- [x] 4.2 Sweep for claims this change makes wrong: `rg -n "scaffolded|Stage:"`
  across the repository, and the README's own links. Verified: the only
  surviving mentions are the Makefile's `[SKIP] no alembic.ini — application not
  scaffolded yet` guard and its description in `docs/reference/commands.md`, which
  describe a mechanism rather than the project's stage and are still accurate;
  no document calls the project a scaffold any more. Every link in `README.md`
  and in `docs/explanation/architecture.md` resolves (checked by walking them);
  the documentation index lists every file under `docs/` and lists nothing that
  is not there.
- [x] 4.3 `openspec/ROADMAP.md` and `docs/explanation/requirements.md` §7 row 16
  carry the tier this change declares and the scope it actually has. Verify:
  both re-read whole.

## 5. Closing the change

- [ ] 5.1 `openspec validate harden-quality-and-docs --strict` passes (done,
  and re-run after every edit since) and every task above is checked with its
  evidence. **Open** while 1.3 and 5.3 wait for the CI run on the head Gate 2
  reviews: a task that says every task above it is checked cannot itself be
  checked before they are. It closes with them.
- [x] 5.2 Run locally everything CI runs, in CI's own form:
  `FORCE_COLOR=1 CI=true make check`, `openspec validate --all --strict`,
  `sh -n scripts/*.sh`, every `scripts/*_test.sh`,
  `FORCE_COLOR=1 CI=true make test-integration` with the database up,
  `make audit`, and `make image`. Verify (re-run after the Gate 2 fixes, which
  touched application code): 690 unit/api passed, 293 integration passed,
  validation 17/17, `sh -n` clean, `workflow_verify_test` 23 passed,
  `gate_run_test` 77 passed, the audit reporting no known vulnerabilities in 91
  packages, and both images built.
- [ ] 5.3 Hand over for the push with `handoff.md` at `awaiting-gate-2` and
  `scripts/pregate-verify.sh gate2 harden-quality-and-docs` passing. Verify: the
  verifier's output is recorded in the handoff; the gate follows the user's push
  and a green CI run on that exact head. **Open** until that run exists: the
  branch moved under both review rounds, so the evidence from the earlier push
  is not evidence about this head.

## 6. Gate 2 round 1 — four majors, all accepted

- [x] 6.1 Finding 1: the tier. A mandatory audit step added to CI is the
  "verifier/CI infrastructure" AGENTS.md assigns to `high`, whatever share of
  the change is documentation. Raised to `high` in `proposal.md`, in
  `openspec/ROADMAP.md` row 16 and in `docs/explanation/requirements.md` §7 row
  16; `design.md` gained the applicability table the tier requires; §6.5 below
  is the demonstrated failing input per check. Verify: `rg -n "medium"` over the
  change's artifacts and the two registers finds no surviving claim of the old
  tier; Gate 1 runs on these artifacts before Gate 2 is confirmed.
- [x] 6.2 Finding 2: the published example for `GET /assets/{id}/jobs` was
  missing `lease_expires_at` and `last_error` — FastAPI encodes the finished
  document with `exclude_none` (the closing `jsonable_encoder` of its own
  `get_openapi`), which eats nulls **inside** an example while the schema
  beside it still requires the field. `app/core/openapi.py` now writes every
  declared example back into the finished document, walking the routers FastAPI
  0.141 keeps as wrappers rather than flattening; the test validates the
  example **the document publishes** through its model, and the null-stripping
  helper it used to compensate with is gone. Verify: in the served OpenAPI
  document the jobs example carries both nulls and `IndexingJobList.model_validate`
  accepts it; two planted breakages in §6.5.
- [x] 6.3 Finding 3: the router SQL guard read only `from sqlalchemy import …`,
  so `import sqlalchemy as sa` and `sa.select(...)` passed it. The form itself
  is now refused — no allowlist can cover a whole-package import — by
  `packages_imported_whole()` and `test_no_router_takes_sqlalchemy_whole`, with
  the walker's self-test extended to both forms. Verify: two planted imports in
  §6.5, one aliased and one of a submodule.
- [x] 6.4 Finding 4: the audit policy said three different things. `uv audit`
  has neither a severity filter nor a fix-availability one, so the rule is the
  command's own — **any** known advisory fails the run — and the escape for an
  advisory nobody can act on yet is `--ignore-until-fixed <ID>` on the `make
  audit` line, where a reviewer sees it. Reconciled in
  `docs/explanation/requirements.md` (NFR-SEC-6, keeping `pip-audit` as the
  fallback it always named), the `deployment` delta spec and its scenario, the
  `Makefile` comment, the CI step's comment, `design.md` decision 4 and its
  risk row, and `proposal.md` in both places. The same sweep found `make audit`
  documented nowhere: `docs/reference/commands.md` was missing it and the six
  container targets change 15 added, and now lists all seven. Verify:
  `rg -n "with a fix|HIGH/CRITICAL"` outside the image scan finds only the new
  wording; `make help` and the reference table name the same targets.
- [x] 6.5 A demonstrated failing input for every check this change adds or
  changes, each run by planting the violation, running the suite and putting the
  file back:

  | Planted | What fell over |
  |---|---|
  | `app.api` imports `app.db.engine` | 1 failed, 9 passed |
  | `app.api` imports `app.ml.registry` | 1 failed, 9 passed |
  | `app.ml` imports `app.repositories.assets` | 1 failed, 9 passed |
  | `app.repositories` imports `app.schemas.assets` | 1 failed, 9 passed |
  | `app.services` imports `app.api.deps` | 1 failed, 9 passed |
  | `app.domain` imports `fastapi` | 1 failed, 9 passed |
  | a router takes `select` out of SQLAlchemy | 1 failed, 9 passed |
  | a router takes SQLAlchemy whole (`import sqlalchemy as sa`) | 1 failed, 9 passed |
  | a router takes a submodule whole (`import sqlalchemy.orm`) | 1 failed, 9 passed |
  | an operation loses its example | 3 failed, 18 passed |
  | an exemption is deleted while its operation still has no example | 1 failed, 20 passed |
  | an exemption outlives its operation | 2 failed, 19 passed |
  | an example carries a count that is not one | 1 failed, 20 passed |
  | an example carries a timestamp that is not one | 2 failed, 19 passed |
  | the document correction is removed (`exclude_none` eats the nulls) | 2 failed, 19 passed |
  | the walker stops descending into included routers | 2 failed, 19 passed |
  | `uv audit --locked` against a lock holding `requests==2.19.1` | exit 1, four advisories named (`idna 2.7`) |

  Verify: every row is one run with that one edit, and the working tree is
  identical afterwards (`git status --short` clean).

## 7. Gate 1 round 1 — two majors, both accepted

- [x] 7.1 Finding 1: the proposal said the service's behaviour was unchanged and
  that the only Python touched was example constants and tests, while the change
  also rewrites the **published** OpenAPI document (`app/core/openapi.py`, its
  installation in `app/main.py`). Scope and mechanism are now stated where a
  reviewer meets them: `proposal.md` gained a "Changed in the application" entry
  and a narrower "Unchanged" claim (no endpoint, no query, no setting, no
  response body), `design.md` decision 5 gained the paragraph on how an example
  reaches the document and why the correction exists, and the Migration Plan
  says what a reader will notice. Verify: both documents re-read whole; the
  delta spec's guarantee and the mechanism now name each other.
- [x] 7.2 Finding 2: three tasks were checked on evidence that does not exist
  yet. 1.3 and 5.3 are open again — they close on a green CI run for the head
  Gate 2 reviews, and the branch has moved under two review rounds since the
  last green one. 3.2 stays checked with its evidence named: the user reported
  the diagram renders on the pushed page (`bc06c2b`) and `README.md` has not
  changed since. Verify: every unchecked task names what closes it, and nothing
  checked claims evidence that does not exist — see 7.3, which is the same rule
  applied once more.
- [x] 7.3 Confirmation 2 found the rule's last hiding place: 5.1 claimed
  "every task above is checked" while 1.3 and 5.3 were open. It is open too now,
  and closes with them. The same pass removed two records that had started to
  drift: §1.2 and §2.2 each carried their own copy of a plant table with the
  counts of the day they were run, and both now point at §6.5, the one table
  that covers every check this change adds. §5.2's numbers were re-measured
  after the Gate 2 fixes touched application code (690 unit/api, 293
  integration, both images rebuilt). Verify: the user arbitrated this third
  confirmation, as AGENTS.md requires after two failed ones; `rg -n "passed"`
  over `tasks.md` finds counts only in §5.2 and §6.5.
