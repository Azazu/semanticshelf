# Handoff — add-indexing-worker

**Updated:** 2026-09-24 · claude
**State:** implementing
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

Push `change/add-indexing-worker` and watch CI. On green:
`/gate-review add-indexing-worker 2`.

All 27 tasks are done. `scripts/pregate-verify.sh gate2 add-indexing-worker`
passes.

What Gate 2 should know before reading the diff:

- **The guarantee is at-least-once with a fenced completion**, stated that way
  in the delta spec, the requirements and the how-to. A test holds one runner
  inside the work while its lease expires, lets a second take the same unit, and
  asserts one vector with the loser's completion discarded.
- **The evidence is processes.** `tests/worker_child.py` is the command's
  runtime with the fake embedder and a barrier; seven integration tests
  rendezvous through `held-<pid>`, `signalled-<pid>` and `ready-<pid>`. The
  fixture that starts children kills any survivor — the first run of these tests
  leaked one, and it went on claiming work from every test after it.
- **The switch has four callers**, because FR-CLI-1 promised it would.
- **One thing outside the change's scope was corrected**: `settings.md` carried
  a copy of the environment template that had drifted from it by nine lines. The
  copy is gone, replaced by a reference — the repository's own rule about one
  authority. The template's own two new lines were added by the user, since the
  permission rules keep the executor out of that directory.

## Blockers

None.
