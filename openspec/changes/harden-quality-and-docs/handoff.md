# Handoff — harden-quality-and-docs

**Updated:** 2026-09-26 · claude
**State:** implementing
**Branch:** change/harden-quality-and-docs

## Done this session
- Branch `change/harden-quality-and-docs` created off `main` (which now carries
  the archived `containerize-full-stack`, the `deployment` capability and the
  widened `demo-ui` requirement); change scaffolded with `openspec new change`
  (schema `spec-driven`).
- `openspec/ROADMAP.md` already carries row 16 for this change — left as is.

## The artifacts
- `proposal.md` — **Risk-Tier: medium**, raised from the roadmap's `low` with
  both sides of the argument stated: four fifths of this change is
  documentation, and two pieces are not — a dependency audit that can redden a
  later change, and a layering rule the repository will be held to. No Gate 1
  (tier medium); Gate 2 reads the diff.
- `specs/http-api-conventions/spec.md` — MODIFIED: every operation carries an
  example that parses as the answer it illustrates, with the exemption for a
  body-less or binary answer recorded where the rule is enforced.
- `specs/deployment/spec.md` — ADDED: the locked dependencies are audited by CI
  and by a command, failing on a known vulnerability that has a fix.
- `design.md` — six decisions: Mermaid over an exported image, screenshots
  captured rather than composed, one table of forbidden import edges with a
  planted violation per row, `uv audit --locked` in CI (and why this one is in
  CI while the image scan is not), examples validated by their own models with
  the test inverted to catch the next operation, and the three boundaries the
  README states as boundaries.
- `tasks.md` — 5 groups, 16 tasks, each with its verification.

## What this change was measured against
16 operations, 5 with an example; `uv audit` reporting no vulnerabilities in 91
packages; three screenshots for five pages; a README that still says the
project is "scaffolded".

## Next step
`/opsx:apply harden-quality-and-docs` — the last change of the plan: the README a reader meets first (screenshots, an architecture diagram,
the benchmarks, the security notes of NFR-SEC-7, the CPU latency expectations,
the English-query limit), the layering test NFR-QA-2 asks for, a dependency
audit in CI (NFR-SEC-6), an ADR index, the how-to pages still missing, and the
OpenAPI examples owed by the operations of changes 2–7 (FR-OPS-4).

## Blockers
None. Note for the screenshots: the demo corpus in the development database was
truncated by integration runs, so `make demo` comes before `make screenshots`.
