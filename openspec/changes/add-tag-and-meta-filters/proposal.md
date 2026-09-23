# Narrowing a search without lying about it

**Risk-Tier:** medium

Ordinary search behaviour, by the table in `AGENTS.md`: no authorization, no
money, no concurrency, no deletion, no migration, no network egress. A filter
value does reach SQL, but as a bound parameter in a containment test — `@>`,
`&&`, `meta @> '{"k":"v"}'` — with the key checked against a pattern before it
is used, which is the same handling the listing has had since change 5.

**The executor asks for Gate 1 anyway**, which the tier does not require. This
change's risk is not in its code but in one design decision — how a filter and
an approximate index scan are made to agree — and a wrong answer there is a
search that quietly returns less than it has. Gate 1 costs one review and is
the cheapest place to be told the answer is wrong.

## Why

Two of the three filters exist on the listing and none of them exist on any
search. The requirements have said what they must do since the brief (FR-FLT-2,
FR-FLT-3), the demo interface has a tag box that is *not* a filter of the
search — it removes rows from what was already fetched, and the `demo-ui`
capability makes it say so out loud — and change 11 left `POST /search/image`
and `/assets/{id}/similar` with no filters either, naming this change as their
owner.

The hard part is the one FR-FLT-2 names: **inside** the vector query, "not by
post-filtering a fixed candidate list, so a narrow filter still returns `limit`
items when they exist". A `WHERE` next to an HNSW scan does not do that by
itself — with `hnsw.iterative_scan = off`, which is what this database has
today, the index chooses its candidates first and the filter then removes some
of them, so a tag that matches one picture in a thousand returns an almost
empty page while the matches sit just past the candidate window. pgvector 0.8
has the mechanism that fixes it, this change is where it is turned on, bounded,
and measured.

## What Changes

- **`tags_all`, `tags_any` and `meta.<key>` on all three searches.**
  `GET /search/text` and `GET /assets/{id}/similar` take them as query
  parameters; `POST /search/image` takes them as form fields beside the picture,
  where its page fields already are. Tags are normalised as FR-TAG-1 normalises
  them; at most five `meta.<key>` filters, keys matching `^[a-z0-9_]{1,64}$`
  (FR-FLT-3); `tags_all` and `tags_any` may be combined.
- **The filter is applied inside the vector query**, as a predicate on the
  joined `assets` row within the scan the index answers — not on the page after
  it was cut. What that costs and what it then promises is design decision 1,
  and the answer is measured rather than assumed.
- **`hnsw.iterative_scan` is set per query**, the way `hnsw.ef_search` already
  is, so that a filtered search keeps looking until it has the page or reaches a
  stated bound. The bound is part of the contract: a page may still come back
  short, and the answer says so rather than implying the store holds nothing
  more.
- **`meta.<key>` on the listing** (`GET /api/v1/assets`), which has had
  `tags_all` and `tags_any` since change 5 and never had this one. The
  repository can already express it; the API cannot.
- **The measurement ADR-002 needs**: what a filter costs an HNSW scan at a few
  selectivities, with the commands and the numbers, recorded where change 14
  will pick them up rather than re-derive them.
- **The demo interface's tag box becomes the service's own filter.** The page
  stops explaining that the filter applies only to what was fetched, because it
  no longer does.

## Non-goals

- **Choosing or tuning the index.** HNSW against IVFFlat, `m`, `ef_construction`
  and the parameters that follow from them are ADR-002 and change 14. This
  change measures what a filter does to the index the service has, and hands
  those numbers over.
- **More kinds of filter.** No ranges, no dates, no negation, no `OR` across
  different fields, no search inside `meta` beyond top-level string equality —
  FR-FLT-3 fixes that shape deliberately, and anything wider is a new proposal
  with its own index question.
- **Moving the threshold into the query.** `min_score` stays outside the page
  (change 8, design decision): it removes results the page already holds rather
  than reaching further down for replacements. A filter is not a threshold, and
  this change does not blur them.
- **A schema change.** `ix_assets_tags` (GIN) and `ix_assets_meta` (GIN,
  `jsonb_path_ops`) have been there since change 3. If the measurement says the
  service wants a different index, that is a finding handed to change 14, not a
  migration written here.
- **Filtering the tag census.** `GET /api/v1/tags` keeps answering for the whole
  store; a census narrowed by a filter is a different question.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `text-search`: what a filter is, that it is applied inside the ranking rather
  than to a page already chosen, what that promises when the filter is narrow,
  and what the answer says when the search reached its bound before it filled
  the page. The rule lives here for the reason change 11 put the model rule
  here: this capability already owns what a page of a ranking is.
- `image-search`: both picture searches take the same filters, by reference to
  the rule above rather than by restating it.
- `asset-api`: the listing also filters by top-level metadata equality.
- `demo-ui`: the search page's tag filter is the service's filter, and the
  caveat that it is not goes away.

## Impact

- New: nothing structural — the filter is a value object shared by the three
  searches and the listing (`app/services/search.py` and the repositories),
  plus a measurement script or how-to page for the numbers.
- Changed: `app/repositories/embeddings.py` (the predicate inside the window and
  the join it needs), `app/services/search.py` (the filter travels with the
  page and the effort), `app/api/search.py` and `app/api/assets.py` (four
  surfaces, and `meta.<key>` parsed from the raw query string because its name
  is not fixed), `app/repositories/assets.py` (the listing's metadata filter),
  `ui/pages/search.py` and `ui/shell.py`, `docs/how-to/searching.md`,
  `docs/how-to/demo-ui.md`, `docs/explanation/requirements.md` where it
  describes what was built.
- Unchanged: the schema and every migration; the queue; the upload path; the
  threshold's place; the depth bounds, unless the measurement says an iterative
  scan makes them mean something different — in which case the design says so
  before any code is written.
- No new dependency: PostgreSQL's own containment operators and a pgvector
  setting the installed 0.8.5 already has.
