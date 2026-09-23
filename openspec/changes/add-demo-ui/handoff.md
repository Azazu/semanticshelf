# Handoff — add-demo-ui

**Updated:** 2026-09-23 · claude
**State:** proposing
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

Gate 2 only (tier `medium`), so implementation is next: `/opsx:apply
add-demo-ui`. Twenty tasks in seven groups; the first settles which multipage
entry point the installed Streamlit wants, which is the design's one open
question.

## Blockers

None.
