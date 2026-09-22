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
  member whose declared uncompressed size **exceeds** `MEMBER_MAX_BYTES`, and
  any other member name; nothing is extracted to disk (design decision 4).
  Verify: `tests/unit/test_demo_manifest.py` builds zips in the test — the good
  one, one without the member, one whose member declares a size above the
  bound, one whose member is named `../instances_val2017.json` — and asserts
  the first is read and the rest are refused with a message naming what was
  expected. Demonstrated failing input: dropping the exact-name check lets the
  `../` member through; dropping the size check reads a member above the bound.
- [ ] 2.2 The licence filter: an allowlist of licence URLs, looked up through
  the manifest's own `licenses[]`, refusing NonCommercial, NoDerivs, an
  undefined id and a missing `license` field (design decision 2). Verify: unit
  tests over a synthetic manifest carrying all eight COCO licences plus an
  undefined id and an entry with no licence at all; each expected outcome is
  asserted by licence URL. Demonstrated failing input: adding the NoDerivs URL
  to the allowlist makes the test that asserts ND is refused fail.
- [ ] 2.3 The label-to-tag conversion this change owns (design decision 6):
  runs of whitespace become `-`, the result must then pass `normalise_tag`
  unchanged, a label that does not is dropped, and the count is capped at
  `MAX_TAGS`. Verify: unit tests for `traffic light` → `traffic-light`, for a
  picture with no annotations, for a label that cannot pass (asserted against
  `normalise_tag` itself, so the test fails if the two rules drift apart), and
  for more than 32 distinct categories. Demonstrated failing input: passing a
  raw multi-word label to `normalise_tag` raises `TagError`, which is why the
  conversion exists.
- [ ] 2.4 Read the real manifest once and record what it says: the eight
  licence entries, whether `val2017` image entries carry `flickr_url` beside
  `coco_url` (design.md, Open Questions), and the count of pictures under each
  accepted licence. Verify: the numbers appear in
  `docs/reference/demo-dataset.md` with the exact command that produced them,
  and the open question is struck from `design.md`.

## 3. The transfers, each bounded by its own bound

- [ ] 3.1 Fetch one picture: a per-request timeout, redirects refused rather
  than followed, the response abandoned past `MAX_UPLOAD_BYTES`, the bytes
  accepted only if they decode as a picture the service accepts (design
  decisions 4 and 5). Verify: `tests/unit/test_demo_download.py` drives it
  through an `httpx.MockTransport` — a success, a redirect to another host, a
  response longer than the bound, a response that times out, a response that is
  not a picture — and asserts what landed in the directory each time and that
  the run continued. Demonstrated failing input: allowing redirects makes the
  redirect test write a file from the wrong host.
- [ ] 3.2 Fetch the archive under `ARCHIVE_MAX_BYTES`, with its own timeout and
  the same refusal of redirects, and with an archive failure ending the command
  instead of being counted (design decision 4). Verify: unit tests through the
  same stub for a streamed response that passes the bound, one that times out
  and one that redirects; each asserts the command failed naming the bound or
  the host, that no staging file survives, and that no picture was requested.
  Demonstrated failing input: applying `MAX_UPLOAD_BYTES` to the archive makes
  the ordinary 241 MiB archive fail, which is the mistake Gate 1 named.
- [ ] 3.3 Every written name is built from the identifier the command validated
  and the extension it derived from the decoded bytes; nothing from the
  manifest builds a path. Verify: a unit test whose manifest entry has
  `file_name` `../../../../etc/passwd.jpg` asserts the picture is written
  inside the target directory under the identifier-derived name and that
  nothing exists outside it. Demonstrated failing input: using `file_name` for
  the output path makes the test fail on a file outside the directory.
- [ ] 3.4 Staging and publication: every file is written as
  `<final>.<pid>-<random>.part` and renamed once complete, the sidecar before
  its picture (design decision 5). Verify: unit tests assert the staging name
  carries the process id, that a failure between the two steps leaves no
  picture under a final name, and that a second run then writes both files.
  Demonstrated failing input: writing straight to the final name leaves a
  truncated picture that the skip rule would treat as finished.
- [ ] 3.5 The concurrency claim of the applicability table, tested rather than
  asserted: two downloads writing the same pictures into one directory. Verify:
  a unit test runs two downloads against the same target with a transport that
  serves the same bytes, and asserts every final file is complete, every
  picture has its sidecar, neither run raised, and no `.part` file is left
  behind by a run that finished.
- [ ] 3.6 Bounds and repetition: `--count` honoured and defaulted to 500,
  `--count 0` writing nothing but still printing the notice, a picture already
  present skipped without a request, and a per-picture failure counted without
  ending the run. Verify: unit tests for each, with the transport asserting how
  many requests were made.

## 4. The sidecar in the folder import

- [ ] 4.1 `app/services/folder.py`: a picture's sidecar supplies its tags and
  metadata — tags added to the run's, metadata merged over the run's, the
  recorded origin winning over both, all through the normalisation and limits
  an upload applies (design decision 7). Verify: unit tests for the merge
  rules; `tests/integration/test_folder_import.py` gains a folder with
  sidecars and asserts the stored tags, metadata and origin.
- [ ] 4.2 The sidecar is opened the way a picture is: relative to the
  descriptor of the directory the walk holds, with `O_NOFOLLOW | O_NONBLOCK |
  O_CLOEXEC`, and judged by `fstat` on that descriptor — never by its path
  (design decision 7). Verify: integration tests for a sidecar that is a
  symbolic link (pointing outside the folder), for one that is a fifo, and for
  one replaced between the picture being listed and the sidecar being read;
  each asserts the picture is refused with that reason, that nothing outside
  the folder was read, and that the run did not block. Demonstrated failing
  input: opening the sidecar with `open(path)` reads through the symbolic link,
  which the first of those tests catches.
- [ ] 4.3 A sidecar that can be opened but not accepted — not an object, over
  the limits, an unacceptable tag — refuses its own picture with a reason
  naming the sidecar, and the run continues. Verify: an integration test with
  one good picture and one whose sidecar is broken asserts the summary and the
  store. Demonstrated failing input: skipping the sidecar validation stores a
  tag the service would refuse at upload.
- [ ] 4.4 A sidecar is never a candidate picture: it is not imported, not
  refused and not skipped-with-a-reason. Verify: the integration test above
  asserts the counters name only the pictures.
- [ ] 4.5 `docs/how-to/indexing.md` documents the sidecar with a run whose
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
- [ ] 5.3 A corpus picture whose bytes are already stored creates no second
  asset and changes nothing on the existing one (design decision 10). Verify:
  an integration test stores a picture first — once by upload and once by an
  ordinary folder import with its own tags — then runs the demo import over a
  directory holding the same bytes with a sidecar, and asserts one asset, its
  tags and metadata unchanged, and the run reporting it as already stored.
- [ ] 5.4 `make demo` runs the two commands in order. Verify: `make -n demo`
  shows exactly those commands, and the target appears in `make help`.

## 6. Documentation and the amendments this change owes

- [ ] 6.1 `docs/reference/demo-dataset.md`: the dataset, the eight licences and
  which four are accepted, why NoDerivs is not, the label-to-tag conversion,
  the provenance keys written per asset, how attribution is given, the download
  sizes and bounds, and the exact commands. Verify: every command in it was run
  in the form shown and its output pasted from that run.
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
