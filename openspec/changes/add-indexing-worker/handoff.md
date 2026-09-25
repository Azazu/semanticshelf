# Handoff — add-indexing-worker

**Updated:** 2026-09-24 · claude
**State:** ready-to-merge
**Branch:** change/add-indexing-worker

## Done this session

26 of 27 tasks, in five commits:

- **the loop** (`run_worker`): a batch that took something is followed by
  another at once, a batch that took nothing by a wait — and that wait *is* the
  wait for the stop token, so a runner asked to stop while idle ends at once.
  `WORKER_POLL_SECONDS` with it.
- **stopping**: the first signal sets the token and the batch in hand is
  finished; the second logs that it was forced, restores that signal's default
  disposition and re-raises it, so the process dies the way `kill` means it to
  and the work returns by its lease.
- **the command** `semanticshelf worker [--once] [--batch N]`, the first that
  configures logging because it is the first that is a server.
- **the switch**: one function answers "may this process index what it just
  queued?", and four callers ask it — upload, reindex, `index-folder`,
  `index missing`. A command that leaves work queued says which of `--no-index`
  and `INDEXING_RUNNER` decided it.
- **the evidence**: `tests/worker_child.py` runs the real runtime with the fake
  embedder and a barrier inside the work; seven process tests rendezvous through
  `held-<pid>`, `signalled-<pid>` and `ready-<pid>`, and the fixture that starts
  children kills any that outlive their test — the first run leaked one, and it
  quietly claimed work from every test after it.

Five demonstrated failing inputs, each run and restored (the commit bodies name
them). `make check` 580, integration 275, ui 59, both script suites, `sh -n`,
`openspec validate --all --strict` 16.

## Next step

`/git:merge add-indexing-worker` — **Gate 2 confirmed** (confirmation 1 of round
1, commit `3f47574`): all three findings resolved, nothing new raised. Every
task checked, the branch pushed, CI green on that head.

The reviewer notes it could not rerun the process integration tests (its
database container was down) and inspected them instead; they were run here —
`make check` 582, integration 276, ui 59 — on the commit it confirmed.

After the merge: `/opsx:archive add-indexing-worker`, then the Russian companion
document outside the repository.

## Blockers

None.
