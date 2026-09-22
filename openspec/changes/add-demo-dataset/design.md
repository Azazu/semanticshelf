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

4. **Two bounds, because there are two kinds of object.** A picture is bounded
   by `MAX_UPLOAD_BYTES` (20 MiB): that is what a picture may weigh. The
   manifest archive cannot be — it is 241 MiB — so it carries its own
   `ARCHIVE_MAX_BYTES`, set at 512 MiB, twice the size COCO publishes today and
   still a bound rather than a hope. Gate 1 caught the first draft applying the
   picture bound to "every request", which is impossible as written.
   The archive transfer is streamed to a staging name in the target directory
   and abandoned the moment it passes that bound; the staging file is removed
   and the command fails naming the bound, because without the manifest there
   is nothing to download. The same for its timeout and for a redirect: an
   archive failure is fatal, a picture failure is counted.
   Inside the archive, `annotations/instances_val2017.json` is read by exact
   name; a missing member, a member declaring an uncompressed size above
   `MEMBER_MAX_BYTES` (128 MiB, against a real member of ~46 MiB), or any other
   name, fails the command. Nothing is extracted to disk from the archive
   except that one member — read into memory, never written — so a zip entry
   named `../…` has nothing to escape into.
   The archive is kept in the target directory once complete, so a second run
   costs nothing. 241 MiB is the price of a manifest that carries per-picture
   licences, and the documentation says so.

5. **The unit of publication is the pair, and the pair is published by one
   rename of a directory.** The first confirmation of Gate 1 killed the earlier
   scheme: per-run staging names stop two runs from mixing bytes inside one
   file, but they do not stop `sidecar A, sidecar B, picture B, picture A` from
   leaving picture A beside sidecar B, and "both runs fetched the same bytes"
   was an assumption with no mechanism under it.

   So a picture and its sidecar are written into a staging directory
   `<into>/.staging/<id>.<pid>-<random>/` as `<id>.<ext>` and `<id>.json`, and
   published by `os.rename` of that directory to `<into>/pictures/<id>/`. A
   directory rename is atomic and moves both files at once, so the corpus never
   holds one run's picture beside another run's sidecar. If the target already
   exists the rename fails (`ENOTEMPTY`), the staging directory is removed, and
   the picture is counted as already present: the first publisher wins and its
   pair stays intact.

   The layout under `--into` is therefore three things: `pictures/` — the
   corpus, one directory per picture; `.staging/` — where runs build pairs; and
   the archive beside them. `demo-dataset index` imports `pictures/`
   recursively, so neither a staging directory nor the archive is ever a
   candidate for import, and the sidecar rule is unchanged: the sidecar lies
   beside its picture.

   A picture is streamed to `<staging dir>/<id>.<ext>.part`, abandoned if the
   response passes `MAX_UPLOAD_BYTES`, decoded through the same inspection an
   upload uses, and renamed inside its own staging directory; nothing of it is
   ever visible in the corpus until the directory rename. The archive is
   staged and renamed the same way, as a file.
   What a killed run leaves is exactly one thing: its own staging directory,
   which no other run reads, which no later run needs removed, and which the
   operator may delete at any time.
   The manifest's `file_name` is parsed for nothing but a sanity check that it
   matches the identifier; it never becomes a path.

   Rejected: flat `<into>/<id>.jpg` plus `<into>/<id>.json` with per-run
   staging names — the interleaving above. Rejected: making the sidecar carry
   the picture's content hash and having the import verify it — that would put
   a demo corpus's rule into the general folder import, which any folder with
   sidecars would then have to satisfy. Rejected: a lock file — a rename is
   already atomic, and a lock adds a failure mode of its own.

6. **A label is not a tag, so this change states the conversion.** COCO gives
   each picture zero or more annotations, each naming a category ("traffic
   light", "sports ball"). FR-TAG-1's normalisation is NFKC, trim and
   lower-case followed by a pattern that **rejects** a space — it does not
   slugify, and Gate 1 was right that the first draft claimed it did. So the
   conversion is this capability's own and is written down: runs of whitespace
   become `-`, and the result must then survive `normalise_tag` unchanged to be
   used. `traffic light` becomes `traffic-light` by the conversion and passes
   the normalisation; a label that still does not pass is dropped rather than
   failing the picture — a corpus without one tag is better than a corpus
   without a picture. The count is capped at the 32 tags an asset may carry.
   Rejected: dropping every multi-word category, which is half of COCO's
   eighty. Rejected: changing `normalise_tag` to slugify — it is the rule the
   API enforces on clients, and loosening it here would loosen it there.
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

   **The sidecar is opened exactly as a picture is**, which is the part Gate 1
   caught missing: relative to the descriptor of the directory the walk holds,
   with `O_NOFOLLOW | O_NONBLOCK | O_CLOEXEC`, and judged by `fstat` on that
   descriptor rather than by its path. A sidecar that is a symbolic link, a
   fifo, a directory or anything else that is not a regular file refuses its
   picture with that reason. This is not a new mechanism: it is the one change 7
   paid three Gate 2 rounds for, and reading a sidecar by path would have
   reopened every hole it closed.

8. **`make demo` is download, then index.** The import already finishes the
   work it created (change 7), so there is nothing extra to wait for: when
   `demo-dataset index` returns, the corpus is searchable, and the target says
   what it did.

9. **`httpx` becomes a runtime dependency.** It is already in the lock file for
   the tests. What this change needs from it — a per-request timeout,
   `follow_redirects=False`, and streaming with a size bound — is three
   keyword arguments against a few dozen lines of `urllib.request` plumbing in
   a path that handles remote bytes.

10. **A picture already in the store keeps what it has.** The duplicate rule is
    the content hash and it is global, so a corpus picture whose bytes are
    already stored — uploaded by hand, imported from a folder — produces no
    second asset, and the import does not rewrite the existing asset's tags or
    metadata from the sidecar. The demo provenance is therefore recorded on the
    assets this import creates, and nowhere else. Gate 1 caught the first draft
    promising a demo asset and an imported asset side by side, which the
    duplicate rule makes impossible.
    Rejected: merging the sidecar's provenance into an existing asset. It would
    make an import edit assets it did not create, which no import does today,
    and the surprise would be worse than the gap.

11. **The demo module is not part of the service.** It lives under
    `app/services/` with the rest of the use cases, but nothing the application
    factory imports reaches it, and a test asserts that: NFR-SEC-4's promise
    that the API and the worker make no outbound request is only worth
    something if something checks it.

## Applicability

| Question | Answer |
|---|---|
| Crash around an external effect | A picture and its sidecar are built inside a staging directory only that run writes, and enter the corpus by one `rename` of that directory. A crash therefore adds nothing to the corpus and leaves exactly one leftover: that staging directory, which no other run reads and no later run needs removed. NOT guaranteed: that the staging area is empty after a crash — only that nothing half-finished is ever in the corpus. |
| Concurrent writers | Two downloads publish by renaming their own directories: the corpus receives one run's pair whole, and the second rename fails on the existing directory, is counted as already present, and leaves the published pair untouched. A picture beside another run's sidecar is therefore impossible rather than unlikely. Two indexing runs are safe because the duplicate rule is the content hash. NOT guaranteed: that concurrent runs do not fetch the same picture twice, or that a dead run's staging directory is cleaned up by another run. |
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
