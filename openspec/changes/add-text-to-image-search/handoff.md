# Handoff — add-text-to-image-search

**Updated:** 2026-09-21 · claude
**State:** proposing
**Branch:** change/add-text-to-image-search

## Done this session

- Branch and scaffold created, the first change of stage 2. The work, from
  roadmap row 8 and `docs/explanation/requirements.md` §2.5 (FR-TXT-1…5) with
  §2.7 (FR-FLT-1…5): `GET /api/v1/search/text?q=…` embeds the query with the
  CLIP text tower and ranks the stored `clip-vit-l14` image vectors by cosine
  similarity — the first time the project does the thing it exists for.
- What the brief fixes, and what the proposal will have to decide: the query is
  1–256 characters and the answer says when CLIP truncated it; an item is the
  asset representation plus a score in [−1, 1], ordered by score then
  identifier; only assets whose CLIP work is `done` can appear; the envelope
  carries `items`, `limit`, `offset`, `has_more` (fetched as `limit + 1`), the
  model key, and `query_truncated`, with no total; `min_score` drops items
  after ranking; `tags_all` and `tags_any` filter **inside** the vector query
  rather than after it; every search sets `hnsw.ef_search` to
  `max(HNSW_EF_SEARCH, limit + offset)` and refuses a page beyond 1 000 with
  422 `page-too-deep`.
- ADR-001 is the constraint that shapes the query: the index is partial and on
  a cast expression, so a search that loses the cast or the model predicate
  silently stops using the index. The proposal has to say how that is kept
  honest — `EmbeddingRepository.nearest` already carries the cast and the
  plan-asserting test.

## Next step

`/opsx:propose add-text-to-image-search` — proposal, spec delta, design and
tasks. Tier is `medium` by the roadmap, and the proposal should argue it: no
path handling, no deletion, no concurrency beyond what exists; the risk is a
ranking that looks plausible and is wrong, which is a matter for tests rather
than for a gate. Gate 2 on the code, then.

## Blockers

None.
