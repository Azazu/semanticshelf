# Upload, read and remove a picture

Every command here was run in the form shown, against a local service
(`make run`, `MEDIA_ROOT=.data/media`), and the answers are the answers it
gave — only the identifiers and request ids differ from run to run, and long
bodies are shown formatted.

## Upload

```console
$ curl -s -X POST http://127.0.0.1:8000/api/v1/assets \
    -F "file=@dragon.png" \
    -F "tags=dragon,blue" \
    -F 'meta={"origin":"handbook"}'
{
    "id": "20716b23-ee42-4a71-adb9-3e8822f2b82d",
    "created_at": "2026-09-21T13:59:15.281316Z",
    "content_type": "image/png",
    "width": 800,
    "height": 600,
    "size_bytes": 4207,
    "sha256": "c7d4df25cbdc7ee4a56c12cd13c459188c382b1f95fcf9de9af1d32d0a7e458b",
    "original_filename": "dragon.png",
    "source": "upload",
    "tags": ["dragon", "blue"],
    "meta": {"origin": "handbook"},
    "index_status": {"clip-vit-l14": "pending"},
    "links": {
        "file": "/api/v1/assets/20716b23-ee42-4a71-adb9-3e8822f2b82d/file",
        "thumbnail": "/api/v1/assets/20716b23-ee42-4a71-adb9-3e8822f2b82d/thumbnail"
    }
}
```

The answer is 201 with a `Location` header. `index_status` says `pending`
because the upload queued the work and did not wait for it: by the time you
read the asset back it will say `done`, and
[`indexing.md`](indexing.md) is the whole story. `tags` may be repeated
(`-F tags=dragon -F tags=blue`) or comma-separated; both give the same set,
normalised (trimmed, lower-cased, deduplicated). `meta` is a JSON object as a
string.

The format comes from the bytes. A PNG called `photo.jpg` with a part header
claiming `image/jpeg` is stored as a PNG — the name and the header are not
evidence.

## What is refused, and with what

| Answer | When |
|---|---|
| 413 `/errors/upload-too-large` | the request body is over `MAX_UPLOAD_BYTES` (20 MiB by default), refused while it is being read |
| 415 `/errors/unsupported-media-type` | the file does not decode as a picture, or is not JPEG, PNG or WebP |
| 422 `/errors/image-too-large` | more pixels than `MAX_IMAGE_PIXELS`, refused from the header before anything is decoded |
| 422 `/errors/image-too-small` | the shorter side is under `MIN_IMAGE_SIDE` |
| 422 `/errors/invalid-tags` · `/errors/invalid-meta` | a tag outside the pattern, or metadata that is not an object, too large or too deeply nested |
| 409 `/errors/duplicate-asset` | those exact bytes are already stored; the body names the existing asset |
| 400 | the multipart body itself is malformed, or has more parts than an upload can have |

Two examples, as they actually answer:

```console
$ curl -s -X POST http://127.0.0.1:8000/api/v1/assets -F "file=@notes.txt"
{"type": "/errors/unsupported-media-type", "title": "Unsupported Media Type", "status": 415,
 "detail": "the file does not decode as an image", "instance": "urn:request:…"}

$ curl -s -X POST http://127.0.0.1:8000/api/v1/assets -F "file=@dragon.png"   # the second time
{"type": "/errors/duplicate-asset", "title": "Conflict", "status": 409,
 "detail": "those bytes are already stored", "instance": "urn:request:…",
 "existing_asset_id": "2632a112-bab4-499e-abc3-96c35bd0d040"}
```

A refusal stores nothing: no row, and nothing left in the media root.

## Read it back

```console
$ curl -s -D- -o /dev/null http://127.0.0.1:8000/api/v1/assets/<id>/file
HTTP/1.1 200 OK
cache-control: private, max-age=86400
etag: "b6b786cef39234916d810ef603378716a92bb271131adfcf368189f2278faf1c"
content-type: image/png
content-disposition: inline; filename="2632a112-bab4-499e-abc3-96c35bd0d040.png"
content-length: 2791
```

The entity tag is the content hash, so a client can revalidate cheaply. The
thumbnail is the same, as WebP:

```console
$ curl -s -D- -o thumb.webp http://127.0.0.1:8000/api/v1/assets/<id>/thumbnail
HTTP/1.1 200 OK
content-type: image/webp
content-length: 174

$ python -c "from PIL import Image; print(Image.open('thumb.webp').size)"
(256, 192)
```

The thumbnail is bounded by its longest side and never enlarged, so a picture
already smaller than 256 px keeps its own size.

Listing is newest first, with `limit` (20 by default, 100 at most), `offset`
(10 000 at most), `tags_all`, `tags_any`, `meta.<key>` (top-level equality in
the metadata, at most five conditions) and `source`:

```console
$ curl -s "http://127.0.0.1:8000/api/v1/assets?limit=20&tags_any=dragon"
{"items": ["2632a112-bab4-499e-abc3-96c35bd0d040"], "limit": 20, "offset": 0, "has_more": false}
```

There is no total. `has_more` comes from fetching one row beyond the page,
which is honest; a count would be stale before it reached the client.

## Change what may change

```console
$ curl -s -X PATCH http://127.0.0.1:8000/api/v1/assets/<id> \
    -H 'content-type: application/json' -d '{"tags":["dragon","fog"]}'
{"id": "20716b23-ee42-4a71-adb9-3e8822f2b82d", …, "tags": ["dragon", "fog"],
 "meta": {"origin": "handbook"}, "index_status": {"clip-vit-l14": "done"}, "links": {…}}
```

An omitted field is left alone; `"meta": null` clears the metadata. The
picture itself — its bytes, its hash, its dimensions, its content type — is
immutable.

## Remove it

```console
$ curl -s -o /dev/null -w "%{http_code}\n" -X DELETE http://127.0.0.1:8000/api/v1/assets/<id>
204
$ curl -s -o /dev/null -w "%{http_code}\n" -X DELETE http://127.0.0.1:8000/api/v1/assets/<id>
404
```

The row goes with everything derived from it in one transaction, and the two
files follow after the commit. The second call is a 404 on purpose: the caller
is told the asset does not exist.

## Where the bytes live

```
.data/media/86/862c3538-2d72-4c1d-be01-7c207aef0437.png
.data/media/86/862c3538-2d72-4c1d-be01-7c207aef0437.thumb.webp
```

`MEDIA_ROOT`, then two hex characters of the identifier as a directory, then
the identifier and the detected format. Every part of that path is generated
by the service; nothing a client sends reaches it, and nothing under the root
is served by path — only by identifier, through the endpoints above.

The service does not create the media root: a mistyped path should be
reported, not silently created beside the real one. `make init` creates the
default, and `GET /ready` says so when it is missing:

```json
{"checks": {"database": "ok", "migrations": "ok", "models": "ok",
            "media": "the media root does not exist"}}
```

## Find what nobody owns

Files are written before the row, so a crash between them can leave files no
asset refers to; a file can also be lost under a live asset.

```console
$ uv run semanticshelf storage prune
orphan files: 1
assets with missing files: 0
ignored as too young: 0
  orphan  abandoned.png
nothing was changed; pass --apply to act

$ uv run semanticshelf storage prune --apply
orphan files: 1
assets with missing files: 0
ignored as too young: 0
  orphan  abandoned.png
removed 1 file(s); marked 0 job(s) failed with 'file-missing'
```

Two things it will not do. It ignores files younger than
`PRUNE_MIN_AGE_SECONDS` (an hour by default) and says how many. And it does
not run at all while an upload is in flight:

```console
$ uv run semanticshelf storage prune --apply
an upload is in flight; nothing was examined or changed
```

An upload between its files and its row looks exactly like rubbish, and it can
be delayed for any length of time, so the two hold an advisory lock in the
database rather than trusting a timeout.
