# Handoff — add-dinov2-image-search

**Updated:** 2026-09-23 · claude
**State:** archived
**Branch:** change/add-dinov2-image-search
**Security-sensitive:** yes — a picture arrives in a request body and is decoded
(FR-IMG-1), and a second model is downloaded from the model hub on first use.
The query picture goes to a temporary file outside the media root, through the
same inspection an upload passes, and is unlinked whatever happens; the body is
bounded by the middleware and the multipart parser by its own limits; no path is
ever built from anything a client sent. No new dependency.

## Done this session

All 27 tasks, Gate 1 passed (Confirmation 2 of round 1, all three findings
confirmed), and everything CI runs is green locally:

| Check | Result |
|---|---|
| `openspec validate --all --strict` | 15 passed |
| `scripts/*_test.sh` | both suites pass |
| `sh -n scripts/*.sh` | clean |
| `FORCE_COLOR=1 CI=true make check` | 470 passed |
| `FORCE_COLOR=1 CI=true make test-integration` | 230 passed |
| `FORCE_COLOR=1 CI=true make test-ui` | 45 passed |
| `make test-models` (real weights, never in CI) | 19 passed |
| `scripts/pregate-verify.sh gate2` | all checks passed |

What was built: the DINOv2 adapter (CLS token after the final layer norm, read
from the installed transformers, text refused outright), `POST /search/image`,
`GET /assets/{id}/similar`, a `model` parameter on all three searches with 503
and 422 refusals decided before anything loads, `semanticshelf index missing`,
and the interface's fifth page with a "Find similar" action under every
thumbnail.

Seven guards were demonstrated by removing them and watching the right test
fail: exclusion after the page is cut (a repeated neighbour), the missing window
candidate (`has_more` wrong at the deepest page), the excluding depth rule (the
effort invariant), the unlinked query picture, the modality check (503 instead
of 422), the advisory lock (the second backfill does not wait), and `failed`
treated as merely unfinished (work that gave up gets a fresh budget).

Two things found on the way, both fixed here:

- **CI was about to run the integration suite with both models enabled** and
  would have gone red in 43 tests: CI sets no `ENABLED_MODELS`, the default is
  now every implemented key, and only the machine's environment file was hiding
  it. The integration suite now declares what it runs, fakes every implemented
  key, and the folder CLI writes `ENABLED_MODELS` into the environment it hands
  the command.
- **`.env.example` and the local environment file** pinned one model. The user
  updated both by hand (the policy blocks those paths for me); the settings
  reference and the template block were updated to match.

## Next step

None — this change is done. Its four capability deltas are in
`openspec/specs/` (`image-search` is new; `text-search`, `indexing-jobs` and
`demo-ui` each carry what this change added), and `openspec/ROADMAP.md` opens
stage 3 with what it delivered.

## Blockers

None.
