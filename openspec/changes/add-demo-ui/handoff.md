# Handoff — add-demo-ui

**Updated:** 2026-09-23 · claude
**State:** proposing
**Branch:** change/add-demo-ui

## Done this session

Branch and scaffold only. The roadmap already carried the row (change 10,
tier low): a Streamlit demo — Search, Browse, Upload and Status pages, its own
dependency group, `make ui`.

Everything it needs already exists: `GET /search/text` with scores and a
threshold, the listing with tag and index-status filters, upload, `/tags` and
`/stats`, and a corpus `make demo` produces from nothing.

## Next step

`/opsx:propose add-demo-ui`. What the proposal has to settle before anything is
written:

- the UI is an HTTP client of the API and owns no database session — the
  requirements are explicit (`ui/` talks HTTP only), so nothing in `ui/` may
  import `app.*`, and that wants a test like the one change 9 added for the
  demo module;
- its dependencies are a group of their own, so `make check` and CI do not grow
  Streamlit;
- what the four pages actually promise, which is what the spec delta will say;
- how thumbnails are shown without the UI learning where files live (the API
  serves them by identifier);
- whether anything is tested beyond "the pages render against a running API",
  and how, since Streamlit is awkward to drive headlessly.

Tier is `low` in the roadmap. Worth re-deciding in the proposal rather than
inheriting: the UI takes a query from a person and shows pictures, but it adds
no endpoint, no storage and no egress of its own.

## Blockers

None.
