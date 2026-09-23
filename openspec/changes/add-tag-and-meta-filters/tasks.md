# Tasks — add-tag-and-meta-filters

Tier `medium`: Gate 2 on the code. Every new check below still names the input
that makes it fail when the check is removed, because the failure this change
prevents is silent — a page that is short for the wrong reason looks exactly
like a page that is short for the right one.

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

- [ ] 3.1 A narrowed page that comes back short asks one bounded question —
  do more matching assets exist than this answer holds? — and the envelope says
  whether the search stopped at its bound (design decision 3). Verify: unit
  tests of the decision itself (short page + more exist → limited; short page +
  nothing more → not limited; full page → the question is never asked).
- [ ] 3.2 The field is in the API's answer and in the OpenAPI document, absent
  in substance for an unnarrowed search. Verify: api tests assert it on a
  narrowed and an unnarrowed answer; the document carries it with a description
  and the example shows it.
- [ ] 3.3 Against a real index, a narrowing that outruns the scan's budget is
  reported rather than presented as the end of the ranking. Verify: an
  integration test lowers `hnsw.max_scan_tuples` for its transaction so the
  bound is reached deliberately, and asserts a short page that says it stopped
  early while the store holds more matches. Demonstrated failing input:
  answering `has_more: false` with nothing else makes that test read the answer
  as the end of the ranking.
- [ ] 3.4 The extra question is asked only when it is needed. Verify: an
  integration test counts the statements of a full narrowed page and of an
  unnarrowed page and asserts neither pays for it.

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

- [ ] 6.1 A script builds a synthetic corpus of a given size and selectivity in
  the integration database and measures the same statement the service runs, at
  each setting (design decision 7). Verify: `uv run python scripts/…` prints the
  table, and running it twice on the same seed prints the same rows-returned.
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
