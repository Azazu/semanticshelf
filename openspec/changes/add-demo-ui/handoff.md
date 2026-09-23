# Handoff — add-demo-ui

**Updated:** 2026-09-23 · claude
**State:** awaiting-gate-2
**Branch:** change/add-demo-ui

## Done this session

Branch, scaffold and all four planning artifacts. Two decisions the user made
before anything was written:

- **The screenshots are automated in this change**, not left for a person: a
  script brings up the API and the UI against the demo corpus, drives a headless
  browser and writes the three images the roadmap asks this change for.
- **The UI tests get their own `ui` marker**, run by `make test-ui` after
  `uv sync --group ui`, exactly as `models` and `integration` keep heavy
  dependencies out of the gate floor. CI will not run them until CI is taught
  to, and that is verifier infrastructure — `high` tier, its own change.

Decided in the proposal rather than inherited:

- **Tier `medium`**, raised from the roadmap's `low`: this adds a second
  application, two dependency groups, a browser-driven step and a page that
  deletes assets on a click. It touches nothing in the service, which is why it
  is not `high`.
- **The "Find similar" page is out of scope.** FR-UI-1 names five pages;
  `/similar` and image search arrive with DINOv2 in change 11, and that page
  arrives with them. This change delivers the four the roadmap names.

## Next step

**Gate 1 passed** — `approved`, the retrospective artifact review the tier
correction owed. Two `minor` findings, both about a claim being wider than its
mechanism, and both fixed rather than left to discretion:

- the tag on the search page filters what has already been fetched, because the
  search endpoint takes no tag (change 12 owns filtered vector search). The
  design, the spec and the how-to now say that, and say what follows from it:
  a page the filter empties is not the end of the ranking, so "More" stays;
- the import walk proves that nothing in `ui/` imports the service. It does not
  prove the interface *cannot* reach a database or the media root — that is held
  by there being nothing in the group that could, and by review of these few
  modules. The design, the spec's scenario and the how-to's opening sentence
  were all claiming the stronger thing.

Run: `/gate-review add-demo-ui 2 confirm 1`. The user pushes first.

Local evidence, the way CI runs it: `make check` 408 green,
`make test-integration` 198 green, `make test-ui` 35 green, strict validation
14/14.

## Blockers

None.
