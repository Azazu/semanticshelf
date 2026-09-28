# Handoff — stretch-style-search

**Updated:** 2026-09-28 · claude
**State:** awaiting-gate-1
**Branch:** change/stretch-style-search

## Done this session

**Gate 1 passed** at `eb3f588` (round 1 changes-requested, confirmation 1
changes-requested, confirmation 2 confirmed). Findings 1 and 2 reshaped the
measurement: `clip-vit-l14` is measured too, and the deciding statistic is a
rank preference rather than a ratio of averages, because a ratio is moved by a
model's own similarity scale.

Implemented, 9 of 17 tasks:

- **1.1, 1.2** `scripts/style_corpus.py` — six looks as pure functions of the
  bytes, the stream the benchmark walks, and the refusals: a corpus below 20
  photographs or 4 looks, and a look that flattens a photograph to one colour.
  That last rule reads the picture's **interior**: a 3x3 filter leaves the
  outermost ring, so `edges` of a uniform picture is a flat field inside the
  original frame and a whole-picture rule missed exactly the case it exists for.
- **2.1** `open_clip_torch` in a group of its own, and `torchvision` declared
  beside it so `[tool.uv.sources]` can point it at the same index as `torch` —
  left to `open_clip` it came from PyPI and every import ended in "operator
  torchvision::nms does not exist". The image test now asserts the service
  builder names **no** group at all.
- **2.2** `scripts/style_candidate.py` — the tower with CLIP's projection
  removed before the load, the checkpoint at its pinned revision read with
  `weights_only=True` and four named globals, 0 missing and 0 unexpected, the
  style head applied to the pooled output.
- **2.3, 2.4, 2.5** `scripts/style_benchmark.py` — the rank preference, the
  diagnostic ratio, the bound as one strict comparison, and the command. The
  measured keys are read from `app.domain`; a unit test proves no key is
  written out in the command.
- **3.3** roadmap and requirements register reshaped: row 18 is the
  measurement, row 18a is the key, proposed only if ADR-006 says yes.
- **5.1** the demonstrated failing inputs, below.

Also written, pending only the numbers: **ADR-006** at `proposed`, carrying the
candidate, the corpus, the statistic and the bound — everything fixed *before*
the run, so the bound cannot be fitted to the table; and the fourth section of
`docs/how-to/benchmarks.md` minus its results.

## Demonstrated failing inputs (high tier, task 5.1)

Each guard removed on its own, the covering test run, the file restored.

| check | file | test | with the guard removed |
|---|---|---|---|
| a look is deterministic | `scripts/style_corpus.py` | `test_a_look_gives_the_same_bytes_every_time` | FAILED |
| a look that returns one colour is refused | `scripts/style_corpus.py` | `test_style_corpus.py -k refused` | FAILED |
| the corpus is large enough | `scripts/style_corpus.py` | `test_too_few_photographs_is_refused` | FAILED |
| the corpus has enough looks | `scripts/style_corpus.py` | `test_too_few_looks_is_refused` | FAILED |
| the allowlist is exactly four globals | `scripts/style_candidate.py` | `test_the_allowlist_is_exactly_these_four_globals` | FAILED |
| no source file turns the pickle check off | `scripts/style_candidate.py` | `test_no_source_file_turns_the_pickle_check_off` | FAILED |
| a checkpoint short of a tensor is refused | `scripts/style_candidate.py` | `test_style_candidate.py -k checkpoint` | FAILED |
| the checkpoint's width is the declared one | `scripts/style_candidate.py` | `tests/models/test_style_candidate.py` (real weights) | FAILED — `CheckpointWidthError` |
| the measured keys come from `app.domain` | `scripts/style_benchmark.py` | `-k measured_keys or no_model_key` | FAILED |
| a corpus forming no triple is refused | `scripts/style_benchmark.py` | `-k no_triple` | FAILED |
| the ratio has no value through a non-positive denominator | `scripts/style_benchmark.py` | `-k denominator` | FAILED |
| the bound is strict | `scripts/style_benchmark.py` | `-k exactly_on_the_bound or indifference_itself` | FAILED |
| the bound is taken against the best incumbent | `scripts/style_benchmark.py` | `test_the_bound_is_taken_against_the_best_incumbent_not_the_first` | FAILED |

## Scope change, and why Gate 1 is requested again

The machine this measurement runs on is in use, and twenty-five minutes of
CPU on it is not a number that can be scheduled around. The user asked for the
run to be payable in instalments while staying a full one, and agreed to the
shape below; that agreement is not a gate record, so the artifacts carry it and
the gate decides.

**Design decision 6** adds `--only <model>` and `--cache <directory>`, and
**task 2.6** implements them. The default is unchanged — with no `--cache` the
command writes nothing anywhere. What the decision is really about is the
fingerprint: a cache that served a vector from a different corpus would corrupt
a published number invisibly, so a cached file is read only when the model, the
candidate's revision, the corpus root, **every photograph's content**, the looks
and the labels all match, and a write is a rename of a temporary file.

Two rows of the applicability table changed with it — "crash around an external
effect" now has a second effect to answer for, and "concurrent writers" is no
longer `n/a`.

**Round 2 returned one major finding, and the first answer to it was wrong in
the same way.** The fingerprint named "the model", but only the candidate is
pinned here: `clip-vit-l14` and `dinov2-large` load a checkpoint *name* that is
a setting, with no revision. The first fix added the name and a commit hash
resolved from the local cache; the confirmation pointed out that each adapter
resolves the weights and the processor in two separate calls, that a later
lookup can report a snapshot neither of them read, and that the processor's
behaviour depends on the installed `transformers` too. Both are true, and they
are the same defect: a list of names and versions is always one entry short.

So the model side is no longer described — it is **checked**. A run that wants
to read a cache re-embeds the corpus's first few images with the model it
loaded and compares them with the cached rows. They match exactly when the
loaded model is the same function from picture to vector as the one that filled
the file, which is the only property the reuse depends on. A cache is then a
saving of the embedding, not of the loading.

## Next step

`scripts/gate-run.sh stretch-style-search 1 confirm 2` — second confirmation of
round 2, then task 2.6 and the run. Per AGENTS.md this is the last confirmation
attempt on this finding: if it fails again the cache is dropped and the change
goes back to the shape Gate 1 already approved, with the measurement run in one
sitting.

**Then blocked on one run** (below). When its output exists: fill ADR-006's Decision
and Consequences and set its status, add "What one run says" and "Reading it" to
the how-to (tasks 3.1, 3.2, 4.1, 4.2), then 5.2, 5.3 and 5.4.

## Blockers

The published measurement needs 600 images through three ViT-L-scale models on
a CPU — about 25 minutes at four threads, and the machine it would run on is in
use. The command is
`TORCH_NUM_THREADS=4 nice -n 19 uv run --group style python scripts/style_benchmark.py --pictures 100`
and it prints its progress and the time remaining.

Paying for it in instalments is what design decision 6 and task 2.6 add, and
why this change is at Gate 1 again rather than implementing them on a chat
agreement.
