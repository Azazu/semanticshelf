# Handoff — add-background-indexing

**Updated:** 2026-09-21 · claude
**State:** awaiting-gate-2
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

The branch is pushed and its CI run is green (reported by the user), so all
59 tasks are checked. Gate 2 requested with
`/gate-review add-background-indexing 2`; the verdict and its findings are
recorded in `review.md` by the runner.

Local evidence, each command in its documented form:
`env -u DATABASE_URL make check` green (252 tests);
`make test-integration` green (113 tests) against pgvector;
`openspec validate --all --strict`, every `scripts/*_test.sh` and
`sh -n scripts/*.sh` green — everything CI runs.

## Blockers

None.
