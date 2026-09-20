# Handoff — add-embedder-protocol-and-clip

**Updated:** 2026-09-20 · claude
**State:** proposing
**Branch:** change/add-embedder-protocol-and-clip

## Done this session
- Branch and change scaffold created (roadmap row 4, tier high: the adapter downloads model weights, which is network egress from the service).

## Next step
- `/opsx:propose add-embedder-protocol-and-clip` — the `Embedder` protocol, a lazy per-process registry, a bounded inference threadpool, the deterministic fake embedder the test layers already expect, the CLIP adapter for both towers, a warm-up command and an on-demand real-model smoke test (specification §2.3 and §7, change 4). Tier high: Gate 1 on the artifacts before any code.

## Blockers
- None.
