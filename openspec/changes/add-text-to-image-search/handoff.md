# Handoff — add-text-to-image-search

**Updated:** 2026-09-21 · claude
**State:** proposing
**Branch:** change/add-text-to-image-search

## Done this session

- All four artifacts written and strict-valid: `proposal.md` (tier `medium`),
  four delta specs, `design.md`, `tasks.md` (29 tasks).
- Capabilities: `text-search` and `service-stats` are new; `asset-api` gains
  the tag census; `embedding-storage`'s lookup gains an offset and a maximum
  distance, because a page of results and a threshold have to be one statement
  the index answers rather than a sift over a fixed candidate list.
- Three scope decisions the proposal argues rather than assumes: tag and
  metadata filters on search belong to change 12 (they are a filtered-HNSW
  question with its own measurement), the `model` parameter and DINOv2 belong
  to change 11, and FR-TXT-3's "only assets whose job is done" is amended —
  what the store can answer is "has a vector", and a reset leaves the old
  vector in place rather than hiding the asset from search until the work runs.
- `scripts/pregate-verify.sh gate1 add-text-to-image-search` passes. Tier
  `medium` means no Gate 1 is required; the floor was run because it is cheap
  and it checks the artefacts are coherent before implementation starts.

## Next step

`/opsx:apply add-text-to-image-search`, starting with task group 1: the vector
query gains an offset and a threshold, with the plan-reading test extended to
the statement the endpoint will actually run.

## Blockers

None.
