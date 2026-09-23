# The demo corpus

A search engine with nothing in it cannot be shown to anyone. `make demo`
fetches a few hundred pictures, indexes them, and leaves a corpus you can type
a description at.

Every number and every output on this page came from a real run — the corpus
and the licence counts on 2026-09-22, the third command and the picture search
below on 2026-09-23, after the second model arrived. The commands are in the
form they were run in.

## The dataset

**COCO val2017** — 5 000 photographs with object annotations, published by the
COCO Consortium.

- **The annotations** (the manifest this command reads) are licensed CC BY 4.0
  by the COCO Consortium.
- **The pictures are not the Consortium's.** They belong to their
  photographers, were published on Flickr, and each carries its own licence.
  The manifest records which, so this command decides picture by picture rather
  than making a claim about the dataset as a whole.

Unsplash Lite, the other candidate the technical specification named, was
rejected: its dataset terms forbid publishing or redistributing "any portion of
the Licensed Data", which cannot be reconciled with the README screenshots of a
public portfolio, and it costs a 700 MB download to reach 500 pictures.

## Which pictures are taken

The manifest declares eight licences. Four permit reuse; four do not, and their
pictures are never downloaded. Counted from the real manifest:

| id | Licence | Pictures | Taken |
|---|---|---|---|
| 1 | Attribution-NonCommercial-ShareAlike | 1 431 | no |
| 2 | Attribution-NonCommercial | 630 | no |
| 3 | Attribution-NonCommercial-NoDerivs | 1 414 | no |
| 4 | Attribution (CC BY 2.0) | 857 | **yes** |
| 5 | Attribution-ShareAlike (CC BY-SA 2.0) | 417 | **yes** |
| 6 | Attribution-NoDerivs | 246 | no |
| 7 | No known copyright restrictions (Flickr Commons) | 5 | **yes** |
| 8 | United States Government Work | 0 | **yes** |

**1 279 of the 5 000 are available**; the other 3 721 are refused and counted.

**NoDerivs is refused although it permits redistribution.** The first thing this
service does with a stored picture is re-encode a thumbnail of it (FR-AST-6),
and a thumbnail is a derivative work.

The decision is made on the licence's **URL**, looked up through the manifest's
own table: an id is that file's numbering, a URL states the licence. A picture
with no licence, or one whose id the table does not define, is refused too.

## What is recorded for each picture

Tags come from the picture's object categories. A label is not a tag — the
service's rule (FR-TAG-1) lower-cases and trims and then refuses a space — so
the command converts first: runs of whitespace become `-`, and the result has to
pass that same rule unchanged. `traffic light` becomes `traffic-light`; a label
that still cannot pass is dropped rather than costing the picture.

The provenance is the keys FR-TAG-2 reserves, as far as COCO supplies them:

```json
{
  "meta": {
    "dataset": "coco-val2017",
    "dataset_id": "122745",
    "licence": "http://creativecommons.org/licenses/by/2.0/",
    "source_url": "http://farm2.staticflickr.com/1028/1143164889_bf35e363ed_z.jpg"
  },
  "tags": ["stop-sign"]
}
```

**There is no `author` key, because the manifest has no author name** — not for
one picture out of 5 000. Attribution is therefore by address: `source_url` is
the original on Flickr, which carries the photograph's Flickr id, and the key is
absent rather than invented.

## What it costs, and what bounds it

| Object | Size | Bound |
|---|---|---|
| the annotation archive | 252 907 541 B (241 MiB) | `ARCHIVE_MAX_BYTES`, 512 MiB |
| the manifest inside it | 19 987 840 B (19 MiB) | `MEMBER_MAX_BYTES`, 128 MiB |
| one picture | 166 KiB on average over the twenty fetched | `MAX_UPLOAD_BYTES`, 20 MiB |

The archive is fetched once and kept, so a second run costs nothing for it. A
picture that is already there is not fetched again.

Every request carries a timeout and is **refused rather than followed** when it
is answered with a redirect to another host. A picture that fails is counted and
the run continues; the archive failing ends the run, because without the
manifest there is nothing to fetch.

Every request goes to `https://s3.amazonaws.com/images.cocodataset.org/…` —
the bucket's path-style address — because the host COCO documents,
`images.cocodataset.org`, serves no certificate for its own name, and the
addresses inside the manifest are plain `http://`. Nothing from the manifest is
ever fetched, and no name from it ever becomes a path: every file is named from
the identifier the command validated and the extension the decoded bytes earned.

## The two commands

```console
$ uv run semanticshelf demo-dataset download --count 20 --into .data/demo
coco-val2017: the annotations are CC BY 4.0 (COCO Consortium); the pictures belong to
their photographers and are taken only under these licences:
  http://creativecommons.org/licenses/by-sa/2.0/
  http://creativecommons.org/licenses/by/2.0/
  http://flickr.com/commons/usage/
  http://www.usa.gov/copyright.shtml
Attribution is by address: the manifest records no author name.
Details: docs/reference/demo-dataset.md
written:            20
already present:    0
refused (licence):  3721
failed:             0
```

That run took 30 seconds, of which the archive was most of it.

```console
$ uv run semanticshelf demo-dataset index --into .data/demo
folder: /home/you/semanticshelf/.data/demo/pictures
created: 20
already stored: 0
refused: 0
skipped: 0
indexed: 20
still queued: 0
failed: 0
```

A third command ends the run:

```console
$ uv run semanticshelf index missing
model: clip-vit-l14
queued: 0
skipped (failed work): 0
indexing: nothing to do
model: dinov2-large
queued: 0
skipped (failed work): 0
indexing: nothing to do
```

Nothing to do, because the import above queued every enabled model — which is
exactly what it should say. It earns its place for the corpus you imported
*before* a model was enabled: those assets have no vector for it, nothing will
give them one on its own, and this is the command that does. It is idempotent,
so running it on a corpus that needs nothing costs one query per model.

`make demo` is those three in order, with `DEMO_COUNT` (500) and `DEMO_ROOT`
(`.data/demo`).

Afterwards the corpus is searchable, through the ordinary endpoint. The answer
below is the one the service gave, with each asset trimmed to the fields that
identify it and the scores rounded, as `docs/how-to/searching.md` trims them:

```console
$ curl -s "http://127.0.0.1:8000/api/v1/search/text?q=a+red+stop+sign+at+a+junction&limit=3" \
    | jq '{items: [.items[] | {name: .asset.original_filename, tags: .asset.tags,
                              score: (.score * 1000 | round / 1000)}], has_more, model}'
{
  "items": [
    { "name": "000000297343.jpg", "tags": ["stop-sign"],            "score": 0.235 },
    { "name": "000000122745.jpg", "tags": ["stop-sign"],            "score": 0.206 },
    { "name": "rose.png",         "tags": ["garden","flower","red"], "score": 0.194 }
  ],
  "has_more": true,
  "model": "clip-vit-l14"
}
```

Both pictures COCO tagged `stop-sign` come first, and they were found by the
words, not by the tags: nothing about the query touches them.

And by a picture, which is the other half of what the corpus is for — here one
of those stop signs is the query, so it scores 1 against itself and the other
one follows:

```console
$ curl -s -X POST "http://127.0.0.1:8010/api/v1/search/image" \
    -F "file=@.data/demo/pictures/297343/000000297343.jpg" -F "limit=2" \
    | jq -c '{items: [.items[] | {name: .asset.original_filename, tags: .asset.tags,
                                  score: (.score * 1000 | round / 1000)}], model}'
{"items":[{"name":"000000297343.jpg","tags":["stop-sign"],"score":1},
          {"name":"000000122745.jpg","tags":["stop-sign"],"score":0.37}],
 "model":"dinov2-large"}
```

That run had the service on `APP_PORT=8010`; the default is 8000. What each
kind of search is *for*, and what a score means in each, is in
[`../how-to/searching.md`](../how-to/searching.md).

## The layout on disk

```text
.data/demo/
├── annotations_trainval2017.zip   the manifest archive, fetched once
├── pictures/                      the corpus — this is what is imported
│   └── 122745/
│       ├── 000000122745.jpg
│       └── 000000122745.json      its tags and provenance
└── .staging/                      where a run builds a pair before publishing it
```

One directory per picture, because **a picture and its sidecar are published
together or not at all**: both are built under `.staging/` and enter the corpus
by a single rename of that directory. Two runs at once therefore cannot leave
one run's picture beside another run's sidecar, and a run that is killed leaves
nothing in the corpus — only its own staging directory, which nothing else reads
and which is safe to delete at any time.

`demo-dataset index` imports `pictures/` alone, recursively, so neither the
archive nor the staging area is ever a candidate for import. The corpus enters
the store through the ordinary folder import (`docs/how-to/indexing.md`): the
same acceptance rules, the same storage, the same duplicate rule, the same
queued work. A picture whose bytes are already stored — uploaded by hand,
imported from elsewhere — is reported as already stored, and the asset that
holds them is left exactly as it is.

## What this does not do

- Nothing here runs inside the service. The API and the worker make no request
  to the dataset (NFR-SEC-4), and a test asserts the application cannot even
  import the module that does.
- The corpus is never committed: `.data/` is gitignored.
- Captions are not used. COCO has them, and indexing them as tags would flatter
  the search — a text query would be matching a human's sentence about the
  picture rather than the picture.
- A licence that changes after the download is not noticed. What is recorded is
  what the manifest said when the picture was fetched.
