# Tasks — add-tag-and-meta-filters

Tier `high` (raised at Gate 1 round 1, finding 3: this change handles client
input): Gate 1 on the artifacts, Gate 2 on the code, and **a demonstrated
failing input for every new or changed check** — the one below, and every
refusal in group 1. Each commit that touches the parser or the surfaces carries
the security-sensitive flag, and so does `handoff.md`.

The failure this change prevents is silent: a page that is short for the wrong
reason looks exactly like a page that is short for the right one, and a page
that is *full* can be just as wrong.

## 1. What a narrowing is

- [ ] 1.1 `app/domain.py` gains the frozen filter value: the tags all of which
  must be present, the tags any of which suffice, and the metadata equalities
  (design decision 4). It carries no framework and no SQL. Verify: unit tests
  assert that it is frozen, that an empty one is falsy (nothing to apply) and
  that two built from the same input are equal.
- [ ] 1.2 One parser builds it: tags normalised as `app/services/tagging.py`
  normalises them, metadata keys matched against `^[a-z0-9_]{1,64}$`, at most
  five conditions, the same key twice refused. Verify: unit tests for each
  refusal with the message naming the offending value, for normalisation
  (` Dragon ` and `dragon` are one tag), and for the five-condition bound at
  five and at six. Demonstrated failing input: dropping the duplicate-key
  refusal makes a request that can never match look acceptable, which the test
  asserting the 422 catches.

## 2. Inside the vector query

- [ ] 2.1 `EmbeddingRepository.nearest_statement` takes the filter and joins
  `assets` inside the **window**, above nothing and below the page (design
  decision 1). Verify: an integration test reads the plan of the narrowed
  statement and asserts a scan of the model's partial index with no sequential
  scan of `embeddings`; another asserts that the page and the threshold are
  unchanged for an empty filter (the statement is the one change 8 and 11 left).
- [ ] 2.2 The search service sets `hnsw.iterative_scan = strict_order` for a
  narrowed query, beside the effort it already sets, and leaves it off
  otherwise (design decision 2). Verify: an integration test reads
  `current_setting('hnsw.iterative_scan')` from inside the transaction that runs
  the query, for a narrowed and an unnarrowed search.
- [ ] 2.3 A narrowing that matches rarely still fills a page. Verify: the
  integration test that reproduced the defect — 3 000 assets, one in three
  hundred carrying the tag, shuffled so they are not the nearest rows — asserts
  a full page of the nearest matching assets, in distance order. Demonstrated
  failing input: leaving `iterative_scan` off returns an empty page while ten
  matches exist, which is the measurement recorded in `design.md`.
- [ ] 2.4 A narrowing changes which assets are ranked, never their scores.
  Verify: an integration test searches with and without a narrowing and asserts
  that an asset in both answers carries the same score in both.

## 3. What the answer says when the scan stops

- [ ] 3.1 The repository reports how many candidate rows the page produced
  **before** the threshold, and the threshold moves out of the outermost select
  into the service (design decision 3). Verify: an integration test asserts that
  a threshold shortens a page exactly as it did before the move — same items,
  same `has_more` — reusing change 8's own threshold tests unchanged; another
  asserts the candidate count is the pre-threshold number for a page the
  threshold empties. Demonstrated failing input: counting after the threshold
  makes the empty-page-after-threshold test report a stopped scan.
- [ ] 3.2 The decision itself: the search is reported as stopped at its bound
  when the page produced fewer candidates than the answer asked for
  (`limit + 1`, plus one more when an asset excludes itself, beyond `offset`)
  **and** more matching rows exist than `offset + candidates`; otherwise not.
  Verify: unit tests over the decision function for — the page produced
  everything asked (never limited, no question asked); it produced fewer and
  nothing more exists (exhausted); it produced fewer and more exist (limited);
  it produced exactly `limit` while more exist (limited, although the page is
  full). Demonstrated failing input: deciding from the rendered page instead of
  the candidate count makes the fourth case report the end of the ranking —
  the defect Gate 1 named.
- [ ] 3.3 The bounded question is asked with the search's own inputs: its model,
  its narrowing, and the asking asset excluded for `/similar`, bounded by
  `offset + candidates + 1`. Verify: integration tests assert it counts neither
  assets without a vector of that model nor the asking asset, and that a nonzero
  offset compares against the prefix the scan consumed rather than against the
  page. Demonstrated failing input: dropping the model from the question makes
  an asset indexed only by the other model count as reachable.
- [ ] 3.4 Against a real index, a narrowing that outruns the scan's budget is
  reported. Verify: an integration test lowers `hnsw.max_scan_tuples` for its
  transaction so the bound is reached deliberately, and asserts both shapes —
  a short page and a page of exactly `limit` — say that the search stopped
  early while the store holds more matches. Demonstrated failing input: leaving
  the report to `has_more` alone makes both read as the end of the ranking.
- [ ] 3.5 The question is asked only when it is needed. Verify: an integration
  test counts the statements of an unnarrowed page, of a narrowed page that got
  everything it asked for, and of a narrowed page that did not, and asserts only
  the last pays for it.
- [ ] 3.6 The envelope carries the report, and the OpenAPI document describes
  it. Verify: api tests assert it on a narrowed answer that was cut short, on a
  narrowed answer that was not, and on an unnarrowed answer; the document
  carries the field with a description and the example shows it.

## 4. The three searches and the listing

- [ ] 4.1 `GET /api/v1/search/text` and `GET /api/v1/assets/{id}/similar` take
  `tags_all`, `tags_any` and `meta.<key>`; `POST /api/v1/search/image` takes
  them as form fields beside the picture (design decision 5). Verify: api tests
  for each surface — a narrowing that is honoured, one that is refused, and the
  refusal's problem type; the OpenAPI document describes the `meta.<key>`
  convention in each operation.
- [ ] 4.2 An asset may ask for its neighbours under a narrowing it does not
  itself satisfy. Verify: an integration test narrows to a tag the asking asset
  lacks and asserts it is answered, with the asset still absent from its own
  answer.
- [ ] 4.3 `GET /api/v1/assets` gains `meta.<key>`, alongside the tag filters it
  has had since change 5. Verify: an integration test asserts exactly the
  matching assets; an api test asserts the refusals; the plan test asserts the
  metadata index still answers it.
- [ ] 4.4 Every refusal is the problem details this service uses, with a stable
  type. Verify: api tests assert the type and that the detail names the value
  that was wrong, for each of: a tag that is not a tag, a metadata key outside
  the shape, six conditions, a repeated key.

## 5. The interface

- [ ] 5.1 `ui/pages/search.py` sends the tag to the service instead of filtering
  what it fetched, and the page stops saying that the filter applies only to
  what was fetched. Verify: `AppTest` asserts the request carries the tag and
  that the results shown are what the service returned; the wording that
  described the old behaviour is gone from the page and from
  `docs/how-to/demo-ui.md`.
- [ ] 5.2 When the service says it stopped at its bound, the page says so.
  Verify: `AppTest` with a stubbed answer that carries the flag asserts the
  sentence is on the page, and that an ordinary answer does not carry it.
- [ ] 5.3 The interface still imports nothing from the service. Verify: the
  existing layering test covers the changed modules because it walks every file
  under `ui/`.

## 6. The numbers

- [ ] 6.1 `scripts/filter_benchmark.py` builds a synthetic corpus of a given
  size and selectivity in the database `DATABASE_URL` names and measures the
  same statement the service runs, at each setting (design decision 7). Verify:
  `uv run python scripts/filter_benchmark.py --assets 3000 --rare-every 300
  --seed 7` prints the table, and a second run with the same arguments prints
  the same rows-returned. The script empties the tables it uses and says so
  before it starts — on this machine that database is also the one development
  uses.
- [ ] 6.2 `docs/how-to/benchmarks.md` carries that output, the command that
  produced it, and what it means for a deployment — including the cost of an
  iterative scan against a single one, and the bound at which a narrowed search
  gives up. Verify: every command in the page was run in the form shown, and the
  numbers are from that run.
- [ ] 6.3 `docs/how-to/searching.md` gains how to narrow a search on all three
  endpoints, with output from a real run against the demo corpus, and says what
  a short page means when a narrowing is in force.
- [ ] 6.4 `docs/explanation/requirements.md` reads as the implementation
  behaves: FR-FLT-2's promise is the one the service makes (with the scan's
  bound named), FR-FLT-3's shape is what the parser accepts, and the row for
  this change says what it did. Verify: `openspec validate --all --strict`
  passes and the text matches the code.

## 7. Evidence

- [ ] 7.1 `make check`, `make test-integration` and `make test-ui` green the way
  CI runs them (`FORCE_COLOR=1 CI=true`), `openspec validate --all --strict`,
  every `scripts/*_test.sh`, and `sh -n` over `scripts/*.sh`.
- [ ] 7.2 A real run against the demo corpus: a narrowed search on each of the
  three endpoints and the narrowed listing, captured into the how-to.
