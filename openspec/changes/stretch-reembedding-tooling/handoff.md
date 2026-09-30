# Handoff — stretch-reembedding-tooling

**Updated:** 2026-09-30 · claude
**State:** proposing
**Branch:** change/stretch-reembedding-tooling

## Done this session

- Branch `change/stretch-reembedding-tooling` created off `main`, which carries
  changes 0–20 archived, including `pin-model-revisions` and ADR-007.
- Change scaffolded with `openspec new change` (schema `spec-driven`).
- **Roadmap row 21 added.** This wish had no row: §9 of the requirements has
  listed "re-embedding tooling" since change 0, and `openspec/ROADMAP.md` never
  carried it. The two documents disagreed, which surfaced when the user asked
  what work was left.

## Why now

ADR-007 names this the repair for something it could not fix: vectors stored
before revisions were pinned have provenance nobody can reconstruct, and the
only way to make a corpus one model's again is to re-embed it. The project now
references tooling it does not have.

## What is already here, and what is missing

- `semanticshelf index missing [--model KEY]` queues the work stored assets have
  no vector for and carries it out. That is the **filling** half, and it exists.
- `POST /assets/{id}/reindex` re-runs one asset.
- The queue is at-least-once with leases and an idempotent upsert (ADR-003), so
  an interrupted run is already a solved problem in the layer below.
- What is missing is the **retirement** half: moving a corpus from one key to
  another and taking the old key out of service, without a window in which
  searches answer from a half-filled index.

## Questions the proposal has to answer

- **What "without downtime" means here.** Two keys coexist while the new one
  fills, and search keeps answering from the old one until the new is complete —
  so the command needs a definition of complete, and the service needs to know
  which key answers while both exist.
- **How completeness is established** before anything is deleted. Every asset
  with a vector under the old key has one under the new, counted in one place at
  one moment, or the deletion is refused.
- **What an interrupted run leaves.** Probably nothing new: the queue is
  at-least-once and the upsert is idempotent, so a re-run should be a no-op for
  what finished. That needs stating rather than assuming.
- **Whether the old key is deleted at all, or only disabled.** Deleting
  embeddings is irreversible; disabling a key is not. These are different
  promises and the requirements say "retires", which is ambiguous.
- **Risk tier.** `high`: deletion of embeddings is on this project's own trigger
  list, and so is a migration if the model allowlist has to change.

## Next step

`/opsx:propose stretch-reembedding-tooling`.

## Blockers

None.
