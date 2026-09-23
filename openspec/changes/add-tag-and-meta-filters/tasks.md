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

- [x] 1.1 `app/domain.py` gains the frozen filter value: the tags all of which
  must be present, the tags any of which suffice, and the metadata equalities
  (design decision 4). It carries no framework and no SQL. Verify: unit tests
  assert that it is frozen, that an empty one is falsy (nothing to apply) and
  that two built from the same input are equal.
- [x] 1.2 One parser builds it: tags normalised as `app/services/tagging.py`
  normalises them, metadata keys matched against `^[a-z0-9_]{1,64}$`, at most
  five conditions, the same key twice refused. Verify: unit tests for each
  refusal with the message naming the offending value, for normalisation
  (` Dragon ` and `dragon` are one tag), and for the five-condition bound at
  five and at six. Demonstrated failing input: dropping the duplicate-key
  refusal makes a request that can never match look acceptable, which the test
  asserting the 422 catches.

## 2. Inside the vector query

- [x] 2.1 `EmbeddingRepository.nearest_statement` takes the filter and joins
  `assets` inside the **window**, above nothing and below the page (design
  decision 1). Verify: an integration test reads the plan of the narrowed
  statement and asserts **no sequential scan of `embeddings`** — which of the two
  plans the database picks is its own judgement (`design.md`, Context), and a
  test that demanded one of them would forbid the other; that the vector index
  is still available and correct under a narrowing is task 3.5's regression.
- [x] 2.2 The search service sets `hnsw.iterative_scan = strict_order` for a
  narrowed query, beside the effort it already sets, and leaves it off
  otherwise (design decision 2). Verify: an integration test reads
  `current_setting('hnsw.iterative_scan')` from inside the transaction that runs
  the query, for a narrowed and an unnarrowed search.
- [x] 2.3 A narrowing that matches rarely still fills a page — whichever plan
  answers it. Verify: an integration test over 3 000 assets, one in three
  hundred carrying the tag, shuffled so they are not the nearest rows, asserts a
  full page of the nearest matching assets in distance order. Demonstrated
  failing input: with `iterative_scan` left off, that page comes back **empty**
  — which holds while the fixture's statistics are as a freshly written table
  leaves them, because that is what keeps the query on the index path this
  change is about (`design.md`, Context).
- [x] 2.4 A narrowing changes which assets are ranked, never their scores.
  Verify: an integration test searches with and without a narrowing and asserts
  that an asset in both answers carries the same score in both.

## 3. What the answer says when the scan stops

The four numbers of design decision 3 — window reach, candidates, reached,
needed — are the vocabulary of this group. None of these tasks may decide
anything from the shape of the answer, and none of them may assume which of the
two plans answered the query.

- [x] 3.1 The repository returns the candidates in order — after the exclusion,
  **before** the offset and **before** the threshold — up to the window reach,
  and the service applies the offset and the threshold over them. Verify: change
  8's own threshold tests and change 11's own paging tests pass unchanged
  against the same fixtures (same items, same `has_more`, same order); an
  integration test asserts `reached` is the pre-offset, pre-threshold count for
  a page the threshold empties **and** for a page the offset empties.
  Demonstrated failing input: counting after the offset makes the second of
  those report an exhausted ranking for a scan that stopped early.
- [x] 3.2 The decision: cut short when `reached < needed` and more matching rows
  exist than `reached`, where `needed = offset + limit + 1`. Verify: unit tests
  over the decision function, one per row of design decision 3's worked table —
  25 reached at offset 0 (complete, nothing asked); exactly 20 with more in the
  store (cut short, although the page is full); exactly 20 with 20 in the store
  (complete); 10 reached at offset 50 with 40 in the store (cut short); the
  threshold keeping none of 25 (complete); an asset's own search with 21
  neighbours after the exclusion (complete, nothing asked). Demonstrated failing
  input: comparing against `offset + reached` instead of `reached` turns the
  fourth row into "exhausted" — the defect confirmation 1 named.
- [ ] 3.3 The window asks for `offset + limit + 1 + excluding` rows, and the
  page needs `offset + limit + 1` of them: the exclusion's extra row belongs to
  the window and never to what the answer requires. Verify: a unit test asserts
  both numbers for an ordinary search and for an asset's own search; an
  integration test asserts that an asset's search with exactly `limit + 1`
  neighbours after the exclusion asks no bounded question — both when the asset
  itself satisfies the narrowing and when it does not. Demonstrated failing
  input: requiring one more usable row makes every such search pay for the
  question.
- [ ] 3.4 The bounded question carries the search's own model, its narrowing and
  the asking asset, and stops at `reached + 1`. Verify: integration tests assert
  it counts neither an asset without a vector of that model nor the asking
  asset. Demonstrated failing input: dropping the model makes an asset indexed
  only by the other model count as reachable.
- [x] 3.5 The whole positive path, against a real index and without touching the
  planner's statistics: the index path reached deliberately (`enable_sort = off`
  — a narrowing broad enough to get it naturally turns out to be satisfied by
  the first iteration of the scan, measured), a budget lowered so the scan
  cannot reach what the page needs, and matching assets left over. Verify: an
  integration test asserts the plan uses the model's vector index, that the
  answer is a **full** page, and that `scan_limited` is true — the candidates,
  the bounded question and the flag, wired together — paired with the same query
  at the default budget, which must be false. Demonstrated failing inputs: never
  asking the bounded question, and asking it with `needed` in place of
  `reached`, each of which makes this test fail while every unit test still
  passes.
- [x] 3.5a The negative cases, over a store the search can exhaust: a full page,
  a short page, an empty page at an offset, and a page the threshold empties.
  Verify: an integration test asserts `scan_limited` is false for each, because
  in each the scan reached what the answer needed or the store held no more.
- [x] 3.6 The question is asked only when it is needed. Verify: an integration
  test counts the statements of an unnarrowed page, of a narrowed page that
  reached what it needed, and of a narrowed page that did not, and asserts only
  the last pays for it.
- [ ] 3.7 The envelope carries the report, and the OpenAPI document describes
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

- [ ] 6.1 `scripts/filter_benchmark.py` builds its corpus **in a schema of its
  own**, which it creates and drops: it never writes to, and never deletes from,
  the tables the service uses, so the published command is safe to run against a
  working store (design decision 7). It measures, per selectivity, which plan
  answered, how many rows came back against how many were asked for, and how
  long it took — at `iterative_scan` off and `strict_order`, with statistics
  fresh and without them. Verify: `uv run python scripts/filter_benchmark.py
  --assets 3000 --seed 7` prints the table, and a second run with the same
  arguments prints the same plans and rows.
- [ ] 6.1a The published command cannot empty a store. Verify: an integration
  test seeds assets, embeddings and jobs, runs the benchmark's entry point with
  its default arguments, and asserts every row is still there and the schema it
  used is gone. Demonstrated failing input: pointing the script at the service's
  own tables makes that test fail with the store emptied — which is exactly what
  happened to this machine's demo corpus while this change was being measured.
- [ ] 6.2 `docs/how-to/benchmarks.md` carries that output, the command that
  produced it, and what it means for a deployment: where the planner changes its
  mind, what each plan costs, what an iterative scan buys on the path that uses
  the index, and what stale statistics do to all of it. Verify: every command in
  the page was run in the form shown, and the numbers are from that run.
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
