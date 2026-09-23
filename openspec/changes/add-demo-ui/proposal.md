# Something to look at

**Risk-Tier:** high

Raised twice. The roadmap declares `low`; this change was first proposed as
`medium` on the reasoning that it touches nothing in the service. Gate 2 was
right that the reasoning does not matter: `AGENTS.md` says a change touching
**file uploads or dependencies** is `high` tier, and this one adds two
dependency groups and a page that uploads a file. It also deletes assets
irreversibly on a click, which the tier table names on its own.

So it is `high`: Gate 1 on the artifacts as well as Gate 2 on the code, an
applicability table in `design.md`, a demonstrated failing input for every new
check, and the security-sensitive flag in the commit body and the handoff.

## Why

Everything the service does is reachable only by `curl`. A reviewer of this
repository — or its author in an interview — cannot see a search happen, and
`docs/reference/demo-dataset.md` ends with a corpus nobody can look at.

The pieces are all there: `GET /search/text` with scores and a threshold, the
listing with tag and index-status filters, upload, `/tags`, `/stats`, `/ready`,
and `make demo` to fill a machine from nothing. This change puts a face on
them.

## What Changes

- **A Streamlit application in `ui/`**, its own package with its own dependency
  group, talking to the service over HTTP and nothing else. Four pages, which
  are the ones the roadmap names for this change:
  - **Search** — a text box, a grid of thumbnails with their scores, a
    `min_score` slider, a tag filter, and a "more" button that pages with
    `offset`;
  - **Browse** — a paginated grid, a tag cloud from `/tags`, an asset's detail
    with its metadata, its index status and its full-size picture, and a delete
    that asks first;
  - **Upload** — a file, tags and metadata, with the service's refusal shown as
    the service worded it;
  - **Status** — `/ready`, the counts per index status and the oldest waiting
    work, from `/stats`.
- **One setting, `API_BASE_URL`**, defaulting to the port `make run` uses. The
  UI knows no database URL, no media root and no model: it cannot reach them,
  and a test asserts that nothing in `ui/` imports `app.*`.
- **Every picture comes from the API by URL** (`links.file`, `links.thumbnail`),
  never from the filesystem — the UI does not know where anything is stored.
- **A refusal is shown as the service explained it**: problem details rendered
  as their `title` and `detail`, never a traceback, and never a bare status
  code.
- **`make ui`** runs it; **`make test-ui`** runs the smoke tests the technical
  specification asks for (`streamlit.testing` against a stubbed API) under a new
  `ui` marker, after `uv sync --group ui`. They stay out of `make check` for the
  same reason the model tests do: the group is not installed in the environment
  that runs the gate floor.
- **Screenshots are produced by a script**, not by hand: `make screenshots`
  brings up the API and the UI against the demo corpus, drives a headless
  browser and writes `docs/images/search.png`, `browse.png` and `status.png`.
  That is this change's exit criterion in the roadmap, and a recipe in a how-to
  would have rotted the first time a page moved.
- **A how-to page** for running the UI, and what each page is for.

## Non-goals

- **The "Find similar" page.** FR-UI-1 names five pages; `/similar` and image
  search arrive with DINOv2 in change 11, and the page arrives with them. The
  roadmap's row for this change names the other four, and this change delivers
  exactly those.
- **The README.** NFR-DOC-1 assembles it in change 16; this change produces the
  images it will use and nothing else in it.
- **A Compose service for the UI** — that is change 15, with the rest of the
  stack.
- **Any change to the service.** No endpoint, no schema, no setting of the API's
  gains anything here; if a page wants something the API does not offer, the
  page does without it and the proposal says so.
- **Teaching CI to run the new markers.** CI configuration is verifier
  infrastructure, which `AGENTS.md` puts at `high` tier with its own demanded
  evidence; wiring `ui` and `screenshots` into the workflow belongs in a change
  that is about that.
- **Authentication, multi-user state, or anything a person could break the
  service with.** The UI is a client with no privileges of its own.

## Capabilities

### New Capabilities

- `demo-ui`: the demonstration interface — what it may talk to, what its pages
  promise a person, how a refusal reaches them, and what it is forbidden to
  know.

### Modified Capabilities

None. The service is untouched.

## Impact

- New: `ui/` (the Streamlit app and its pages), `tests/ui/` (the smoke tests
  under the `ui` marker), `scripts/screenshots.py` and `make screenshots`,
  `docs/how-to/demo-ui.md`, `docs/images/*.png`.
- Changed: `pyproject.toml` (a `ui` dependency group with Streamlit, and a
  `screenshots` group with Playwright; a new pytest marker), `Makefile`
  (`ui`, `test-ui`, `screenshots`), `AGENTS.md`'s layout note if the shape of
  `ui/` differs from the one line it carries now.
- Unchanged: `app/`, every migration, every endpoint. The gate floor does not
  grow: neither new group is installed for `make check`.
- New dependencies, both in groups of their own and neither reaching the API
  image: **Streamlit**, which the technical specification chose for this job
  (D11) and which brings its own tree; **Playwright**, only to press a button
  and take a picture — it is the smallest way to get a real screenshot of a real
  page, and the alternative was a recipe for a human to follow every time a page
  changes.
