# Handoff — stretch-style-search

**Updated:** 2026-09-28 · claude
**State:** awaiting-gate-1
**Branch:** change/stretch-style-search

## Done this session

Gate 1 round 1 returned `changes-requested` with three findings. All three are
fixed, and finding 1 turned out to reach further than it was written.

- **Finding 1 (major) — only one incumbent was being measured.** `clip-vit-l14`
  stores image vectors too. The probe was re-run against it, and it is the key
  that matters: on the ratio the proposal published it scores 0.675, against
  `dinov2-large`'s 0.145 and the candidate's 0.92. The benchmark, the ADR and
  the spec now cover every key the service stores vectors of that kind under,
  read from `app.domain` rather than written out.
- **Finding 2 (major) — the ratio is undefined where it must not be**, and it
  answers the wrong question. Adding CLIP showed both at once: it ranks a shared
  look above a shared subject in 1.9% of triples while the ratio calls it two
  thirds of the way to a style model, because its similarities sit in a narrow
  high band. The deciding number is now a **rank preference** — a proportion of
  a finite set of triples, so no zero denominator, no negative value, no
  dependence on a model's similarity scale — and the bound is `> 0.5` plus half
  the remaining headroom over the best incumbent, both derived from the metric
  rather than from the probe. The ratio stays as a printed diagnostic that
  decides nothing, with `undefined` where its denominator is not positive.
- **Finding 3 (minor) — the applicability table and task 1.1 disagreed** about a
  look that returns a blank picture. One rule now: the corpus builder refuses a
  look that returns a constant picture for a given photograph, so nothing blank
  reaches an embedder.
- **Swept for the claim, not the line:** `rg` over `leaning`, `3×`, `incumbent`
  and `blank` found and fixed three stale siblings — the Goals line naming only
  DINOv2, the "one candidate, one incumbent" non-goal, and the "one candidate
  against the incumbent" non-goal.
- **One claim checked and made precise while here:** "0 missing and 0
  unexpected" holds only when CLIP's own projection is removed *before* the
  load; leave it attached and the report names `proj` missing. Verified in the
  prescribed order, and the order is now in task 2.2 and in the design.
- Tasks grew from 15 to 16: the bound is its own task with its own tests.

**Confirmation 1** confirmed findings 1 and 3 and returned finding 2: task 2.4
asked for a test that cannot exist. The bound `incumbent + (1 - incumbent) / 2`
is `(1 + incumbent) / 2`, which is never below 0.5, so no candidate can clear it
while scoring under 0.5 — the second condition was redundant and its test
impossible. The bound is now **one strict comparison**, the design says why that
subsumes the indifference floor, and task 2.4's cases are the ones that exist:
short of the bound, exactly on it (refused), above it, the incumbent taken from
the highest of several, and the degenerate incumbent of 0.

## Next step

`scripts/gate-run.sh stretch-style-search 1 confirm 1` — second confirmation of
round 1. `scripts/pregate-verify.sh gate1 stretch-style-search` passes (16 tasks, tier
declared, applicability table present, links resolve) and
`openspec validate stretch-style-search --strict` is clean.

## Blockers

None.
