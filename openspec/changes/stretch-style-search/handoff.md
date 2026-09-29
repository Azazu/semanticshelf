# Handoff — stretch-style-search

**Updated:** 2026-09-28 · claude
**State:** awaiting-gate-2
**Branch:** change/stretch-style-search

## Done this session

**Gate 1 passed** at `eb3f588` (round 1 changes-requested, confirmation 1
changes-requested, confirmation 2 confirmed). Findings 1 and 2 reshaped the
measurement: `clip-vit-l14` is measured too, and the deciding statistic is a
rank preference rather than a ratio of averages, because a ratio is moved by a
model's own similarity scale.

Implemented, 9 of 16 tasks:

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

**Round 2's finding was withdrawn with the feature it objected to.** The cache
had to prove that the vectors in a file came from the same weights the next run
loads, and there is nothing here to prove it with: `clip-vit-l14` and
`dinov2-large` load a checkpoint *name* that is a setting, with no revision, and
each adapter resolves the weights and the processor in separate calls. A partial
check proves only the part it checked; a full check is the measurement itself.
Two confirmations failed on this, so under AGENTS.md the executor stopped and
the user arbitrated: **drop the cache**, run the measurement in one sitting.

Design decision 6 and task 2.6 are removed, the two applicability rows are back
to what Gate 1 round 1 confirmed, and the finding is `wont-fix` with that
reason. The defect it exposed is real and outlives this change, so it is
**roadmap row 20** (`pin-model-revisions`): ADR-005 pinned the query encoder's
revision for exactly this reason and the two stored keys were never pinned, which
means a stored vector cannot be reproduced from the key alone.

The artifacts are now the shape Gate 1 confirmed at `eb3f588`, plus the
implementation of tasks 1.1-2.5, 3.3 and 5.1.

## What CI runs, run locally (task 5.3)

| command | result |
|---|---|
| `FORCE_COLOR=1 CI=true make check` | **green** — 798 passed, 1 skipped |
| `openspec validate --all --strict` | **green** — 17 passed, 0 failed |
| `sh -n scripts/*.sh` | **green** — 7 files |
| `scripts/gate_run_test.sh` | **green** — 77 passed |
| `scripts/workflow_verify_test.sh` | **green** — 23 passed |
| `make audit` | **green** — no known vulnerabilities in 97 packages |
| `make image` | **green** — and the point of the group holds |
| `FORCE_COLOR=1 CI=true make test-integration` | **green** — 296 passed, 1 skipped |

**The image did not grow.** `semanticshelf:runtime` is **1.79 GB**, the same as
the build of 2026-09-28 that predates the dependency, and the service image
carries none of what the `style` group pulls in:

```console
$ docker run --rm --entrypoint sh semanticshelf:runtime \
    -c 'ls /app/.venv/lib/python3.12/site-packages | grep -iE "^(open_clip|torchvision|timm)"'
(nothing)
```

**The integration database is a container of its own.** The suite reads
`semanticshelf_it` on port 5434 from a standalone `pgvector/pgvector:pg16`
container named `semanticshelf-it`, not the compose `db` service on 5433; it had
stopped when the machine rebooted, and `docker start semanticshelf-it` was the
whole fix. Nothing in the configuration needed changing.

**One check failed first and was right to.** `make check` rejected
`scripts/style_candidate.py`: its own docstring quoted the literal the sweep
forbids. The sweep reads `git ls-files`, so the file passed while it was
untracked and failed the moment it was committed — the guard working exactly as
written. The docstring says the same thing without the literal.

## The mechanical floor for Gate 2 (task 5.4)

```console
$ scripts/pregate-verify.sh gate2 stretch-style-search
[OK]   git diff --check clean
[OK]   openspec validate stretch-style-search --strict
[OK]   risk tier declared: high
[OK]   proposal.md has a Non-goals section
[OK]   tasks.md has 16 task(s)
[OK]   every task checked
[OK]   checked-task referenced paths exist
[OK]   markdown links resolve (11 changed .md files)
[OK]   make check green
pregate-verify: gate2 stretch-style-search — all checks passed (0 warning(s))
```

## Next step

The user pushes `change/stretch-style-search` and reports the CI run; then
`/gate-review stretch-style-search 2` — Gate 2 on the code diff.

## Blockers

None.
