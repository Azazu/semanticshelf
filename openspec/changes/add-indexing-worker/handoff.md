# Handoff — add-indexing-worker

**Updated:** 2026-09-24 · claude
**State:** fixing-g2
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

Push, then `/gate-review add-indexing-worker 2 confirm 1`. Round 1 asked for
changes (two major, one minor) and all three are fixed:

1. **A real bug.** `run_worker` claimed a batch before reading the stop, so a
   signal arriving while the handlers were being installed — or while an idle
   wait was timing out — was answered with one more batch of due work. The stop
   is now read at the top of the loop, and two unit tests cover an
   already-requested stop against a queue that has work, with and without
   `--once`. The fix caught a bad assumption in one of my own tests, which asked
   for a stop it did not mean.
2. **The harness was a copy.** The child recreated the engine, the pool, the
   handlers and the summary instead of running the command, so a broken
   production adapter could not fail these tests. It now installs the fake
   embedder and one seam — the acknowledgement — and hands its argv to
   `app.cli`: the engine, the logging, the loop, the summary and the disposal
   under test are the real ones. Demonstrated: removing `install_stop_handlers`
   from the adapter now fails two process tests, where before it would not have.
3. **The documented startup command** lacked `APP_PORT=8010` while the requests
   that follow it use that port.

`make check` 582, integration 276, ui 59.

## Blockers

None.
