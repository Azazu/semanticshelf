# Tasks — add-dinov2-image-search

Tier `high`: every new check below names the input that makes it fail when the
check is removed, and that failure is demonstrated before the task is ticked.

## 1. The second model

- [ ] 1.1 `app/ml/dinov2.py`: the adapter behind the `Embedder` protocol —
  `facebook/dinov2-large` from `DINOV2_MODEL_NAME`, the CLS token after the
  final layer norm, batches of `EMBED_BATCH_SIZE`, `TextNotSupportedError` from
  `embed_text`. Read the installed `transformers` for which attribute carries
  that token rather than assuming it. Verify: `tests/models/test_dinov2.py`
  (marked `models`, never in CI) loads the real checkpoint once and asserts the
  width is 1024, the vectors are unit length, and two renderings of the same
  picture land nearer each other than either does to a different picture.
- [x] 1.2 The key joins `IMPLEMENTED_MODELS` and the registry's factories, and
  the existing test that holds those two sets together keeps passing. Verify:
  that test names both keys; `GET /ready` reports `models: ok` against the live
  schema, whose constraint already declares 1024 for this key.
- [x] 1.3 `app/domain.py` says what each model can be asked — text, pictures, or
  both — in one table. Verify: unit tests assert CLIP takes both and DINOv2
  takes only pictures, and that every implemented key appears in the table
  (so a third model cannot be added without answering the question).
  Demonstrated failing input: removing a key from the table fails that test.
- [x] 1.4 `DINOV2_MODEL_NAME` in settings and in `docs/reference/settings.md`,
  beside `CLIP_MODEL_NAME`. Verify: a unit test reads it from the environment
  and asserts the default.

## 2. Asking with a picture

- [ ] 2.1 `app/services/search.py` gains `search_image`: the query vector comes
  from a picture, everything after it is the path `search_text` already takes —
  the same effort, the same page, the same threshold, the same envelope.
  Verify: integration tests with the planar fake embedder assert the ordering,
  the threshold and `has_more` for a picture query, reusing the ranking fixture
  change 8 wrote.
- [ ] 2.2 The picture is decoded under the upload rules and never stored: a
  temporary file outside the media root, `images.inspect`, and an unlink in a
  `finally` (design decision 3). Verify: an api test asserts the refusals an
  upload gives (undecodable, unsupported format, too large, too small) and an
  integration test asserts that after a search no asset exists and the media
  root is unchanged. Demonstrated failing input: writing the temporary file
  under the media root makes the "nothing is left" test fail.
- [ ] 2.3 `POST /api/v1/search/image` in the API: multipart `file` plus the page
  fields as form fields, the envelope of `/search/text`, and the body bound the
  upload path already enforces. Verify: api tests for the shape, for each
  refusal, and for the same page bounds as the text endpoint; the OpenAPI
  document carries the operation with a summary, a description and an example,
  and its 503 and 422 responses.

## 3. Asking with an asset

- [ ] 3.1 `EmbeddingRepository` can read one asset's vector for a model, and
  `search_similar` uses it as the query with no inference at all. Verify: an
  integration test asserts the neighbours of a known asset, and that no model
  was loaded to answer (the registry is asserted empty afterwards).
- [ ] 3.2 The asset is never among its own neighbours, on any page, and the
  pages are pages of the ranking it has already been taken out of:
  `nearest_statement` takes the asset to exclude, the window (the index scan)
  stays unfiltered and takes one row more than the page reaches, and the select
  above it drops the asset before it orders, offsets and cuts (design decision
  5). Verify: integration tests read consecutive pages of a ranking whose
  nearest row is the asset itself and assert that each neighbour appears on
  exactly one page, in order, with every page but the last full; the existing
  plan test covers the excluding statement and still reads an index scan on the
  model's partial index. Demonstrated failing input: dropping the asset in the
  service after the page was cut makes the second page repeat the last
  neighbour of the first — the defect Gate 1 round 1 named.
- [ ] 3.3 A search that excludes an asset reaches one page-depth less, and says
  so rather than searching shallower than the page needs: `check_depth` and
  `effort_for` account for the excluded row, the bound is `MAX_SEARCH_EFFORT -
  2`, and a page beyond it is refused with the problem details a too-deep page
  already gets. Verify: unit tests assert that the effort granted to an
  excluding search always covers the page, the excluded row and the row beyond
  the page, and that the two bounds (998 excluding, 999 not) are each accepted
  at their edge and refused one past it; api tests assert the refusal on
  `/similar`. Demonstrated failing input: leaving the excluding bound at 999
  makes the effort test fail, because 1001 candidates would be needed and the
  index grants 1000.
- [ ] 3.4 The deepest page `/similar` accepts is answered from the whole of it,
  and not one candidate short — arithmetic about the effort is not evidence that
  the statement asks for it. Verify: an integration test asks for
  `limit + offset = 998` against a corpus built with the fake embedder and
  asserts the items of that page and `has_more` twice — once over a corpus that
  holds a further neighbour, where it must be true, and once over a corpus whose
  last neighbour is the page's last item, where it must be false — and asserts
  that `limit + offset = 999` is refused. Demonstrated failing input: taking one
  candidate fewer into the window (the row the exclusion pays for) makes the
  first case report that nothing follows while a neighbour does, which is the
  way a granted effort of 1000 and a fetch of 999 would look from outside.
- [ ] 3.5 `GET /api/v1/assets/{id}/similar`: 409 problem details when the asset
  has no vector for the search model, 404 when no asset carries that
  identifier, and the ordinary envelope otherwise. Verify: api and integration
  tests for all three, including an asset whose work exists but has not finished.
  Demonstrated failing input: answering an empty page instead of 409 makes the
  test that distinguishes "nothing is known" from "nothing is like it" fail.

## 4. Choosing the model

- [ ] 4.1 All three searches take `model`, defaulting to the model that kind of
  query is answered by today. A key this build does not run answers 503 naming
  it; a key that cannot take that kind of query answers 422 naming what it can
  take (design decision 2). Verify: api tests for every combination — text with
  CLIP, text with DINOv2 (422), a picture with DINOv2, a picture with CLIP,
  either with a key that does not exist (503) — asserting the problem type each
  time. Demonstrated failing input: removing the modality check lets a text
  query reach an image-only model and fail deeper, with a different problem.
- [ ] 4.2 The answer always names the model that ranked it, and the query is
  embedded by that same model. Verify: an integration test with vectors of both
  models over the same assets asserts that a search of one never returns a
  result ranked by the other's vectors.

## 5. Work for what is already stored

- [ ] 5.1 `IndexingJobRepository` can queue the missing work for a model in one
  statement, under `pg_advisory_xact_lock` keyed on the model: assets that have,
  for it, neither a vector nor work that is pending, running **or failed**
  (design decision 6). It answers with what it queued and how many assets it
  passed over because their work had failed. Verify: integration tests assert
  what is queued for a store holding all four kinds of asset — vector, work
  waiting, work failed, nothing — and that running it twice queues nothing the
  second time. Demonstrated failing input: treating `failed` as work that is
  simply not unfinished queues a fresh job with a fresh attempt budget for it,
  which contradicts FR-IDX-5 and fails the test that asserts the failed asset is
  passed over and counted.
- [ ] 5.2 Two backfills of the same model cannot queue the same work twice.
  Verify: an integration test runs the statement in two overlapping
  transactions on real PostgreSQL and asserts that each asset ends with exactly
  one new unit of work, and that the second transaction reports nothing queued.
  Demonstrated failing input: removing the advisory lock makes that test find
  two jobs per asset — the queue has no unique constraint on the pair to catch
  it, which is what Gate 1 round 1 found.
- [ ] 5.3 `semanticshelf index missing [--model KEY] [--no-index]` queues that
  work and then carries it out, reporting what it did — the shape
  `index-folder` reports, plus the assets passed over for failed work and the
  command that runs them again (`POST /assets/{id}/reindex`). Verify: a CLI test
  with the fake embedder asserts the summary, including the skipped count and
  the hint, and that `--no-index` leaves the work queued.
- [ ] 5.4 Nothing queues work by itself: not at start, not in the lifespan, not
  in a background task. Verify: a test asserts that building the application and
  running its lifespan against a store with missing vectors creates no work.
  Demonstrated failing input: queueing in the lifespan makes it fail.
- [ ] 5.5 `make demo` ends with `index missing`, so the demo corpus is
  searchable by both kinds of query. Verify: `make -n demo` shows the three
  commands in order.

## 6. The fifth page

- [ ] 6.1 `ui/pages/similar.py`: a picture to upload, or an asset reached from
  the "similar" action, with the grid, scores, model and paging the search page
  has, and the service's own refusal for a 409 or a 422. Verify: `AppTest`
  covers a picture search, an asset search, a 409 and a refused picture, all
  against the stubbed service, asserting what is rendered after one click.
- [ ] 6.2 The "similar" action appears under every thumbnail the interface
  shows, and opens that asset's neighbours. Verify: `AppTest` asserts the action
  on the search and browse grids, and that clicking it asks the service for that
  asset's neighbours.
- [ ] 6.3 The interface still imports nothing from the service. Verify: the
  existing layering test covers the new module because it walks every file under
  `ui/`.

## 7. Documentation

- [ ] 7.1 `docs/how-to/searching.md` gains both new ways to ask, with output
  from a real run, and says plainly what each model is for: words find what a
  picture is *about*, a picture finds what *looks like* it. It also says that a
  score from one model means nothing against a score from the other, and that
  `/similar` needs that asset's vector to exist.
- [ ] 7.2 `docs/reference/demo-dataset.md` and `docs/how-to/demo-ui.md` mention
  that the demo now ends with `index missing`, and what the fifth page does.
  Verify: every command in both was run in the form shown.
- [ ] 7.3 `docs/explanation/requirements.md`: FR-IMG-2's tag filters are not
  delivered here (change 12 owns filters); its 409 is owed to the absence of a
  vector rather than to a job that is not `done`, the same correction change 8
  made to FR-TXT-3 for the same reason (a reindex puts the work back while the
  vector stays); the searchable depth of a self-excluding search is one page
  shallower; and the row for this change says what it did. Verify: the text
  reads as the implementation behaves, and `openspec validate --all --strict`
  passes.

## 8. Evidence

- [ ] 8.1 A real run: `make demo` on a clean store, then a picture search and a
  `/similar` against the corpus with the real weights, captured into the how-to.
  Verify: the captured output is from that run, and `make test-models` asserts
  1024 on the real checkpoint.
- [ ] 8.2 `make check`, `make test-integration` and `make test-ui` green the way
  CI runs them (`FORCE_COLOR=1 CI=true`), `openspec validate --all --strict`,
  every `scripts/*_test.sh`, and `sh -n` over `scripts/*.sh`.
