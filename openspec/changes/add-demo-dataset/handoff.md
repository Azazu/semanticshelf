# Handoff — add-demo-dataset

**Updated:** 2026-09-22 · claude
**State:** implementing
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

**Gate 1 passed** (Confirmation 2 of round 1, commit `f03c61a`, all five
findings confirmed). The contract is settled before a line of it exists:

- three bounds, one per kind of object, with an archive failure fatal and a
  picture failure counted;
- the sidecar read through the descriptor the walk holds, never by path;
- a label converted to a tag by this change's own rule, leaving the service's
  normalisation alone;
- a picture whose bytes are already stored left exactly as it is;
- the picture and its sidecar published as one directory rename, so a
  mismatched pair is impossible rather than unlikely.

Run: `/opsx:apply add-demo-dataset`. 26 tasks in seven groups; the first is the
dependency move and the layering test, and nothing in the service may import
the new module.

## Blockers

None.
