# Handoff — add-demo-dataset

**Updated:** 2026-09-22 · claude
**State:** fixing-g1
**Branch:** change/add-demo-dataset

## Done this session

Branch, scaffold and all four planning artifacts. Two decisions the user made
before anything was written:

- **The dataset is COCO val2017.** FR-CLI-3 left the choice here and named two
  candidates. COCO's manifest carries a licence per picture, so the licence
  check is a filter rather than a sentence; Unsplash Lite's terms forbid
  publishing any portion of the data, which collides with the README
  screenshots NFR-DOC-1 wants.
- **The tier is `high`**, raised from the `medium` the specification and the
  roadmap declare. Their reason holds — the egress is an operator's, not the
  service's — but the command also turns remote bytes into files, which is
  security-sensitive input handling.

Two things the planning found by checking rather than assuming:

- `images.cocodataset.org` has **no valid certificate for its own name**
  (`SSL: no alternative certificate subject name matches target hostname`), and
  the manifest's own addresses are plain `http://`. The same objects answer
  over `https://s3.amazonaws.com/images.cocodataset.org/…` with a certificate
  that verifies — checked for the archive and for a picture.
- The manifest's shape was verified against a real COCO file (the small
  `image_info_test2017` archive): `licenses[]` of eight entries, a `license` id
  on every image, and **no author field** — so attribution is by the picture's
  address, and `author` is absent rather than invented.

## Next step

Confirmation 1 of Gate 1 confirmed four findings and refused the fifth, with a
concrete interleaving: per-run staging names stop two runs from mixing bytes
inside one file, but `sidecar A, sidecar B, picture B, picture A` still leaves
one run's picture beside the other run's sidecar, and "both runs fetched the
same bytes" was an assumption with no mechanism under it.

The mechanism is now the pair rather than the file: a picture and its sidecar
are built in `<into>/.staging/<id>.<pid>-<random>/` and published by one
`os.rename` of that directory to `<into>/pictures/<id>/`. A directory rename
moves both files at once, so the mismatched pair is impossible rather than
unlikely; a target that exists makes the rename fail, the staging directory is
removed and the picture is reported as already present. The layout under
`--into` is `pictures/`, `.staging/` and the archive, and `demo-dataset index`
imports `pictures/` recursively, so neither the staging area nor the archive is
ever a candidate for import. The concurrency test now serves **different** bytes
and labels from the two runs, so it demonstrates the guarantee instead of
assuming it.

Run: `/gate-review add-demo-dataset 1 confirm 1`.

## Blockers

None.
