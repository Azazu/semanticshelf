# Handoff — stretch-multilingual-queries

**Updated:** 2026-09-28 · claude
**State:** ready-to-merge
**Branch:** change/stretch-multilingual-queries

## Done this session

**The artifacts, and the probe under them.** Before anything was proposed the
feasibility question was answered rather than assumed: the package the model
card recommends does not load under this project's transformers, while the
model itself — XLM-RoBERTa large, a mean pool over the attention mask, one
linear layer — assembles by hand from the checkpoint and answers at width 768
in CLIP's space. **Risk-Tier: high** (a model download is egress from a process
this repository ships; the search endpoint widens).

**Gate 1 — three majors, all accepted**, then two confirmations on the same
defect this project keeps catching, a claim updated in one artifact and left
standing in a sibling. The acceptance bound was relative only, so a zero
baseline would have passed an encoder that finds nothing; the checkpoint was
read from a mutable branch while the numbers were to be evidence about a stable
key; and the truncation flag was missing from the adapter's task. Confirmed at
`0d4115d`.

**The implementation**

- **The encoder as a participant of its own**: `QUERY_ENCODERS` beside the
  model registry rather than a key in it, an adapter with no new dependency,
  both repositories pinned, the checkpoint read with `weights_only=True`.
  Against the real weights: width 768, unit rows, order kept, pictures refused,
  a query past the context cut and flagged, a wrong declared width refused —
  and a Russian query landing nearer the red square than the blue one, in
  vectors CLIP's *image* tower produced.
- **`model=` resolves to a pair**, and the answer names both. 503 for an
  encoder this build does not run, 422 for a picture asked of one, the default
  unchanged. Against a real index: the ranking is the encoder's, and nothing is
  written under its name — no vector, no job, no row in the stats.
- **The measurement** (`scripts/multilingual_benchmark.py`): recall@10 against
  the corpus's own labels and agreement@10 with the English page, over a
  concept set chosen by rules that look at no language's results. Russian,
  German, French and Spanish all clear both bounds. Published in
  `docs/how-to/benchmarks.md`, decided in **ADR-005**.
- **The documentation that had to change with it**: FR-TXT-5, the README's
  boundary (carrying the numbers rather than a promise), the searching and
  models how-tos, the settings reference, both registers.

**Two defects of my own, found by running my own work.** The benchmark
overwrote its English baseline with the encoder's page when asked for
`--languages en`, which would have made agreement 1.000 by construction; and
the width check had no test at all — the plant that removed it changed nothing.
Both are fixed, and both now have the test that would have caught them.

**Twenty planted violations, twenty failures** (§5.1 of `tasks.md`).

**Checks, in CI's own form**: `make check` 733 passed, integration 296,
`openspec validate --all --strict` 17/17, `sh -n` clean, `gate_run_test` 77,
`workflow_verify_test` 23, `make audit` clean on 91 packages, both images
built — and the `models` suite, which CI never runs and which this change is
the reason for, 9 passed against the real checkpoint.

**Gate 2 round 2 — two majors and a minor, all accepted** (§6 of `tasks.md`).
The adapter threw away what `load_state_dict` reported, so a checkpoint missing
a tensor would have loaded with a random layer and ranked under a published
key; the three `MCLIP_*` settings could point the key at other weights while
ADR-005's languages rode along on it, and are gone — the checkpoint and both
revisions are constants, because an encoder's key claims alignment that nothing
at runtime can check; and the endpoint still described itself as English-only
with scores comparable within a model. Twenty-two plants now, twenty-two
failures.

**Gate 1** confirmed at `0d4115d`, **Gate 2** confirmed at `a2732c3` — all
three findings of each round.

## Next step

`/git:merge stretch-multilingual-queries`, then `/opsx:archive`. The change
carries two spec deltas (`text-search`, `embedding-models`) for the sync.

## Blockers

None.
