# A corpus anyone can search

**Risk-Tier:** high

Raised from the `medium` the technical specification and the roadmap declare.
Their reason — "egress from an operator command, not from the service"
(NFR-SEC-4) — is still true, but it is only half the picture: this command
reads a manifest written by someone else, follows URLs from it, and writes the
bytes that come back to disk. Remote input that becomes files is
security-sensitive input handling, which `AGENTS.md` lists as a `high` trigger.
The user raised the tier on 2026-09-22, before the proposal was written.

## Why

The search works and nobody can see it work. Trying it means finding a few
hundred pictures first, and a reviewer of this repository — or its author on a
clean machine — has none. `make demo` should be the whole distance between a
fresh clone and a corpus you can type "a red double-decker bus" at.

It is also what the README and the demo UI are built on: NFR-DOC-1 wants
screenshots of Search and Browse over a real corpus, and change 10 has nothing
to render until this one exists.

## What Changes

- **The dataset is chosen and recorded: COCO val2017.** FR-CLI-3 named two
  candidates and left the choice to this change. COCO wins on the one thing
  that matters here — its manifest carries a licence *per image*
  (`licenses[]` plus a `license` field on every image entry), so "licence
  check" is a filter this command runs rather than a sentence it prints. The
  annotations are CC BY 4.0; the pictures are Flickr users' and carry eight
  different licences, of which only some permit commercial use, so the command
  downloads only the permissively licensed ones. Unsplash Lite was rejected:
  its dataset terms forbid publishing or redistributing "any portion of the
  Licensed Data", which collides with the README screenshots NFR-DOC-1 asks
  for, and it costs a 700 MB download to reach 500 pictures.
- **New command `demo-dataset download [--count 500] [--into .data/demo]`**:
  fetches the annotation archive once, keeps only the images whose licence the
  manifest declares as permissive, downloads that many pictures, and writes
  each one beside a sidecar carrying its tags and its provenance. It prints the
  licence notice and what it skipped and why.
- **New command `demo-dataset index`**: runs the folder import over what was
  downloaded, so the demo corpus goes through exactly the pipeline an upload
  and `index-folder` go through — no second path into the store.
- **The folder import learns sidecars.** A file named after a picture beside it
  may carry that picture's tags and metadata; the run's own `--tags`/`--meta`
  still apply, and neither may overwrite the origin the import records. This is
  what makes `demo-dataset index` a plain `index-folder` rather than a private
  importer, and it is useful to anyone importing a folder that already has
  per-picture metadata.
- **`make demo`**: download, index, and wait for the queued work to finish, so
  the target ends with a corpus that is actually searchable (NFR-DOC-2).
- **`docs/reference/demo-dataset.md`**: which dataset, which licences were
  accepted and which refused, what is written into each asset's metadata, and
  how attribution is given — by link, because the COCO manifest records no
  author name (only the picture's page on Flickr). The provenance keys of
  FR-TAG-2 are written as far as the dataset supplies them: `author` is absent
  rather than invented.
- **`httpx` moves from the dev dependency group to the runtime dependencies.**
  No package enters the lock file that is not already in it: the test suite has
  used `httpx` since change 2, and change 10's UI will use it as its HTTP
  client. The alternative was `urllib.request` from the standard library, which
  for a `high`-tier download means hand-rolling what `httpx` states in one line
  — a per-request timeout, refusing redirects rather than following them, and
  streaming with a size bound.
- **The technical specification and the roadmap are amended**: FR-CLI-3 records
  the chosen dataset, and §7's row 9 and `openspec/ROADMAP.md` record the tier
  this change actually carries.

## Non-goals

- **Any network request from the API or the worker.** NFR-SEC-4 stands: the
  service's only outbound request remains the model download on first use. The
  demo module is a CLI-only path, and a test asserts the application does not
  import it.
- **Shipping images in the repository.** `.data/` is gitignored and stays that
  way; the corpus is downloaded, never committed. The README's screenshots are
  images of the UI, produced in change 16.
- **A general dataset importer.** One dataset, named and recorded. A second one
  would be another change, and the sidecar rule is what makes that cheap.
- **Captions.** COCO's caption annotations are a different archive and a
  different question (they would make text search look better than it is by
  matching a human's words rather than the picture); tags come from the object
  categories only.
- **Re-checking a licence that changed after the download.** The licence is
  recorded per asset at download time; a dataset that relicenses later is not
  something this command can notice.
- **The demo UI and the screenshots** (change 10 and change 16).

## Capabilities

### New Capabilities

- `demo-dataset`: the demo corpus — where it comes from, which pictures may be
  taken from it, what is written for each one, what bounds the download, and
  what the two commands promise about repeating them.

### Modified Capabilities

- `folder-indexing`: the import gains per-picture tags and metadata from a
  sidecar file, under the same normalisation, the same limits and the same rule
  that the recorded origin cannot be overwritten.

## Impact

- New: `app/services/demo_dataset.py` (the manifest, the licence filter and the
  bounded download), the `demo-dataset` commands in `app/cli.py`,
  `docs/reference/demo-dataset.md`, tests under `tests/unit/` and
  `tests/integration/`.
- Changed: `app/services/folder.py` (the sidecar), `app/cli.py`, `Makefile`
  (`demo`), `pyproject.toml` and `uv.lock` (`httpx` becomes a runtime
  dependency), `docs/explanation/requirements.md` (FR-CLI-3 and §7 row 9),
  `openspec/ROADMAP.md`, `docs/how-to/indexing.md` (the sidecar).
- Unchanged: the schema, every migration, the API and the worker path. Nothing
  in `app/api/` or `app/main.py` gains an import from the new module.
- Network: one archive from `images.cocodataset.org` and one request per
  picture to the same host, all over HTTPS, all from an operator command.
