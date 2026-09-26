# Tasks — harden-quality-and-docs

## 1. The rules that were prose

- [ ] 1.1 Write `tests/unit/test_layering.py`: the import graph of `app/` read
  whole (module level **and** inside functions), checked against the table of
  forbidden edges in design decision 3 — routers reach no SQL and no model
  layer, `app.ml` reaches no storage, repositories reach no API schema, services
  reach no router, `app.domain` reaches nothing but the standard library.
  Verify: the suite passes on the repository as it stands, and the test names
  the offending module and the import it found when it fails.
- [ ] 1.2 A planted violation for **every** row of that table: add the import,
  run the test, record the failure, remove it. Verify: a table in this file with
  one row per rule, each from one run; `git status` clean afterwards.
- [ ] 1.3 `make audit` runs `uv audit --locked` with its preview feature named,
  and the existing CI `python` job runs the same command (design decision 4).
  Verify: `make audit` passes locally and its output is recorded (today: no
  known vulnerabilities in 91 packages); `make help` lists it; the workflow
  parses and the user's push shows the step green.
- [ ] 1.4 The audit fails when there is something to fail on. Verify: run it
  against a lock file holding a package with a known fixable advisory — a
  throwaway project in the scratchpad, never this repository's lock — and record
  that it exits non-zero naming the package.

## 2. The examples the API owes

- [ ] 2.1 Add an example to each operation that answers with a body and has
  none: `GET /health`, `GET /ready`, `POST /api/v1/assets`, `GET /api/v1/assets`,
  `GET /api/v1/assets/{id}`, `PATCH /api/v1/assets/{id}`,
  `GET /api/v1/assets/{id}/jobs`, `POST /api/v1/assets/{id}/reindex` — as
  constants beside the schema they illustrate, referenced from the route
  (design decision 5). Verify: the OpenAPI document carries each one.
- [ ] 2.2 Invert `tests/api/test_openapi_examples.py`: it reads every operation
  out of the document and requires an example unless the operation is in a
  table of exemptions with a reason — 204 with no body, and the two that answer
  with image bytes. Verify: the test fails when an example is removed from any
  operation, and fails when an operation is added without one (demonstrated by
  deleting an exemption row).
- [ ] 2.3 Every example parses as the answer it illustrates, by the model the
  service answers with. Verify: the test validates each example through its
  model; an example with a wrong field fails it (demonstrated on one).

## 3. What the project looks like

- [ ] 3.1 Rebuild the demo corpus (`make demo`) — the development database was
  truncated by integration runs — and extend `scripts/screenshots.py` to the two
  pages it does not visit (Find similar, Upload), filling the Upload form before
  it shoots (design decision 2). Verify: `make screenshots` produces five files
  under `docs/images/`, and each is of the page it is named after.
- [ ] 3.2 Rewrite `README.md` (NFR-DOC-1): what it is, the five screenshots, the
  Mermaid architecture diagram (request path, job path, storage), both quick
  starts (`make stack` and the host), the `make` surface, "what this shows", the
  three boundaries of design decision 6 (no authentication, CPU latencies, the
  English-query limit), and links to the ADRs, the benchmarks and the
  specification. Verify: re-read whole after the last edit; every command in it
  was run in its exact form; the Mermaid block renders (checked in the GitHub
  preview by the user, who reports back).
- [ ] 3.3 Write `docs/explanation/architecture.md` — the diagram's long form:
  the request path, the job path, what each process owns, what is deliberately
  absent (no broker, no second store, no authentication) — citing the ADRs
  rather than restating them. Verify: re-read whole; `rg` finds no claim it
  duplicates from the requirements.
- [ ] 3.4 Refresh `docs/README.md`: the three pages it does not list
  (`how-to/demo-ui.md`, `how-to/running-the-stack.md`,
  `reference/demo-dataset.md`), the architecture page, and the benchmarks entry
  which still describes only its first half. Verify: every file under `docs/` is
  either listed or deliberately not (tutorials), checked by `ls` against the
  index.

## 4. Reconciling what this change touches

- [ ] 4.1 The ADR index is complete and current. Verify: every file matching
  `docs/adr/ADR-*.md` has a row in `docs/adr/README.md` and every row points at
  a file that exists.
- [ ] 4.2 Sweep for claims this change makes wrong: `rg -n "scaffolded|Stage:"`
  across the repository, and the README's own links. Verify: no document still
  describes the project as a scaffold; every link in the README resolves.
- [ ] 4.3 `openspec/ROADMAP.md` and `docs/explanation/requirements.md` §7 row 16
  carry the tier this change declares and the scope it actually has. Verify:
  both re-read whole.

## 5. Closing the change

- [ ] 5.1 `openspec validate harden-quality-and-docs --strict` passes and every
  task above is checked with its evidence. Verify: the command's output is
  recorded.
- [ ] 5.2 Run locally everything CI runs, in CI's own form:
  `FORCE_COLOR=1 CI=true make check`, `openspec validate --all --strict`,
  `sh -n scripts/*.sh`, every `scripts/*_test.sh`,
  `FORCE_COLOR=1 CI=true make test-integration` with the database up,
  `make audit`, and `make image`. Verify: all green before the branch is offered
  for a push.
- [ ] 5.3 Hand over for the push with `handoff.md` at `awaiting-gate-2` and
  `scripts/pregate-verify.sh gate2 harden-quality-and-docs` passing. Verify: the
  verifier's output is recorded in the handoff; the gate follows the user's push
  and a green CI run on that exact HEAD.
