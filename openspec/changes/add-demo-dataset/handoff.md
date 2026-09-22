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

Gate 1 round 1 returned six findings — two blockers, three majors, one minor —
and all six were real. Fixed:

1. The 241 MiB archive was bounded by the picture's 20 MiB, which is
   impossible. Two bounds now: `MAX_UPLOAD_BYTES` for a picture,
   `ARCHIVE_MAX_BYTES` for the archive, `MEMBER_MAX_BYTES` for the member; an
   archive failure is fatal where a picture failure is counted, and the
   staging file is removed either way.
2. The sidecar was to be read by path, which would have reopened every hole
   change 7 closed. It is opened relative to the walk's directory descriptor
   with `O_NOFOLLOW | O_NONBLOCK | O_CLOEXEC` and judged by `fstat`, with
   failing inputs for a symlink sidecar and one swapped after the picture was
   listed.
3. `traffic light` → `traffic-light` is not FR-TAG-1 normalisation — that rule
   rejects a space rather than slugifying it. The conversion is now this
   change's own, stated in the spec and the design, and the normalisation is
   left alone.
4. "A demo asset beside an imported one" cannot exist: the content hash makes
   one asset. The spec now says what actually happens — the existing asset is
   reported and left untouched, and the demo provenance lands only on assets
   this import creates.
5. The applicability table claimed more than the mechanism gave. It now names
   the staging scheme (`<final>.<pid>-<random>.part`), the two recoverable
   leftovers, and what is NOT guaranteed, with a concurrency test for the claim
   that remains.
6. Task 2.1 said "passes the bound" where the rule is "exceeds".

Run: `/gate-review add-demo-dataset 1 confirm 1`.

## Blockers

None.
