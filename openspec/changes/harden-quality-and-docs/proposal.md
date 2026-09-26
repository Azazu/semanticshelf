# Proposal — harden-quality-and-docs

**Risk-Tier:** medium

The roadmap says `low`, and for four fifths of this change that is right: it is
documentation, screenshots and an index. Two pieces are not documentation. A
**dependency audit in CI** can turn any later change red the day an advisory
lands, and a **layering test** is a new rule the repository will be held to.
Neither touches the service, so `high` — which AGENTS.md reserves for verifier
and CI infrastructure — feels heavier than this deserves; but the argument for
it is real and a reviewer who disagrees should say so, as three reviewers have
already done in this project. Gate 2 reads the diff.

## Why

This is the last change of the plan, and it is the one a stranger meets first.
Today `README.md` is 34 lines that say the project is **"scaffolded"** — written
when it was — and point at a quick start with no picture of what the thing does,
no diagram, no numbers and no security note. Everything else exists: a service
that searches by words and by pictures, a worker, a measured index, a container
stack. The README describes none of it.

Three promises of the specification are also still open, and they are open in
the parts a reader checks when deciding whether a repository is serious:

- **NFR-DOC-1** — the README: screenshots, an architecture diagram, the quick
  start, the `make` targets, the security boundary (NFR-SEC-7), the CPU latency
  expectations, the English-query limit, "what this shows", and links to the
  ADRs and the benchmarks.
- **NFR-QA-2** — a dependency-rule test over the import graph that **fails on a
  planted violation**: routers hold no SQL and call no model, `app/ml/` does not
  reach `app/db/`, repositories do not return the API's own schemas.
- **NFR-SEC-6** — CI audits the locked dependencies and fails on known
  advisories with a fix. `uv audit` exists in the pinned uv, so this needs no
  new dependency at all.

And **FR-OPS-4**: every operation carries a summary, a description and an
example. Measured today — 16 operations, 5 with an example, 11 without.

## What Changes

- **A README that shows the project.** What it is in two sentences, the five
  screenshots, an architecture diagram (the request path, the job path, the
  storage) as Mermaid so it is text in the repository rather than an image
  nobody can edit, both quick starts (`make stack` in containers, `make init`
  on the host), the `make` surface, "what this shows" as the list of mechanisms
  a reader might be looking for, the security boundary stated as a boundary, the
  CPU latencies (text ≤ 300 ms, a query image ≤ 3 s, nobody should expect GPU
  numbers), the English-query limit of CLIP, and links to the ADRs, the
  benchmarks and the specification.
- **Five screenshots, not three.** `docs/images/` has Search, Browse and Status
  from change 10; the interface has had a fifth page since change 11 and an
  Upload page all along. `scripts/screenshots.py` captures what the README
  shows, and the corpus it captures is rebuilt with `make demo` first.
- **An architecture page** in the explanation quadrant, which the documentation
  index has been promising since the first implementing change. The diagram's
  long form: what happens on an upload, where the vectors come from, who talks
  to whom, and what is deliberately not there.
- **The documentation index refreshed.** It is missing three pages that exist
  (`how-to/demo-ui.md`, `how-to/running-the-stack.md`,
  `reference/demo-dataset.md`) and still promises the architecture page as
  future work.
- **The dependency-rule test NFR-QA-2 asks for.** One table of forbidden edges
  read out of the import graph, and a planted violation for each rule showing
  the test failing — the repository has three narrower layering tests already
  (the service never reaches the demo-dataset module, repositories return no ORM
  class, nothing imports the measurement commands); this is the general one.
- **`uv audit` in CI and in `make`.** The locked dependencies audited on every
  push, failing on known advisories; `make audit` is the same check by hand.
  Today it reports no vulnerabilities in 91 packages, which is the number this
  change starts from.
- **The OpenAPI examples FR-OPS-4 owes.** Eight operations gain an example
  validated by the model it illustrates; three are exempt for a stated reason
  (a 204 has no body, and `/file` and `/thumbnail` answer with image bytes),
  and the exemption is in the test rather than in somebody's memory.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `http-api-conventions`: the OpenAPI requirement today asks every operation for
  a summary and a description. It gains the example FR-OPS-4 always meant —
  with the honest carve-out for operations that answer with no body or with
  bytes, and the rule that an example must parse as the thing it illustrates.
- `deployment`: one added requirement beside the image scan — the dependencies
  the build resolves are audited against the lock by CI, and a known
  vulnerability with a fix available fails that run.

## Impact

- **New:** `docs/explanation/architecture.md`, `tests/unit/test_layering.py`,
  two screenshots under `docs/images/`, examples in the schema modules of the
  operations that lack them, a `make audit` target and an audit job in CI.
- **Changed:** `README.md` (rewritten), `docs/README.md` (the index),
  `scripts/screenshots.py` (five pages), `tests/api/test_openapi_examples.py`
  (every operation, with the exemptions named), `.github/workflows/ci.yml`,
  `Makefile`, and `openspec/ROADMAP.md` / `docs/explanation/requirements.md`
  where this change's row or tier moves.
- **Unchanged:** every behaviour of the service. The only Python that changes is
  the addition of example constants to schema modules and the test files; no
  endpoint, no query, no setting.
- **Dependencies:** none added. `uv audit` ships with the uv this repository
  already pins in CI; the screenshots use the `screenshots` group that exists.

## Non-goals

- **Tutorials.** The Diátaxis quadrant stays empty and the index keeps saying so
  deliberately: a tutorial is a promise to walk somebody through an outcome, and
  the how-to pages already do that for every outcome this project has.
- **A written domain model page.** `docs/explanation/requirements.md` §3 is the
  data model and it is normative; a second description of it would be the
  duplication this repository's documentation rule exists to prevent.
- **Changing what CI already runs.** The audit is added beside the existing
  jobs; nothing about the gate floor, the workflow verifier or the image build
  moves.
- **Publishing anything.** No registry, no package index, no release tag — the
  image scan of change 15 and the audit here both report and neither ships.
- **Fixing an advisory that does not exist yet.** The audit is wired and the
  current run is clean; a future finding is a future change.
