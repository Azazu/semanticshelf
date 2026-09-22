# Handoff — add-demo-dataset

**Updated:** 2026-09-22 · claude
**State:** proposing
**Branch:** change/add-demo-dataset

## Done this session

Branch and scaffold only. The roadmap already carried the row (change 9,
tier medium): a demo corpus the search can be shown on — a download command
for an openly licensed dataset with its licence checked and its notice kept,
tags from the dataset's own labelling, provenance in `meta`, and `make demo`.

## Next step

`/opsx:propose add-demo-dataset`. Questions the proposal has to settle before
anything is written: which dataset and under which licence, what the command
does when the licence file cannot be verified, where the notice lives in the
repository, how much is downloaded by default, and whether the import goes
through the folder pipeline of change 7 or its own path.

Network egress from the service is a `high`-tier trigger in AGENTS.md, so the
tier is the first thing the proposal decides rather than inherits: the roadmap
says `medium`, and a command that downloads from the internet may not be.

## Blockers

None.
