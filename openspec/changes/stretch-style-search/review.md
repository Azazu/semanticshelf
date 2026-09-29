# Review — stretch-style-search

## Round 1 · Gate 1
**Reviewer:** codex
**Date:** 2026-09-28
**Reviewed-Commit:** f8e62d57fd00dc57c0a5a9de84c4e1ae80134fd2
**Verdict:** changes-requested

### Findings
| # | Severity | Location | Finding | Status |
|---|----------|----------|---------|--------|
| 1 | major | `specs/embedding-models/spec.md:28-32`; `tasks.md:41-44` | The new requirement permits a key only after its margin is measured against every existing key, but the benchmark and decision tasks compare CSD only with `dinov2-large`. `clip-vit-l14` is also a stored image-vector key in `app/domain.py`. Measure it under the same question or narrow the requirement and justify why that key is excluded; otherwise the planned ADR cannot establish the scenario it is meant to satisfy. | fixed |
| 2 | major | `design.md:94-112`; `tasks.md:35-40` | Leaning is a ratio of cosine-similarity means, which can be zero or negative even when both pair sets are nonempty. A zero denominator makes the decision undefined; a negative denominator can reverse the ordering, and a nonpositive incumbent makes the 3× bound vacuous. Define the metric and decision for these cases before the full run, then add tests for those values. | fixed |
| 3 | minor | `design.md:60`; `tasks.md:5-11` | The applicability table says a blank image produced by a look is embedded like any other image, while task 1.1 requires refusing that look. Choose one corpus rule and make the design and verification task agree. | fixed |

## Confirmation 1 · Gate 1 · Round 1
**Reviewer:** codex
**Date:** 2026-09-28
**Reviewed-Commit:** 9d111cf929641dd0e4a139a6129652eab62c38d4
**Verdict:** changes-requested

### Findings
| # | Resolution |
|---|------------|
| 1 | confirmed — the benchmark and decision tasks now measure `clip-vit-l14` and `dinov2-large`, derive the stored image keys from `app.domain`, and record every incumbent in the ADR. |
| 2 | changes-requested — the deciding rank preference and diagnostic ratio handle the zero and negative denominator cases, but task 2.4 requires a test where a candidate clears the headroom bound while scoring below 0.5. This is impossible: preference scores lie in [0, 1], so every incumbent is at least 0 and `incumbent + (1 - incumbent) / 2` is at least 0.5. Replace that test with a feasible boundary case; as written, the Gate 1 implementation plan cannot be completed. |
| 3 | confirmed — the design and task 1.1 now both refuse a constant picture for that photograph. |

## Confirmation 2 · Gate 1 · Round 1
**Reviewer:** codex
**Date:** 2026-09-28
**Reviewed-Commit:** eb3f588328bfd032d6ef7f673c2a78579247191f
**Verdict:** confirmed

### Findings
| # | Resolution |
|---|------------|
| 1 | confirmed — the diff retains the comparison against both stored image keys and the task to derive them from `app.domain`; the ADR task still requires every incumbent's result. |
| 2 | confirmed — task 2.4 replaces the impossible below-0.5 case with feasible tests below, on, and above the strict headroom bound, including an incumbent of 0 and selection of the highest incumbent. The design uses the same single bound; task 2.3 still covers zero and negative diagnostic denominators. |
| 3 | confirmed — the corpus rule remains consistent: the design and task 1.1 both refuse a constant picture for that photograph. |

## Round 2 · Gate 1
**Reviewer:** codex
**Date:** 2026-09-28
**Reviewed-Commit:** f12e7fb6b035d0ecc8747117edef5a28524982ba
**Verdict:** changes-requested

### Findings
| # | Severity | Location | Finding | Status |
|---|----------|----------|---------|--------|
| 1 | major | `design.md:227-240`; `tasks.md:67-79` | The proposed cache fingerprint does not identify the actual CLIP and DINOv2 checkpoints or their processors. Both incumbent adapters load configurable model names without a pinned revision (`app/ml/clip.py` and `app/ml/dinov2.py`), so changing a configured name or receiving new weights at the same name can leave the fingerprint unchanged and reuse vectors from a different model. The claimed equivalence between a cached run and a fresh run therefore does not hold. Bind each cache entry to the effective checkpoint and preprocessing identity for every model, or narrow the cache guarantee and ensure the published run recomputes vectors; add a test that changes an incumbent's model identity. | wont-fix (the cache is withdrawn: after two failed confirmations the user arbitrated, design decision 6 and task 2.6 are removed, and nothing in this change writes or reads a vector outside the run that computed it. The defect the finding exposed — that `clip-vit-l14` and `dinov2-large` load a checkpoint name with no pinned revision — is recorded as roadmap row 20) |

## Confirmation 1 · Gate 1 · Round 2
**Reviewer:** codex
**Date:** 2026-09-28
**Reviewed-Commit:** 95298a9d35967cdc37752140f6eb305bfb1ab644
**Verdict:** changes-requested

### Findings
| # | Resolution |
|---|------------|
| 1 | changes-requested — the new fingerprint includes the configured incumbent name and a commit hash resolved from the local model cache, but it does not bind that hash to the weights and processor actually used. Both adapters call `from_pretrained(name, cache_dir=cache)` separately for the processor and model, without a revision, so the two loads can resolve different snapshots and a later cache lookup can report a snapshot different from either load. The processor's behavior also depends on the installed `transformers` version, which the fingerprint omits. Resolve an immutable revision before loading and use it for both objects, or identify both loaded objects directly; include the preprocessing implementation version (or recompute on a version change). Add tests for a changed resolved revision and for these identity mismatches so a cache hit cannot reuse vectors from different weights or preprocessing. |

## Confirmation 2 · Gate 1 · Round 2
**Reviewer:** codex
**Date:** 2026-09-28
**Reviewed-Commit:** b433fb85177fbad7d339ae13e0152d05cf3f4846
**Verdict:** changes-requested

### Findings
| # | Resolution |
|---|------------|
| 1 | changes-requested — re-embedding the first few images establishes agreement only on those images, not that the loaded weights and processor produced every cached vector. A changed incumbent can agree within tolerance on the probes and differ on other corpus images, so the claimed equality of cached and fresh measurements still does not follow; the design explicitly acknowledges this gap. Task 3.1 still permits assembling the published table from cached runs, and the proposal still promises a fingerprint over every input that can change a vector. Bind cache entries to the effective weights and preprocessing identity, or require the published run to recompute all vectors and narrow the cache claim accordingly. Test the chosen protection with an incumbent whose identity changes while its probe outputs remain the same and other outputs differ. |

## Round 1 · Gate 2
**Reviewer:** codex
**Date:** 2026-09-29
**Reviewed-Commit:** e9ea55c722323ad869f19d8b4448476e26129e78
**Verdict:** changes-requested

### Findings
| # | Severity | Location | Finding | Status |
|---|----------|----------|---------|--------|
| 1 | major | `scripts/style_candidate.py:167` | The candidate is built with a different activation from the released CSD model. Upstream CSD constructs OpenAI CLIP ViT-L/14, whose residual MLPs use QuickGELU; OpenCLIP 3.3.0's plain `ViT-L-14` configuration defaults to `quick_gelu=False`, hence `nn.GELU`. Loading the state dict cannot detect this because the activation has no tensors. The published table therefore measures an altered network, despite the claim that the adapter builds the checkpoint's architecture exactly. Enable the matching QuickGELU architecture, add an architecture/reference-output regression test, and rerun the measurement before updating its decision and numbers. Primary-source evidence is linked below. | fixed ( the tower is `ViT-L-14-quickgelu` and the built activation is asserted before the load; confirmed independently against the local `openai/clip-vit-large-patch14` config, which declares `hidden_act: quick_gelu`, and the two towers differ by cosine 0.93 on this corpus. The measurement was run again on the corrected tower: the candidate falls from 0.395 to 0.282 and `edges` from 0.981 to 0.898, while both incumbent rows come back identical to the digit — which is what established that the activation was the whole of the difference. ADR-006 and the how-to carry the new table, the corpus digest and the resolved incumbent revisions, and the ADR records what the wrong architecture had flattered) |
| 2 | major | `scripts/style_corpus.py:130-150`; `scripts/style_benchmark.py:333-343` | The minimum corpus bounds apply only to planned paths and look names, before constant-image rejection. Nothing checks the surviving labels before scoring and reporting. Reproduced in memory with 20 input pictures, 18 uniform and two gradients: `check_size` succeeds, `images` leaves only two photographs, and `score` still returns a preference (0.5 for identical fake vectors). Thus the command can publish a verdict from a corpus explicitly forbidden by task 1.2 and the how-to. Validate the effective corpus after rejection, refuse a wholly empty stream cleanly, and cover these cases with failing-input tests. | fixed (twice: `embed` now returns an empty result instead of concatenating an empty list, and the test that was supposed to cover it did not — it patched a second copy of `style_corpus`, since `script_module` builds a fresh module object each call, so the command refused for having no photographs at all rather than for losing them to the looks. It now patches the module the command imported and asserts the message of that path; with the guard removed it reproduces the reviewer's `ValueError`) |
| 3 | major | `openspec/changes/stretch-style-search/specs/embedding-models/spec.md:56-59`; `docs/how-to/benchmarks.md` (style run); `scripts/style_benchmark.py:324-343` | The new re-run scenario promises the same numbers from pinned checkpoints, but the published command still loads configurable, unpinned incumbent weights and processors through `FACTORIES`. Recording that existing defect as roadmap row 20 and withdrawing the vector cache does not make this new guarantee true: a fresh run can also load different weights. The published corpus is only a local folder's first 100 JPEGs, without an exact manifest or a reproducible acquisition recipe identifying this sample. Bind the published benchmark to identifiable corpus bytes and effective model/processor revisions, or explicitly narrow the new scenario and the matching design/documentation claims to acknowledge the deferred reproducibility work. This finding concerns the newly claimed guarantee, not a request to restore caching. | fixed (the narrowing is completed rather than the identity captured: capturing it needs the service's adapters to pin a revision and pass it to both calls, which is roadmap row 20. The spec now claims reproducibility only for what this repository pins, the applicability table's retry row is qualified to one machine, and the checkpoint table is printed under a caveat that it is diagnostic only and that matching rows establish neither matching inputs nor matching numbers — asserted by a test) |

### Review evidence

- Targeted checks: 75 passed via `PYTHONDONTWRITEBYTECODE=1 PYTEST_ADDOPTS='-p no:cacheprovider tests/unit/test_style_benchmark.py tests/unit/test_style_corpus.py tests/unit/test_style_candidate.py tests/unit/test_image_definition.py' make test RUN='.venv/bin/python -B -m'`.
- Corpus-bound reproduction used in-memory PIL images and a patched image reader; no corpus files or model downloads were created.
- Architecture checked against [upstream CSD's constructor](https://raw.githubusercontent.com/learn2phoenix/CSD/main/CSD/model.py), [OpenAI CLIP's residual block](https://raw.githubusercontent.com/openai/CLIP/main/clip/model.py), [OpenCLIP 3.3.0's ViT-L-14 configuration](https://raw.githubusercontent.com/mlfoundations/open_clip/v3.3.0/src/open_clip/model_configs/ViT-L-14.json), and [its vision-tower activation selection](https://raw.githubusercontent.com/mlfoundations/open_clip/v3.3.0/src/open_clip/model.py).
- The real-weight benchmark and models suite were not rerun: the current environment has no `open_clip` installation. The reported measurement's numerical change after correcting the activation is therefore not quantified here.

## Confirmation 1 · Gate 2 · Round 1
**Reviewer:** codex
**Date:** 2026-09-29
**Reviewed-Commit:** a34d6dfafea4f5f34f61104af059c8e67fd81bb2
**Verdict:** changes-requested

### Findings
| # | Resolution |
|---|------------|
| 1 | confirmed — the adapter selects `ViT-L-14-quickgelu` and checks the constructed residual MLP activation before loading tensors. The installed OpenCLIP configuration enables QuickGELU and its tower builder uses that flag. Regression tests cover the selected variant and rejection of GELU. ADR-006 and the how-to record the corrected measurement (candidate preference 0.282, edges 0.898) and retain the no-third-key decision. |
| 2 | changes-requested — the surviving-label bounds fix the nonempty undersized corpus, but a wholly rejected corpus still crashes before reaching them: `embed()` calls `np.concatenate(rows)` with an empty list. Calling `main()` with twenty in-memory uniform photographs reproduces `ValueError: need at least one array to concatenate`, rather than the promised clean refusal. Handle the empty stream before concatenation and test the command path through embedding and validation; the new direct `check_present([])` test cannot exercise this failure. |
| 3 | changes-requested — the revised scenario still promises that the record identifies whether runs used the same corpus and checkpoints, and design decision 6/how-to still claim readers can see which input differed. `checkpoints()` only scans the cache's current `main` refs after inference; it does not identify the weights or processor actually loaded by the two separate, unpinned `from_pretrained()` calls. A processor loaded from revision A and weights loaded from B can be reported as B, indistinguishably from a run loading both from B; `unresolved` likewise cannot establish identity. Either capture effective model and processor identities, or complete the permitted narrowing: describe the cache scan as diagnostic only and explicitly state that matching report entries do not establish matching inputs or numbers. Reconcile the remaining exact-reproduction claim in the design applicability table and add a regression test for the chosen behavior. |

### Confirmation evidence

- Scope: only the diff from `e9ea55c722323ad869f19d8b4448476e26129e78` to the reviewed commit and the call paths/artifacts implicated by findings 1–3.
- Targeted checks: 86 passed via `PYTHONDONTWRITEBYTECODE=1 PYTEST_ADDOPTS='-p no:cacheprovider tests/unit/test_style_benchmark.py tests/unit/test_style_corpus.py tests/unit/test_style_candidate.py tests/unit/test_image_definition.py' make test RUN='.venv/bin/python -B -m'`.
- Empty-corpus reproduction patched the image reader, candidate loader, settings and corpus planner in memory, then called the actual `main()`/`embed()` path; no images or model weights were written or downloaded.
- Architecture verified against the installed OpenCLIP quickgelu configuration and vision-tower builder. The real-weight benchmark and models suite were not rerun during this confirmation; the numerical rerun is recorded in the updated ADR and handoff.
