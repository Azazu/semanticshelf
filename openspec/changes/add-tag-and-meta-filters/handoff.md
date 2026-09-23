# Handoff — add-tag-and-meta-filters

**Updated:** 2026-09-23 · claude
**State:** proposing
**Branch:** change/add-tag-and-meta-filters

## Done this session

Branch and scaffold only. Scope, from the roadmap and §2.7 of the requirements:
`tags_all`, `tags_any` and `meta.<key>` on **every** search and on the listing,
applied inside the vector query rather than beside it, plus the measurement of
what that costs an approximate index.

Two facts checked against the live database before anything is proposed, so the
proposal argues from them rather than about them:

- **pgvector is 0.8.5** on PostgreSQL 16.14, and the knobs that decide how a
  filtered vector query behaves are there: `hnsw.iterative_scan` (`off` today),
  `hnsw.max_scan_tuples` (20000) and `hnsw.ef_search` (40). This is the
  mechanism the change exists to measure — with `iterative_scan = off`, a
  `WHERE` beside an HNSW scan filters *after* the index has chosen its
  candidates, which is exactly how a narrow filter returns fewer rows than the
  page asked for even though matching assets exist.
- **The search statement already has the shape this needs** (change 8, amended
  by change 11): a window the index answers, a page cut from it, the threshold
  outside, and — since the neighbours endpoint — one predicate above the window.
  Where the filter goes relative to those three layers is the design's central
  question, and the answer decides whether `limit` is honoured.

## Next step

`/opsx:propose add-tag-and-meta-filters`. What the proposal has to settle:

- **Where the filter is applied**, and what that promises. FR-FLT-2 is explicit
  — inside the SQL of the vector query, "not by post-filtering a fixed candidate
  list, so a narrow filter still returns `limit` items when they exist" — which
  with `iterative_scan = off` is not what a `WHERE` next to an HNSW scan does.
  Either the scan becomes iterative, or the promise is weaker than the
  requirement's, and the proposal must say which and why.
- **What the measurement is**, since ADR-002 and change 14 own index tuning:
  this change owes the filtered-query numbers that ADR needs, not a second
  tuning exercise.
- **The tier.** The roadmap says `medium`, and §2.7 is search logic. But a
  filter value is client input that reaches SQL (bound, and `meta` keys are
  pattern-checked), and the change alters the plan of the one query the whole
  service is built around. The proposal re-reads the triggers in `AGENTS.md`
  and declares the tier with its reason; a tier declared too low was a `major`
  finding once already in this project (change 10).
- **The surfaces.** Three searches and the listing, `tags_all`/`tags_any`
  combinable, `meta.<key>` limited to five and keyed by `^[a-z0-9_]{1,64}$`
  (FR-FLT-3), and what the demo interface does with them — the search page's tag
  box is today a filter of what was already fetched, and says so; this change is
  what lets it stop being that.

## Blockers

None.
