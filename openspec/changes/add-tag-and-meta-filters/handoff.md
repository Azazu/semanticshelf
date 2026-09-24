# Handoff — add-tag-and-meta-filters

**Updated:** 2026-09-24 · claude
**State:** awaiting-gate-1
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

`/gate-review add-tag-and-meta-filters 1` — **a requirement changed, so Gate 1
is reopened** (its last confirmation was on the earlier wording).

The benchmark measured a third plan the earlier hand-run missed: given
statistics, on 3 000 assets, PostgreSQL answers a narrowing of 1 in 5 to 1 in
100 by reading **every** vector of the model and sorting. That is exact,
complete, and at that size the cheapest thing to do — and the delta spec
forbade it. The claim is now what the service can actually promise: the
narrowing is a condition of the query, never a filter over a page already
chosen; an index able to serve it exists; which path answers is the database's
judgement; only the index path is bounded and only it reports stopping. Swept
through design, proposal, tasks, the spec delta and the plan test's docstring.

After the gate: **6.3 / 6.4** (`docs/how-to/searching.md`, FR-FLT-2 and FR-FLT-3
in `docs/explanation/requirements.md`), then **7.1 / 7.2** — every suite the way
CI runs them, and a real run against the demo corpus captured into the how-to.
Then the push, and Gate 2.

## Blockers

None.
