# Handoff — add-dinov2-image-search

**Updated:** 2026-09-23 · claude
**State:** awaiting-gate-1
**Branch:** change/add-dinov2-image-search
**Security-sensitive:** yes — a picture arrives in a request body and is
decoded (FR-IMG-1), a second model is downloaded and loaded on first use, and
the API's search surface gains a parameter a client chooses. `AGENTS.md` puts
file uploads and model downloads at `high`; the roadmap already declared it.

## Done this session

Branch, scaffold and all four planning artifacts; Gate 1 round 1 requested and
recorded: **changes-requested**, three `major` findings — all three verified
against the source, all three real, all three now `fixed`.

One decision the user made before anything was written: **the backfill is an
operator command** (`index missing`), not something the service does at start.

Two things checked rather than assumed while writing the artifacts: no
migration is needed for the vectors themselves (the live CHECK already carries
`dinov2-large` at 1024 and both partial HNSW indexes exist, from change 3), and
`embedding-models` needs no delta (its requirements are already written for any
embedder, including "an embedder without a text tower refuses text").

Each of the three findings was verified against the source before being
accepted, and each holds:

1. `indexing_jobs` has **no** unique constraint on `(asset_id, model)` —
   `app/models/indexing_job.py` carries only `ix_jobs_claim` and `ix_jobs_asset`,
   both non-unique. Design decision 6's `ON CONFLICT DO NOTHING` therefore
   guarantees nothing against a concurrent backfill.
2. `EmbeddingRepository.nearest_statement` applies OFFSET inside SQL, so
   dropping the asset in the service after the page was cut shifts every later
   page: for the ranking `[self, A, B, C, D]` with limit 2, page 1 is `[A, B]`
   and page 2 is `[B, C]`. The lookahead row also has to fit inside
   `MAX_SEARCH_EFFORT`, which the deepest accepted page already saturates.
3. FR-IDX-5 makes `POST /assets/{id}/reindex` "the only way a `failed` job runs
   again", and `failed` is terminal, not unfinished — so a backfill that queues
   "assets with no vector and no unfinished work" would queue a fresh job with a
   fresh attempt budget for work that already exhausted its retries.

How each was resolved: (1) `pg_advisory_xact_lock` keyed on the model, plus the
written-out argument that no other writer can race the selection — the
partial-unique-index alternative is recorded as rejected, because `reset()`
would then be unable to reindex an asset carrying two rows for a pair; (2) the
exclusion moved into the statement above the index scan, before the OFFSET, and
the two spent candidates cost one page of depth (998), stated and refused rather
than met by searching shallower; (3) the selection asks for "no work pending,
running or failed", and the command counts what it passed over and names
`reindex`.

## Next step

Gate 1 confirmation of round 1: `/gate-review add-dinov2-image-search 1 confirm 1`.
All three findings are `fixed`; what the confirmation sees is the diff since
`3001527`.

## Blockers

None.
