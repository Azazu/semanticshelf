# Handoff — add-indexing-worker

**Updated:** 2026-09-24 · claude
**State:** blocked
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

One manual edit (below), then the push and `/gate-review add-indexing-worker 2`.

`scripts/pregate-verify.sh gate2 add-indexing-worker` will fail while task 6.2
is unchecked — that is the floor doing its job, not a surprise.

## Blockers

**Task 6.2 needs one manual edit.** The permission rules keep me out of the
directory holding the environment template, so two lines have to be added by
hand after `WORKER_BATCH_SIZE=4`:

```
WORKER_POLL_SECONDS=2
INDEXING_RUNNER=inline
```

`docs/reference/settings.md` already documents both, and the sweep that compares
the declared settings with the documented ones passes; the template is the only
place left.

