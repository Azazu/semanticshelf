# Tasks — add-demo-dataset

Tier `high`: every new check below names the input that makes it fail when the
check is removed, and that failure is demonstrated before the task is ticked.

## 1. The dependency and where the module may not be reached from

- [ ] 1.1 Move `httpx` from the dev group to the runtime dependencies:
  `uv remove --group dev httpx` then `uv add httpx`. Verify: `pyproject.toml`
  lists it under `dependencies` and no longer under `dev`, `make lock-check`
  passes, and `make check` is green — nothing new enters `uv.lock`, which the
  diff of that file shows.
- [ ] 1.2 `tests/unit/test_layering_demo.py`: building the application factory
  never imports the demo module. Verify: the test drops
  `app.services.demo_dataset` from `sys.modules`, calls `create_app`, and
  asserts the module is still absent. Demonstrated failing input: importing it
  from `app/api/assets.py` makes the test fail.

## 2. The manifest and what may be taken from it

- [ ] 2.1 `app/services/demo_dataset.py`: read `annotations/instances_val2017.json`
  out of the annotation archive by exact name, refusing a missing member, a
  member whose declared size passes the bound, and any other name (design
  decision 4). Verify: `tests/unit/test_demo_manifest.py` builds zips in the
  test — the good one, one without the member, one whose member declares a huge
  size, one whose member is named `../instances_val2017.json` — and asserts the
  first is read and the rest are refused with a message naming what was
  expected. Demonstrated failing input: dropping the exact-name check lets the
  `../` member through.
- [ ] 2.2 The licence filter: an allowlist of licence URLs, looked up through
  the manifest's own `licenses[]`, refusing NonCommercial, NoDerivs, an
  undefined id and a missing `license` field (design decision 2). Verify: unit
  tests over a synthetic manifest carrying all eight COCO licences plus an
  undefined id and an entry with no licence at all; each expected outcome is
  asserted by licence URL. Demonstrated failing input: removing the NoDerivs
  exclusion makes the test that asserts a thumbnail may not be made of an ND
  picture fail.
- [ ] 2.3 Tags from the picture's object categories, normalised by the rule
  FR-TAG-1 states, capped at the 32 tags an asset may carry, dropping a label
  that cannot become a tag (design decision 6). Verify: unit tests for a
  multi-word category (`traffic light` → `traffic-light`), for a picture with
  no annotations, for a label that normalises to nothing, and for more than 32
  distinct categories.
- [ ] 2.4 Read the real manifest once and record what it says: the eight
  licence entries, whether `val2017` image entries carry `flickr_url` beside
  `coco_url` (design.md, Open Questions), and the count of pictures under each
  accepted licence. Verify: the numbers appear in
  `docs/reference/demo-dataset.md` with the exact command that produced them,
  and the open question is struck from `design.md`.

## 3. The download

- [ ] 3.1 Fetch one picture: a per-request timeout, redirects refused rather
  than followed, the response abandoned past `MAX_UPLOAD_BYTES`, the bytes
  accepted only if they decode as a picture the service accepts, written to a
  temporary name and renamed into place (design decision 5). Verify:
  `tests/unit/test_demo_download.py` drives it through an `httpx.MockTransport`
  — a success, a redirect to another host, a response longer than the bound, a
  response that is not a picture — and asserts what landed in the directory
  each time. Demonstrated failing input: allowing redirects makes the redirect
  test write a file from the wrong host.
- [ ] 3.2 Every written name is built from the identifier the command validated
  and the extension it derived from the decoded bytes; nothing from the
  manifest builds a path. Verify: a unit test whose manifest entry has
  `file_name` `../../../../etc/passwd.jpg` asserts the picture is written
  inside the target directory under the identifier-derived name and that
  nothing exists outside it. Demonstrated failing input: using `file_name` for
  the output path makes the test fail on a file outside the directory.
- [ ] 3.3 The sidecar is written before the picture is renamed into place, so a
  picture in the directory always has one. Verify: a unit test that raises
  between the two steps asserts the directory holds no picture afterwards, and
  a second run then writes both.
- [ ] 3.4 Bounds and repetition: `--count` honoured and defaulted to 500,
  `--count 0` writing nothing, a picture already present skipped without a
  request, and a per-picture failure counted without ending the run. Verify:
  unit tests for each, with the transport asserting how many requests were
  made.

## 4. The sidecar in the folder import

- [ ] 4.1 `app/services/folder.py`: a picture's sidecar supplies its tags and
  metadata — tags added to the run's, metadata merged over the run's, the
  recorded origin winning over both, all through the normalisation and limits
  an upload applies (design decision 7). Verify: unit tests for the merge
  rules; `tests/integration/test_folder_import.py` gains a folder with
  sidecars and asserts the stored tags, metadata and origin.
- [ ] 4.2 A sidecar that cannot be read, is not an object, exceeds the limits
  or carries an unacceptable tag refuses its own picture with a reason naming
  the sidecar, and the run continues. Verify: an integration test with one good
  picture and one whose sidecar is broken asserts the summary and the store.
  Demonstrated failing input: skipping the sidecar validation stores a tag the
  service would refuse at upload.
- [ ] 4.3 A sidecar is never a candidate picture: it is not imported, not
  refused and not skipped-with-a-reason. Verify: the integration test above
  asserts the counters name only the pictures.
- [ ] 4.4 `docs/how-to/indexing.md` documents the sidecar with a run whose
  output is captured from a real command.

## 5. The commands and `make demo`

- [ ] 5.1 `demo-dataset download [--count 500] [--into .data/demo]` in
  `app/cli.py`: prints the licence notice on every run, and a summary of
  written, already present, refused for licence and failed. Verify: a CLI test
  with a stubbed transport asserts the notice and each counter, and
  `uv run semanticshelf demo-dataset download --help` shows the options in the
  form the documentation uses.
- [ ] 5.2 `demo-dataset index [--into .data/demo]`: runs the folder import over
  the directory, so the corpus enters the store through the ordinary pipeline
  and its queued work is finished when the command returns. Verify: an
  integration test imports a small prepared directory with sidecars and asserts
  the assets, their provenance and that no job is left waiting.
- [ ] 5.3 `make demo` runs the two commands in order. Verify: `make -n demo`
  shows exactly those commands, and the target appears in `make help`.

## 6. Documentation and the amendments this change owes

- [ ] 6.1 `docs/reference/demo-dataset.md`: the dataset, the eight licences and
  which four are accepted, why NoDerivs is not, the provenance keys written per
  asset, how attribution is given, the download sizes, and the exact commands.
  Verify: every command in it was run in the form shown and its output pasted
  from that run.
- [ ] 6.2 `docs/explanation/requirements.md`: FR-CLI-3 records the chosen
  dataset and the licence filter; §7's row 9 carries the tier this change
  actually has. Verify: both lines read as the implementation behaves, and
  `openspec validate --all --strict` passes.
- [ ] 6.3 `openspec/ROADMAP.md`: row 9 carries the same tier. Verify: the row
  matches `proposal.md`'s `**Risk-Tier:**` line.

## 7. Evidence

- [ ] 7.1 One real run against the live dataset with a small count
  (`uv run semanticshelf demo-dataset download --count 20 --into .data/demo`
  then `uv run semanticshelf demo-dataset index --into .data/demo`), its output
  captured into `docs/reference/demo-dataset.md`, and a search against the
  corpus in `docs/how-to/searching.md`'s form to show it is findable. Verify:
  the captured output is from that run, and the assets carry the provenance the
  spec requires.
- [ ] 7.2 `make check`, `make test-integration` and
  `openspec validate --all --strict` green, and every `scripts/*_test.sh` and
  `sh -n scripts/*.sh` run locally before the branch is pushed.
