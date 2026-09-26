# Design — harden-quality-and-docs

## Context

See `proposal.md` — Why. What shapes the approach:

- `README.md` is 34 lines and says the project is "scaffolded". `docs/` has the
  four Diátaxis quadrants (tutorials empty), nine how-to pages, three reference
  pages, the requirements and the ADR log; `docs/README.md` indexes them and is
  three pages out of date.
- `docs/images/` holds `search.png`, `browse.png` and `status.png`, captured by
  `scripts/screenshots.py` with Playwright against a running service. The
  interface has five pages: Search, Find similar, Browse, Upload, Status.
- Three narrow layering tests exist — `test_layering_demo.py` (nothing the
  service loads reaches the demo-dataset module), `test_repositories_layering.py`
  (no repository returns an ORM class), `test_import_discipline.py` (no module
  imports the model runtime at import time, and none imports a measurement
  command). NFR-QA-2's general dependency rule is the one that is missing.
- `uv audit` exists in the pinned uv, reads `uv.lock`, takes `--locked`, and
  currently reports "no known vulnerabilities and no adverse project statuses in
  91 packages". It is experimental and says so unless the preview feature is
  named.
- Measured today: 16 operations, 5 with an example. Every one already has a
  summary and a description.
- The demo corpus in the development database was truncated by integration runs,
  so screenshots need `make demo` first.

## Goals / Non-Goals

**Goals**

- A README that a stranger can read in three minutes and come away knowing what
  the project does, what it looks like, how to run it and what it deliberately
  does not do.
- Rules that were prose becoming checks: the layering rule, the audit, the
  examples.
- Nothing invented to fill a section. Every number in the README comes from a
  measurement already in the repository.

**Non-Goals** (beyond the proposal's)

- No restructuring of `docs/`. The quadrants and the routing rule stay; what
  changes is that the index stops lying and one promised page arrives.
- No new documentation system, no site generator, no badges that check nothing.

## Decisions

### 1. The diagram is Mermaid in the README, not an image

GitHub renders Mermaid, and a diagram that is text can be edited by the next
person, reviewed in a diff, and corrected when the design moves. An exported PNG
is a screenshot of a decision nobody can revise. Three flows, one diagram: the
request path (client → API → pgvector), the job path (upload → queue → worker →
vectors) and storage (media root, model cache, database).

*Alternative considered:* a drawn image under `docs/images/`. Rejected for the
reason above; screenshots are images because they are of something that is
itself an image, a diagram is not.

### 2. Screenshots are captured, not composed

`scripts/screenshots.py` already drives a headless browser against the running
service and the running interface; it grows the two pages it does not visit yet
(Find similar, Upload). The corpus is rebuilt with `make demo` first, so what
the README shows is the demo dataset anybody can reproduce, and the run is
recorded in the change's commit body.

*The Upload page needs care*: it is a form, and a screenshot of a form is only
useful once it says what it accepts. The capture fills the fields before
shooting rather than showing an empty page.

### 3. The layering test is one table of forbidden edges

A single test module reads the import graph of `app/` — every `import` and
`from ... import`, inside functions as well as at module level, since an import
in a function is exactly how an unwanted dependency arrives — and checks a table:

| From | May not reach | Why |
|---|---|---|
| `app.api` | `sqlalchemy`, `app.db` | a router that writes SQL is a router that owns a schema |
| `app.api` | `app.ml` | model calls belong to the services and the pool, never to a request handler |
| `app.ml` | `app.db`, `app.repositories` | the model layer knows nothing about storage |
| `app.repositories` | `app.schemas`, `app.api` | repositories return domain objects, never the API's own shapes |
| `app.services` | `app.api` | a service that imports a router has the arrow backwards |
| `app.domain` | everything but the standard library | it is the vocabulary every layer may depend on |

Each row gets a **planted violation**: the import is added, the test is run, the
failure is recorded, the import is removed. A rule nobody has seen fail is a
rule nobody knows works — this repository has learned that twice.

*Refined while implementing, by reading the graph before asserting it.* The
first row as written above would have failed on the code as it stands, and
rightly: `app/api/assets.py` and `app/api/health.py` import `AsyncSession` and
`AsyncEngine` to annotate what they are handed, and `app/api/deps.py` imports
`app.db.engine` because wiring a session to a router is its whole job. Neither
is SQL in a router. So the rule is two rules: **no module of `app.api` may reach
`app.db`, except `app.api.deps`, named with its reason**; and **what `app.api`
may take out of SQLAlchemy is a name allowlist** — `AsyncSession`, `AsyncEngine`
and the factory the wiring module builds sessions with. A router that cannot
name `select` or `text` cannot build a query, which is "routers contain no SQL"
as something a check can answer.

*Alternative considered:* a third-party import-linter with its own contract
file. Rejected: another dependency and another configuration language for a
table that fits in one screen, in a project whose anti-overengineering rule asks
what an existing tool cannot cover.

### 4. The audit is `uv audit --locked`, in CI and in `make`

It reads the lock file the image installs from — which is the whole point:
auditing a fresh resolution of the declared ranges answers a question about
versions nobody ships. `--locked` also makes a stale lock a failure rather than
a silent re-resolution.

It is **experimental** in the pinned uv, which is a fact to state rather than
hide: the command is invoked with its preview feature named, so the run is
explicit about what it is using, and the day the flag changes the failure is a
build error rather than a silently skipped check. If it ever disappears,
NFR-SEC-6's other half (`pip-audit`) is the fallback and that is a change, not a
scramble.

*Where it runs:* its own step in the existing `python` job rather than a job of
its own — it needs the same checkout and the same uv, and a separate job would
pay for both again to run a command that takes a second.

*Unlike the image scan* (change 15, deliberately outside CI), this one is
**in** CI because NFR-SEC-6 says so, and because a Python advisory with a fix is
something this repository can act on the same day: bump the lock. A base-image
CVE is somebody else's release schedule.

### 5. Examples live beside the schema they illustrate, and are validated by it

The three that exist (`SEARCH_PAGE_EXAMPLE`, `STATS_EXAMPLE`,
`TAG_LIST_EXAMPLE`) are constants in the schema modules, referenced from the
route decorators and validated in the test by the model they belong to. The
eight that are missing follow that pattern exactly, and the test stops naming a
list of operations it knows about: it reads the OpenAPI document, takes every
operation, and requires an example unless the operation is in a short table of
exemptions with a reason attached.

That inversion is the point. The old test could pass while an operation was
added with no example; the new one fails until the table says why.

**The exemptions**, and there are exactly three: `DELETE /assets/{id}` answers
204 with no body; `/assets/{id}/file` and `/assets/{id}/thumbnail` answer with
image bytes. What those two promise instead is their headers, which the how-to
documents and the API tests assert.

### 6. The README states the boundaries as boundaries

Three of them, because a reader who finds them later feels misled: there is **no
authentication** (D12/NFR-SEC-7) and what that means for where the service may
be exposed; the model runs on **CPU** and the latencies are what CPU latencies
are (text ≤ 300 ms, a query image ≤ 3 s after warm-up, NFR-PERF-2); CLIP's text
tower is **English** and other languages degrade toward a random ranking, which
is why a picture query exists.

## Risks / Trade-offs

- **A README that ages** → it links rather than restates: the numbers it quotes
  are in `benchmarks.md` and ADR-002, the commands in `reference/commands.md`,
  the requirements in the specification. What it repeats is what a reader needs
  before clicking anything.
- **Screenshots go stale the moment the interface changes** → they are produced
  by a command in the repository (`make screenshots`), so refreshing them is a
  command rather than a project, and the change records the corpus they were
  taken from.
- **An experimental audit command** → named as experimental in the workflow and
  in the how-to, with the fallback written down (decision 4).
- **The audit may go red on an advisory this change did not cause** → that is
  what it is for; the fix is a lock bump, and the how-to says so. It is also why
  the audit fails only on advisories **with a fix available**: an unfixable one
  is a decision, not a build error.
- **The layering table could be too strict and block legitimate work** → each
  row is a rule the repository already follows, verified before it is asserted;
  a rule that turns out to be wrong is one line to change, with the reason in
  the commit body.

## Migration Plan

Nothing to migrate: no schema, no setting, no endpoint. The only thing a reader
of the repository will notice is that the README now describes the project.

## Open Questions

None that change the specs, the approach or the tasks. The tier is the one
judgement call, and the proposal states both sides rather than hiding it.
