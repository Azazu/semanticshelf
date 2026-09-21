# Handoff — add-background-indexing

**Updated:** 2026-09-21 · claude
**State:** archived
**Branch:** change/add-background-indexing

## Done this session

Task groups 1-8 complete; 55 of 59 tasks checked.

- `app/services/indexing.py`: the queue's policy (backoff, what a reason may
  say) and its three steps — claim, execute, finish — each in its own session,
  plus `run_batch` and the `drain` an upload and a reset schedule.
- `app/repositories/jobs.py`: the claim query with `SKIP LOCKED`, the lease,
  the conditional finishes bound to it, the reset, and the newest status per
  model for one asset or a whole page.
- The API surface: `index_status` in every asset representation,
  `index_status=<model>:<state>` on the listing, `GET /assets/{id}/jobs` and
  `POST /assets/{id}/reindex`.
- An absent stored file is no longer reported as "not a picture": the
  inspection lets `FileNotFoundError` through, which is what made the
  service's own missing-file branch reachable.
- 25 failing-input probes (group 7), each removing one guard and watching its
  own test fail; the log is in the commit `test(indexing): the greyscale check
  sees what the model was handed`.
- ADR-003 (queue in PostgreSQL, with its measurements),
  `docs/how-to/indexing.md` run against a live service, the three settings in
  the reference, and the corrected layout in AGENTS.md.
- Security-sensitive surface in this change: none of authentication, money or
  cryptography; it does touch input handling (a stored file is re-inspected
  before it is decoded) and concurrency (the claim, the lease, the conditional
  finishes), which is why the tier is `high`.

## Next step

Gate 2 round 1 came back `changes-requested` with two `major` findings, both
real and both fixed:

1. `{"models": []}` reset every job: the endpoint collapsed an empty list to
   "no selection" and the repository treated an empty sequence as an absent
   filter. A selection of nothing now selects nothing, in both places, and the
   rule is in the spec delta, the schema, the endpoint description and the
   how-to. Probes 7.23 and 7.24.
2. `lease_expires_at` never reached the wire, so an operator could not see when
   a running claim stops owning its job. It is in `IndexingJobRead` and its
   mapping now, with the how-to re-recorded against a live service — the
   running snapshot shows the lease ten minutes ahead of `started_at`. Probe
   7.25.

Gate 2 passed: Confirmation 1 on `d24b2e0` reads `confirmed`, both findings
resolved.

Local evidence: `env -u DATABASE_URL make check` green (252 tests);
`make test-integration` green (116 tests); all 28 probes of group 7 caught
their removal on a full re-run.

Merged into `main` as `3da0cc7` (`--no-ff`, gate 2 approved) and pushed. The
delta specs are synced into `openspec/specs/` — `indexing-jobs` is a new
capability, `asset-api` and `asset-upload` gained the requirements above — and
this change is archived.

## Blockers

None.
