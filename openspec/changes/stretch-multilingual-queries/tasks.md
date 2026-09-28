# Tasks — stretch-multilingual-queries

## 1. The encoder, as a thing the application knows about

- [ ] 1.1 `app/domain.py`: `QUERY_ENCODERS` — encoder key → the storage key
  whose space it answers in — with `mclip-xlmr-l14 → clip-vit-l14`, its
  modality (text only) and its width taken from the storage model's entry
  rather than restated (design decision 1). Verify: unit tests that every
  encoder key is absent from `EMBEDDING_MODELS`, that every target is a key of
  `EMBEDDING_MODELS`, and that an entry pointing at an unknown storage key
  fails the check — demonstrated by adding one.
- [ ] 1.2 `app/core/settings.py`: `ENABLED_QUERY_ENCODERS`, empty by default, a
  build that names an unimplemented encoder refuses to start, and an encoder
  whose storage model is not enabled refuses to start naming both (delta spec,
  `embedding-models`). Verify: settings tests for the three cases — accepted,
  unknown key, target not enabled.
- [ ] 1.3 `app/ml/mclip.py`: the adapter. Tokenizer and config from the Hub
  cache, checkpoint from the **main** revision via
  `torch.load(..., weights_only=True)`, transformer from
  `AutoModel.from_config`, the linear head from `LinearTransformation.*`, mean
  pooling over the attention mask, then the shared normalisation and the
  `ZeroVectorError` guard every embedder uses (design decision 2). It refuses
  images, like any text-only model. Verify: a `models`-suite test (real
  checkpoint, never in CI) asserting width 768, unit norm, a batch keeping its
  order, and the refusal of images; the width check demonstrated by pointing
  the key at `xlm-roberta-large` and watching the load fail.
- [ ] 1.4 `app/ml/registry.py` and `app/ml/fake.py`: the encoder is loaded
  lazily and cached per process like every model, and the fake stands in for it
  in every test that is not about the weights — a deterministic text-only
  embedder whose vectors live in the fake `clip-vit-l14` space. Verify: unit
  tests that the registry declares exactly the implemented encoders and that
  loading twice returns one object.

## 2. Asking for it

- [ ] 2.1 `app/services/search.py` and `app/api/search.py`: `model=` resolves to
  either a storage model or a query encoder; an encoder embeds the query and
  the search ranks the vectors of the space it declares (delta spec,
  `text-search`). A named encoder this build does not run is 503; an encoder
  named on `POST /search/image` or `/assets/{id}/similar` is 422 naming what it
  can take. Verify: api tests with the fake for each path — resolved encoder,
  unknown encoder, encoder asked for a picture query, and the default unchanged
  when nothing is named.
- [ ] 2.2 `app/schemas/search.py`: the answer names the pair — the storage model
  whose vectors were ranked and, when it is not that model's own text side, the
  encoder that embedded the query. The OpenAPI example of `/search/text` shows
  both (FR-OPS-4, and the published document carries the example verbatim).
  Verify: api test that the field appears exactly when an encoder was used, and
  `tests/api/test_openapi_examples.py` still passes with the example updated.
- [ ] 2.3 Nothing is written under an encoder's name: no queue row, no
  embedding, no appearance in `/stats` or in an asset's `index_status` (delta
  spec, `embedding-models`). Verify: an integration test that runs a search
  through the encoder and asserts the tables and the counts are as they were.

## 3. The measurement that lifts the boundary

- [ ] 3.1 `scripts/multilingual_benchmark.py` (design decision 4): concepts
  drawn from the corpus's own most frequent tags and printed with the results;
  per language, mean precision@10 by tag and mean agreement@10 with the same
  concept in English; the English CLIP text side as the baseline row; Markdown
  table on stdout. Reuses the benchmark guard of change 14 rather than touching
  the service's tables. Verify: the command runs end to end against the demo
  corpus and prints a table; unit tests for the two metrics on hand-made input,
  including the empty-input and no-tagged-asset cases.
- [ ] 3.2 Run it for Russian, German, French and Spanish over at least 30
  concepts and record the numbers. A language is **claimed** only if its mean
  precision@10 is at least 0.8 × the English baseline's; agreement@10 is
  published without a bound. Verify: the table is in
  `docs/how-to/benchmarks.md` with the exact command above it, and every
  language that misses the bound is in the table with its number and named as
  not supported.
- [ ] 3.3 `docs/adr/ADR-005-multilingual-query-encoder.md`: why a query encoder
  rather than a second model key, what the numbers decided, and what is left
  unmeasured. Verify: the ADR index (`docs/adr/README.md`) carries its row; the
  numbers in it match `docs/how-to/benchmarks.md` exactly.

## 4. Saying what is now true

- [ ] 4.1 `docs/how-to/searching.md`: how to ask for the encoder, what the
  answer names, that a `min_score` tuned for one pair does not carry to
  another, and which languages are measured. Verify: every command in the
  section was run in its exact form; the section is re-read whole after the
  last edit.
- [ ] 4.2 `docs/how-to/models.md`: the encoder beside the two models — what it
  is, what it costs on disk (2.24 GB), that it is fetched only when enabled,
  that the checkpoint is read from the main revision with no pickle executed,
  and the licence question stated as open (design decision 5). Verify: re-read
  whole; `make models warm` documented in the form it is actually run.
- [ ] 4.3 `docs/explanation/requirements.md`: FR-TXT-5 amended in place — the
  English-only limit becomes English plus the measured languages, naming this
  change and ADR-005; §7 row 17 and `openspec/ROADMAP.md` carry the tier this
  change declares. Verify: `rg -n "English"` over the repository leaves no
  statement that the service answers English only.
- [ ] 4.4 `README.md`: the boundary paragraph reworded to the measured claim,
  with the number beside it and a link rather than a restatement; the commands
  table unchanged. Verify: re-read whole; the claim matches
  `docs/how-to/benchmarks.md`.
- [ ] 4.5 `docs/reference/settings.md`: `ENABLED_QUERY_ENCODERS` with its
  default and what it refuses. Verify: every setting the service reads appears
  in the page, checked against `app/core/settings.py`.

## 5. Closing the change

- [ ] 5.1 A demonstrated failing input for every new or changed check (high
  tier): the encoder table's two guards, the two settings refusals, the
  checkpoint width check, the 503 for an unknown encoder, the 422 for a picture
  query, and the two benchmark metrics. Verify: one table, one row per check,
  each a run with that one edit and the file restored afterwards.
- [ ] 5.2 `openspec validate stretch-multilingual-queries --strict` passes and
  every task above is checked with its evidence. Verify: the command's output
  is recorded.
- [ ] 5.3 Run locally everything CI runs, in CI's own form:
  `FORCE_COLOR=1 CI=true make check`, `openspec validate --all --strict`,
  `sh -n scripts/*.sh`, every `scripts/*_test.sh`,
  `FORCE_COLOR=1 CI=true make test-integration` with the database up,
  `make audit`, and `make image`. Verify: each command's result is recorded
  here.
- [ ] 5.4 Hand over for the push with `handoff.md` at `awaiting-gate-2` and
  `scripts/pregate-verify.sh gate2 stretch-multilingual-queries` passing.
  Verify: the verifier's output is recorded in the handoff; the branch is
  pushed and CI is green on it, and anything committed after that green run
  differs only in `review.md`, `handoff.md` and `tasks.md` — the files
  `scripts/workflow-verify.sh merge` allows to differ from a reviewed commit.
