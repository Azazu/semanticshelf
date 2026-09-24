# Handoff — add-tag-and-meta-filters

**Updated:** 2026-09-24 · claude
**State:** implementing
**Branch:** change/add-tag-and-meta-filters
**Security-sensitive:** yes — this change handles client input: a shared
parser for tag and metadata narrowings on four public surfaces, including the
multipart picture search, with parameters whose names the caller invents.
§Security-Sensitive Code of `AGENTS.md` puts that at `high`, which is why the
tier was raised at Gate 1 round 1.

## Done this session

**All 28 tasks are done.** Since the Gate 1 round 3 approval:

- **6.3** `docs/how-to/searching.md` — a "Narrow it" section captured against
  the demo corpus on a running service: the same query with and without a tag,
  `tags_any`, `meta.<key>` on the text and picture searches, an asset asking
  under a tag it does not carry, the narrowed listing, a narrowing nothing
  satisfies, the four refusals, and what a short narrowed page means.
- **6.4** `docs/explanation/requirements.md` — FR-FLT-2 rewritten to the
  measurement, FR-FLT-3 to the parser and its one refusal type, **FR-FLT-6**
  added for `scan_limited`, the envelope and parameter requirements updated, and
  the change table's row 12 at the tier this change became. `ROADMAP.md` too.
- **7.1** every suite the way CI runs them: `make check` 545, integration 257,
  ui 59, `openspec validate --all --strict` 16, both `scripts/*_test.sh`, `sh -n`
  over `scripts/*.sh`. `scripts/pregate-verify.sh gate2` passes.
- **7.2** the run behind the how-to: 20 demo assets, both models `done`, service
  on `APP_PORT=8010` (8000 is taken on this machine).

Earlier in the change: the parser and the filter value, the narrowing inside the
vector query with `iterative_scan`, the four numbers of the scan's report, the
four surfaces, the interface, and the benchmark.

**A note on the local store:** the integration suite truncates `assets`, and
this machine uses one database for development and for that suite, so the demo
corpus was rebuilt afterwards (`storage prune --apply`, then `demo-dataset
index --into .data/demo`, no download): 20 assets, both models `done`.

## Next step

Push `change/add-tag-and-meta-filters` and watch CI. On green:
`/gate-review add-tag-and-meta-filters 2`.

Gate 2 reads the whole code diff. What is worth knowing before it:

- One deliberate contract change: a bad tag in the **listing's** filter answers
  `/errors/invalid-filter`, not `/errors/invalid-tags`. One parser refusing a
  narrowing means one type for it on every surface; the tags of an upload or an
  edit are the asset's own and still answer `/errors/invalid-tags`.
- Gate 1 was reopened once during the apply, because the benchmark measured a
  third plan — a read of every vector, exact and cheapest at small scale — that
  the spec had forbidden. Round 3 approved the corrected wording.
- Every new check has a demonstrated failing input, run and restored: the
  duplicate-key refusal, the counting of candidates before the offset, the
  decision function's comparison, the bounded question's model, the window's
  extra row, the wiring of `scan_limited`, and a benchmark that writes where the
  service's rows are.

## Blockers

None.
