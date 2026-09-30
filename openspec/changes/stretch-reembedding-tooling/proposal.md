# Proposal — stretch-reembedding-tooling

**Risk-Tier:** high

Two triggers from this project's own list: the change **deletes embeddings**, and
it **runs models** over a whole corpus, which is network egress on a cold cache
and hours of CPU on a warm one. Gate 1 before implementation, a demonstrated
failing input for every new check.

## Why

§9 of the requirements has asked for re-embedding tooling since change 0 —
`models migrate <old-key> <new-key>`, "for model upgrades without downtime" —
and `openspec/ROADMAP.md` never carried a row for it. ADR-007 then made it
load-bearing: it names re-embedding as the **only** repair for vectors stored
before checkpoint revisions were pinned, whose provenance nobody can
reconstruct. The project references tooling it does not have.

Half of it is already built. `semanticshelf index missing --model KEY` queues the
work assets have no vector for and carries it out, the queue is at-least-once
with leases and an idempotent upsert (ADR-003), and `POST /assets/{id}/reindex`
re-runs one asset. What is missing is everything after filling: knowing that the
new key is **complete**, and retiring the old one without a window in which
searches answer from a half-filled index.

And the shape §9 asked for is not the shape ADR-007 needs. §9 wants two
different keys; ADR-007 wants **one key rebuilt** because its weights changed.
Underneath they are the same operation with a different selection, so this
change builds one engine and puts two subcommands on it — the alternative is a
command with nothing to run against, because today's allowlist holds two keys of
different spaces and migrating between them is meaningless.

## What Changes

- **`semanticshelf models migrate <old-key> <new-key>`** — compute the new key's
  vectors for every asset that has one under the old key, then report whether
  the new key is complete. With `--apply --retire`, and only when it is
  complete, delete the old key's vectors.
- **`semanticshelf models reembed <key>`** — recompute every vector stored under
  one key and replace it. This is the repair ADR-007 names, and the one that can
  be run against this repository's own corpus today.
- **Both report by default and act on `--apply`**, as `storage prune` does. The
  report says how many vectors would be computed before anything computes them,
  which on a laptop is the difference between a decision and a surprise.
- **Completeness is a precondition, not a hope.** Retirement is refused unless
  every asset with a vector under the old key has one under the new, counted in
  one place at one moment.
- **ADR-008** records why two subcommands share one engine, why retirement is a
  separate word, and what "without downtime" rests on.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `indexing-jobs`: an operator can ask for the work a *rebuild* needs — assets
  that already have a vector for a key — beside the missing work it already
  asks for, and can learn whether a key is complete for the corpus.
- `embedding-storage`: a key's vectors are deleted only when another key can
  answer for every asset that had them, and only when an operator said so in as
  many words.

## Impact

- **New:** two CLI subcommands, a repository query for completeness, a selection
  for "assets that already have a vector under this key",
  `docs/adr/ADR-008-*.md`, sections in `docs/reference/commands.md` and
  `docs/how-to/models.md`, unit and integration tests.
- **Changed:** `app/cli.py`, `app/services/indexing.py` (the selection, not the
  runner), `app/repositories/embeddings.py`, `openspec/ROADMAP.md` row 21.
- **Unchanged:** the queue's mechanics, leases, retries and at-least-once
  guarantee; both search endpoints; the schema, the CHECK and the indexes; the
  API; the model adapters.
- **Downtime:** none, and nothing new is needed for that. Which key answers a
  search is the request's `model`, defaulting to a repository constant — so the
  old key keeps answering while the new one fills, and the switch is a separate,
  deliberate act.

## Non-goals

- **No new model key.** Adding one to the allowlist is a migration and the
  change that adds the model writes it. This command operates on keys the schema
  already permits.
- **No automatic switch of which key answers.** The default key is a constant in
  `app/domain.py`; changing it is a code change with its own review. A command
  that silently repointed search would be the kind of surprise this repository
  spends its reviews preventing.
- **No scheduling.** No cron, no background trigger, no "re-embed when a
  revision changes". An operator runs it.
- **No resume state of its own.** The queue is at-least-once and the upsert is
  idempotent; a re-run finishes what an interrupted run left. Inventing a second
  progress record beside the queue would be a second source of truth.
- **No undo.** Deleted vectors are gone; the repair is to run the command again,
  which is why retirement is refused unless the replacement is already complete.
