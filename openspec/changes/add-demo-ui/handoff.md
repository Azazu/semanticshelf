# Handoff — add-demo-ui

**Updated:** 2026-09-23 · claude
**State:** ready-to-merge
**Branch:** change/add-demo-ui
**Security-sensitive:** yes — this change adds dependencies (two groups:
Streamlit and Playwright), uploads a file from a page, and deletes assets
irreversibly on a person's click. `AGENTS.md` puts each of those at `high` tier
and asks for the flag here and in the commit bodies.

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

- **Tier `high`.** The roadmap declared `low` and this change was first proposed
  as `medium`, on the reasoning that it touches nothing in the service. Gate 2
  rejected that reasoning and was right to: `AGENTS.md` puts a change touching
  file uploads or dependencies at `high` whatever else is true of it, and this
  one also deletes assets irreversibly. The tier was corrected during the change,
  the applicability table added, and Gate 1 run retrospectively (`approved`).
- **The "Find similar" page is out of scope.** FR-UI-1 names five pages;
  `/similar` and image search arrive with DINOv2 in change 11, and that page
  arrives with them. This change delivers the four the roadmap names.

## Next step

**Both gates pass.** Gate 1 `approved` (the retrospective artifact review the
tier correction owed), Gate 2 `confirmed` — all seven findings of round 1, plus
the minor eighth fixed with them.

`/git:merge add-demo-ui`, then `/opsx:archive`. The three screenshots in
`docs/images/` are committed; the corpus they were taken from is not, because
`.data/` is gitignored and `make demo` rebuilds it.

Local evidence, the way CI runs it (`FORCE_COLOR=1 CI=true`): `make check` 408
green, `make test-integration` 198 green, `make test-ui` 35 green, strict
validation 14/14, both `scripts/*_test.sh`, `sh -n` over every script.

## Blockers

None.
