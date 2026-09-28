# Tasks — stretch-multilingual-queries

## 1. The encoder, as a thing the application knows about

- [x] 1.1 `app/domain.py`: `QUERY_ENCODERS` — encoder key → the storage key
  whose space it answers in — with `mclip-xlmr-l14 → clip-vit-l14`, its
  modality (text only) and its width taken from the storage model's entry
  rather than restated (design decision 1). Verify: unit tests that every
  encoder key is absent from `EMBEDDING_MODELS`, that every target is a key of
  `EMBEDDING_MODELS`, and that an entry pointing at an unknown storage key
  fails the check — demonstrated by adding one.
- [x] 1.2 `app/core/settings.py`: `ENABLED_QUERY_ENCODERS`, empty by default, a
  build that names an unimplemented encoder refuses to start, and an encoder
  whose storage model is not enabled refuses to start naming both (delta spec,
  `embedding-models`). Verify: settings tests for the three cases — accepted,
  unknown key, target not enabled.
- [x] 1.3 `app/ml/mclip.py`: the adapter. **Two pinned revisions** (design
  decision 2 — a branch is mutable, and the numbers must be about the assets a
  deployment loads): the M-CLIP config, checkpoint and tokenizer at
  `40afa80a85e8efa990384a24bbe5a1f6f1cc81b5`, and the
  `xlm-roberta-large` config the architecture is built from (a second
  repository, named by the checkpoint's own config) at
  `c23d21b0620b635a76227c604d44e43a9f0ee389`; the checkpoint read with
  `torch.load(..., weights_only=True)`, the transformer from
  `AutoModel.from_config`, the linear head from `LinearTransformation.*`, mean
  pooling over the attention mask, then the shared normalisation and the
  `ZeroVectorError` guard every embedder uses. It refuses images, like any
  text-only model. Verify: a `models`-suite test (real checkpoint, never in CI)
  asserting width 768, unit norm, a batch keeping its order, and the refusal of
  images; a unit test that every revision the adapter passes is one of those two
  constants and not a branch name; the width check demonstrated by pointing the
  key at a checkpoint of another width and watching the load fail.
- [x] 1.3a A query longer than the encoder's context is cut **and says so**:
  the adapter tokenizes with truncation at the model's maximum and returns one
  `truncated` flag per input, which is what the API answers as
  `query_truncated` (`embedding-models`, "Text longer than the model's context
  is truncated and the caller is told"). Verify: a `models`-suite test with two
  inputs in one batch — an ordinary query whose flag is false and one past the
  context whose flag is true — and an api test through the fake that the flag
  reaches `query_truncated` in the response.
- [x] 1.4 `app/ml/registry.py` and `app/ml/fake.py`: the encoder is loaded
  lazily and cached per process like every model, and the fake stands in for it
  in every test that is not about the weights — a deterministic text-only
  embedder whose vectors live in the fake `clip-vit-l14` space. Verify: unit
  tests that the registry declares exactly the implemented encoders and that
  loading twice returns one object.

## 2. Asking for it

- [x] 2.1 `app/services/search.py` and `app/api/search.py`: `model=` resolves to
  either a storage model or a query encoder; an encoder embeds the query and
  the search ranks the vectors of the space it declares (delta spec,
  `text-search`). A named encoder this build does not run is 503; an encoder
  named on `POST /search/image` or `/assets/{id}/similar` is 422 naming what it
  can take. Verify: api tests with the fake for each path — resolved encoder,
  unknown encoder, encoder asked for a picture query, and the default unchanged
  when nothing is named.
- [x] 2.2 `app/schemas/search.py`: the answer names the pair — the storage model
  whose vectors were ranked and, when it is not that model's own text side, the
  encoder that embedded the query. The OpenAPI example of the text search shows
  both (FR-OPS-4, and the published document carries the example verbatim).
  Verify: api test that the field appears exactly when an encoder was used, and
  `tests/api/test_openapi_examples.py` still passes with the example updated.
- [x] 2.3 Nothing is written under an encoder's name: no queue row, no
  embedding, no appearance in `/stats` or in an asset's `index_status` (delta
  spec, `embedding-models`). Verify: an integration test that runs a search
  through the encoder and asserts the tables and the counts are as they were.

## 3. The measurement that lifts the boundary

- [x] 3.1 `scripts/multilingual_benchmark.py` (design decision 4): the concept
  set chosen by rules that look at no language's results — a tag carried by at
  least 3 and at most 10 assets, at least 20 such concepts, and the English
  baseline itself clearing mean recall@10 of 0.5 — with each concept printed
  beside the number of assets that carry its tag. Per language: mean recall@10,
  the worst concept, and mean agreement@10 with the same concept in English;
  the English CLIP text side as the baseline row; **both** pinned revisions in
  the header; Markdown table on stdout. It reads the store in a **read-only
  transaction** and ranks exactly in memory — it builds nothing, unlike the two
  benchmarks of change 14 whose throwaway schema exists because they do, and
  what it measures is the encoder rather than the index (design decision 4). Verify: the command runs end to end
  against the demo corpus and prints the table; unit tests for the metrics and
  for every selection rule on hand-made input — a tag with too few assets, one
  with too many, a set of fewer than 20 concepts, and a baseline below 0.5 —
  each of which makes the run report that it measured nothing rather than
  publish a number.
- [x] 3.2 Run it for Russian, German, French and Spanish and record the
  numbers. A language is **claimed** only if it clears **both** bounds: mean
  recall@10 at least 0.5 in absolute terms, and at least 0.8 × the English
  baseline's over the same concepts. Agreement@10 and the worst concept are
  published without a bound. Verify: the table is in
  `docs/how-to/benchmarks.md` with the exact command above it, both pinned
  revisions beside it, the per-concept relevant counts included, and every
  language that misses either bound present with its numbers and named as not
  supported.
- [x] 3.3 `docs/adr/ADR-005-multilingual-query-encoder.md`: why a query encoder
  rather than a second model key, **both** repository revisions the measurement
  was taken at, what the numbers decided, and what is left unmeasured. Verify:
  the ADR index (`docs/adr/README.md`) carries its row; the numbers and both
  revisions in it match `docs/how-to/benchmarks.md` exactly.

## 4. Saying what is now true

- [x] 4.1 `docs/how-to/searching.md`: how to ask for the encoder, what the
  answer names, that a `min_score` tuned for one pair does not carry to
  another, and which languages are measured. Verify: every command in the
  section was run in its exact form; the section is re-read whole after the
  last edit.
- [x] 4.2 `docs/how-to/models.md`: the encoder beside the two models — what it
  is, what it costs on disk (2.24 GB), that it is fetched only when enabled,
  **both** pinned revisions and why an encoder is the pair of them (design
  decision 2), that the checkpoint is read with no pickle executed, and the
  licence question stated as open (design decision 5). Verify: re-read whole;
  the warming command appears in the exact form it is run
  (`uv run semanticshelf models warm` on the host, `make stack-warm` in the
  stack), and both were run for this encoder.
- [x] 4.3 `docs/explanation/requirements.md`: FR-TXT-5 amended in place — the
  English-only limit becomes English plus the measured languages, naming this
  change and ADR-005; §7 row 17 and `openspec/ROADMAP.md` carry the tier this
  change declares. Verify: `rg -n "English"` over the repository leaves no
  statement that the service answers English only.
- [x] 4.4 `README.md`: the boundary paragraph reworded to the measured claim,
  with the number beside it and a link rather than a restatement; the commands
  table unchanged. Verify: re-read whole; the claim matches
  `docs/how-to/benchmarks.md`.
- [x] 4.5 `docs/reference/settings.md`: `ENABLED_QUERY_ENCODERS` with its
  default and what it refuses. Verify: every setting the service reads appears
  in the page, checked against `app/core/settings.py`.

## 5. Closing the change

- [x] 5.1 A demonstrated failing input for every new or changed check (high
  tier). Each row is one edit to a real file, the suite that owns the check,
  and the file put back; `git status` was clean afterwards.

  | Planted | What fell over |
  |---|---|
  | an encoder key is also a storage key | 2 failed, 7 passed |
  | an encoder answers in a space nobody declares | 4 failed, 5 passed |
  | the settings stop refusing an encoder this build cannot run | 1 failed, 22 passed |
  | the settings stop refusing an encoder whose space is not enabled | 1 failed, 22 passed |
  | a pinned revision is a branch name again | 1 failed, 22 passed |
  | warming may name an encoder that is not enabled | 2 failed, 21 passed |
  | an unknown encoder is no longer unavailable (the 503) | 2 failed, 4 passed |
  | an encoder claims it can take pictures (the 422) | 2 failed, 4 passed |
  | a search with an encoder ranks its own key instead of its space | 2 failed, 1 passed |
  | the answer stops naming the encoder | 1 failed, 2 passed |
  | the width of a checkpoint is no longer checked | 1 failed, 7 passed |
  | a query past the context is cut silently | 1 failed, 6 passed |
  | recall is always perfect | 2 failed, 13 passed |
  | agreement is always perfect | 2 failed, 13 passed |
  | a concept carried by one asset is asked about | 4 failed, 11 passed |
  | a concept carried by half the corpus is asked about | 1 failed, 14 passed |
  | three concepts are enough to publish a number | 1 failed, 14 passed |
  | a baseline that answers nothing is usable | 1 failed, 14 passed |
  | the relative bound alone decides a language | 4 failed, 11 passed |
  | the encoder's English page is compared with itself | 1 failed, 14 passed |

  Worth recording: the width check was the one row that **did not** fail on the
  first run — removing it changed nothing, because no test pointed the key at a
  checkpoint of another width. `tests/models/test_mclip.py` gained that test
  (from the declaration's side, so it costs no second download), and the row
  above is the re-run.
- [x] 5.2 `openspec validate stretch-multilingual-queries --strict` passes
  ("Change 'stretch-multilingual-queries' is valid") and every task above is
  checked with its evidence.
- [x] 5.3 Run locally everything CI runs, in CI's own form:
  `FORCE_COLOR=1 CI=true make check` (728 unit/api passed),
  `openspec validate --all --strict` (17/17), `sh -n scripts/*.sh` (clean),
  `gate_run_test` (77 passed) and `workflow_verify_test` (23 passed),
  `FORCE_COLOR=1 CI=true make test-integration` with the database up (296
  passed), `make audit` (no known vulnerabilities in 91 packages), and
  `make image` (both images built). The `models` suite is not CI's and was run
  anyway, because this change is the reason it exists: 8 passed against the
  real checkpoint.
- [x] 5.4 Hand over for the push: `handoff.md` at `awaiting-gate-2`, the
  mechanical floor passing, and the branch ready. Verify: `scripts/pregate-verify.sh
  gate2 stretch-multilingual-queries` prints all checks passed, and its output
  is recorded in the handoff.

  The green CI run is not this task's evidence but the **gate's** — the
  Definition of Ready asks for it before Gate 2 is requested, so the request
  waits for the user's push and their report of the run. Between that report
  and the gate reading it, the branch may differ only in `review.md`,
  `handoff.md` and `tasks.md`, which is what `scripts/workflow-verify.sh merge`
  enforces before a merge.
