# Handoff — add-demo-dataset

**Updated:** 2026-09-22 · claude
**State:** proposing
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

Gate 1, because the tier is `high`: `/gate-review add-demo-dataset 1`. The
mechanical floor already passes.

## Blockers

None.
