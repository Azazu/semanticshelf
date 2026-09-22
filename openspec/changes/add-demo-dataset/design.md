# Design — add-demo-dataset

## Context

See `proposal.md` — Why. What the design has to work with:

- The store already has one honest way in: the upload pipeline, which
  `index-folder` reuses (change 7). Anything this change adds must go through
  it rather than beside it.
- The pictures come from a host nobody here controls, over a network, with a
  manifest written by someone else. Every value in that manifest is data, never
  an instruction and never a path.
- `MAX_UPLOAD_BYTES` (20 MiB), `MAX_IMAGE_PIXELS`, `MIN_IMAGE_SIDE` and the
  tag rules of FR-TAG-1 already say what a picture and a tag may be. This
  change adds no new limits of its own where one exists.

Measured today, so the numbers below are facts rather than estimates
(`curl -sSI`, 2026-09-22):

| Object | Size |
|---|---|
| `annotations/annotations_trainval2017.zip` | 252 907 541 B (241 MiB) |
| one `val2017` picture (`000000039769.jpg`) | 173 131 B |

## Goals / Non-Goals

Goals beyond the proposal's scope statement:

- Every byte that reaches the disk was fetched over TLS that verified, decoded
  as a picture the service accepts, and arrived under a name this repository
  chose.
- A run that dies halfway leaves nothing a later run can mistake for a finished
  download.
- The corpus is reproducible: the same count against the same dataset gives the
  same pictures, in the same order, because the manifest is ordered and the
  filter is deterministic.

Non-goals at the design level: parallel downloads (one at a time is fast enough
for 500 pictures and keeps the failure story simple), resumable partial files
(a picture is fetched again from the start), and any caching beyond "the file
is already there".

## Decisions

1. **COCO val2017, and the licence is a filter rather than a sentence.**
   FR-CLI-3 left the choice here. The manifest carries `licenses[]` — eight
   entries of `{url, id, name}` — and every image entry carries a `license` id,
   which was verified against a real COCO manifest before this was written
   (`image_info_test2017.json`, the small archive with the same shape). So the
   command can decide *per picture* instead of declaring something about the
   dataset as a whole.
   Rejected: Unsplash Lite. Its terms forbid publishing or redistributing "any
   portion of the Licensed Data", which is hard to reconcile with the README
   screenshots NFR-DOC-1 wants, and its manifest costs 700 MB to reach 500
   pictures.

2. **The accepted licences are matched by URL, and NoDerivs is refused.**
   The allowlist is the set of licence URLs, not ids: an id is an index into
   that dataset's own array, a URL states the licence. Accepted:
   `by/2.0`, `by-sa/2.0`, Flickr Commons "No known copyright restrictions",
   and "United States Government Work". Refused: the three NonCommercial ones,
   and **NoDerivs** — which permits redistribution but not derivative works,
   and the first thing this service does with a stored picture is re-encode a
   thumbnail of it (FR-AST-6). A licence absent from the manifest, or an id the
   manifest does not define, is refused too.
   Rejected: accepting ND because "we only show it" — the thumbnail exists
   whether or not it is shown.

3. **Every request goes to `https://s3.amazonaws.com/images.cocodataset.org/…`,
   because the documented host has no certificate for its own name.**
   `curl -I https://images.cocodataset.org/…` fails with
   `SSL: no alternative certificate subject name matches target hostname`, and
   the manifest's own `coco_url` values are plain `http://`. The bucket answers
   the same objects at the path-style S3 endpoint with a certificate that
   verifies, which was checked for the archive and for a picture before this
   was written. So the command holds one base URL of its own and builds every
   address from it plus a validated identifier; the manifest's `coco_url` is
   read for its *filename only* and never used as an address.
   Rejected: plain HTTP with a pinned checksum of the archive — it would leave
   every picture unauthenticated, and a pinned checksum breaks the day COCO
   republishes the archive. Rejected: `flickr_url`, which is a third party's
   hotlink and rots.

4. **The archive is read for one member, by exact name, under a bound.**
   `annotations/instances_val2017.json` is extracted from the zip by exact
   name; a missing member, a member whose declared size exceeds the bound, or a
   member name that is not exactly that one, fails the command. Nothing is
   extracted to disk from the archive except that one member, so a zip entry
   named `../…` has nothing to escape into.
   The archive itself is kept in the target directory, so a second run costs
   nothing. 241 MiB is the price of a manifest that carries per-picture
   licences, and the documentation says so.

5. **A picture is written only after it is whole and only under a name we
   chose.** The bytes are streamed to a temporary name in the target directory,
   abandoned if the response passes `MAX_UPLOAD_BYTES`, decoded through the
   same inspection an upload uses, and only then renamed into place as
   `<image id>.<extension of the detected format>`. The sidecar is written
   before that rename, so a picture in the directory always has its sidecar.
   The manifest's `file_name` is parsed for nothing but a sanity check that it
   matches the identifier; it never becomes a path.
   Rejected: writing straight to the final name and deleting on failure — a
   crash between the two leaves a truncated file that the next run would see as
   done.

6. **Tags are the object categories, normalised, and a label that cannot become
   a tag is dropped.** COCO gives each picture zero or more annotations, each
   naming a category ("traffic light", "sports ball"). The tag is that name
   normalised by FR-TAG-1's rule; a category that cannot survive it is dropped
   rather than failing the picture — a corpus without one tag is better than a
   corpus without a picture. The count is capped at the 32 tags an asset may
   carry.
   Rejected: COCO's caption annotations. They are a human's sentence about the
   picture, and indexing them as tags would flatter the search: a text query
   would be matching a caption's words, not the picture.

7. **The sidecar is `<picture>.json` beside the picture, and the folder import
   reads it.** This is what makes `demo-dataset index` a plain folder import
   instead of a private path into the store. Rules, all of which fall out of
   what already exists: it is read through the same JSON-object and 8 KB limit
   as `--meta`, its tags through the same normalisation as `--tags`, its
   metadata merges over the run's, its tags add to the run's, and the recorded
   origin wins over both. A sidecar that cannot be read refuses its own picture
   and nothing else. The file is not a candidate picture — the walk knows a
   sidecar by its name, not by trying to decode it.
   Rejected: one manifest file for the whole folder — it would be a second
   format to validate and would make a partially downloaded corpus
   unimportable.

8. **`make demo` is download, then index.** The import already finishes the
   work it created (change 7), so there is nothing extra to wait for: when
   `demo-dataset index` returns, the corpus is searchable, and the target says
   what it did.

9. **`httpx` becomes a runtime dependency.** It is already in the lock file for
   the tests. What this change needs from it — a per-request timeout,
   `follow_redirects=False`, and streaming with a size bound — is three
   keyword arguments against a few dozen lines of `urllib.request` plumbing in
   a path that handles remote bytes.

10. **The demo module is not part of the service.** It lives under
    `app/services/` with the rest of the use cases, but nothing the application
    factory imports reaches it, and a test asserts that: NFR-SEC-4's promise
    that the API and the worker make no outbound request is only worth
    something if something checks it.

## Applicability

| Question | Answer |
|---|---|
| Crash around an external effect | A download writes to a temporary name in the target directory and renames into place after the bytes decoded; the sidecar is written before that rename. A crash therefore leaves either nothing or a complete pair, and the next run resumes by skipping what is there. The archive is written the same way. |
| Concurrent writers | Two downloads into one directory duplicate work but cannot corrupt: each file appears by rename. Two indexing runs are safe because the store's duplicate rule is the content hash, and both see the same pictures. |
| Empty / zero / null inputs | `--count 0` writes nothing and still prints the notice; a manifest whose permissive pictures are fewer than the count writes what there is and says so; indexing an empty or missing directory reports it rather than failing. |
| Deletion / expiry | The commands never delete: `--into` is written to, never cleaned. A picture that vanishes from the dataset is a per-picture failure, counted, and the run continues. |
| Idempotent retries | A retried download skips every picture already present; a retried index creates no second asset because the pipeline dedupes on the content hash. Both are safe to run any number of times. |
| Authorization boundary | n/a — the service has no authentication (D12). The boundary that matters here is the network one: one host, no credentials sent, and redirects refused rather than followed. |
| Money rounding | n/a. |

## Risks / Trade-offs

- **241 MiB for a manifest** → Cached in the target directory and downloaded
  once; the documentation states the cost, and `--count` does not change it.
- **The dataset's host or layout changes** → Every address is built from one
  base URL and one member name, both constants in one module; a change is a
  one-line fix and a failing command rather than a silent wrong corpus.
- **A picture that no longer exists, or a slow host** → per-picture failures
  are counted and reported, never fatal; the run continues and the summary says
  how many were lost.
- **The licence array could gain an entry COCO later reuses** → the allowlist
  is by URL, and an unknown URL is refused rather than assumed permissive.
- **Attribution without an author name** → COCO's image entries carry no
  author; attribution is by the picture's address, recorded per asset and
  explained in `docs/reference/demo-dataset.md`. This is what the dataset makes
  possible, and the document says so rather than implying more.
- **The corpus is object photography** → search demos will look like "a red
  bus" rather than "a moody landscape". Accepted: the licences are checkable,
  which matters more for a public repository.

## Migration Plan

Nothing to migrate: no schema change, no data change, no API change. The
dependency move is picked up by `uv sync`. A deployment that never runs the
command is unaffected, which is the point of keeping it out of the service.

## Open Questions

- Whether `val2017`'s image entries carry `flickr_url` beside `coco_url` (the
  `test2017` manifest, which was the one small enough to check while planning,
  does not). It decides only which address is recorded as the picture's own,
  and the first implementation task reads the real manifest and settles it.
