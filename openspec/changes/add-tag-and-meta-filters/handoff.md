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

24 of 28 tasks, committed in six blocks:

- **3.3 / 3.4** the window's extra row against what the answer needs
  (`rows_needed`), and what the bounded question counts — its model, its
  narrowing, the asking asset, and its bound. Two demonstrated failing inputs.
- **3.7 / 4.x** the four surfaces take one narrowing. `meta.<key>` is read from
  the raw query string, and from the raw form fields of the picture search,
  because the framework cannot declare a parameter whose name the caller
  invents; each operation's description carries the convention. The listing
  passes the same filter object as the searches (`app/repositories/narrowing.py`
  is the one definition of what it means in SQL). The envelope carries
  `scan_limited`.
- **5.x** the interface's tag box is the service's own filter now, and the page
  says when the service stopped at its bound.
- **6.1 / 6.1a / 6.2** `scripts/filter_benchmark.py` and
  `docs/how-to/benchmarks.md`.

One deliberate contract change: a bad tag in the **listing's** filter answers
`/errors/invalid-filter`, not `/errors/invalid-tags`. One parser refusing a
narrowing means one type for it on every surface; the tags of an upload or an
edit are the asset's own and still answer `/errors/invalid-tags`.

## Next step

`/opsx:apply add-tag-and-meta-filters` — Gate 1 round 3 **approved** on the
corrected requirement (the narrowing is a condition of the query and an index
can serve it; which path answers is the database's judgement; only the index
path is bounded). Its one `minor` finding is fixed: the design's Risks row no
longer dismisses the very integration test task 3.5 requires.

24 of 28 tasks are done. The rest:

- **6.3 / 6.4** `docs/how-to/searching.md` — how to narrow on all three
  endpoints, what a short page means under a narrowing — and FR-FLT-2 / FR-FLT-3
  in `docs/explanation/requirements.md`, which must read as the service behaves
  (the scan's bound named, the parser's shape as it is).
- **7.1 / 7.2** every suite the way CI runs them (`FORCE_COLOR=1 CI=true`:
  `make check`, `make test-integration`, `make test-ui`, `openspec validate
  --all --strict`, every `scripts/*_test.sh`, `sh -n` over `scripts/*.sh`), and
  a real run against the demo corpus — a narrowed search on each of the three
  endpoints and the narrowed listing — captured into the how-to.

Then the push, CI green on that HEAD, and `/gate-review add-tag-and-meta-filters 2`.

## Blockers

None.
