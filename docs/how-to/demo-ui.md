# Look at the service instead of curling it

The demo interface is four pages over the same HTTP API everything else uses:
search, browse, upload, and the service's own state. It holds no database
session, reads no file and loads no model — it cannot, and a test proves it.

Every command here was run in the form shown on 2026-09-23. Where a run printed
this machine's addresses, only the local one is kept.

## From nothing to something to look at

```console
$ make demo          # a corpus: COCO val2017, licence-filtered, indexed
$ make run           # the service, on 127.0.0.1:8000
$ make ui            # the interface, on 127.0.0.1:8501
the demo is at http://127.0.0.1:8501 — the service must be running (make run)

  You can now view your Streamlit app in your browser.
  Local URL: http://localhost:8501
```

The first `make ui` installs Streamlit, which lives in a dependency group of its
own — the gate floor, the API image and CI never see it.

Two settings, both optional:

| Variable | Default | What it is |
|---|---|---|
| `API_BASE_URL` | `http://127.0.0.1:8000` | where the interface looks for the service |
| `UI_PORT` | `8501` | where the interface listens |

## What each page is for

**Search** — describe a picture and the service ranks what it has by how near it
is to your words. The score beside each result is `1 − cosine distance`, so it
is comparable within one model and one query and nowhere else; the page names
the model for that reason. The slider is the API's `min_score`, which cuts the
tail of a page rather than reaching deeper for replacements, and **More** asks
the service for the next page by offset — the grid never fetches more than it
shows.

**Browse** — everything stored, newest first, narrowed by a tag from the tag
census. Opening a picture shows what the service knows about it: its metadata,
its indexing state per model and the full-size image. Deleting asks first, and
deletes through the API exactly as `curl` would.

**Upload** — a file, tags and metadata. What the service decides is what you
see: it reads the format from the bytes, so a `.png` that is really a PDF is
refused with the service's own words.

**Status** — `/ready` with each check, how much is stored, the work per model
and state, and how long the oldest waiting job has waited (absent rather than
zero when nothing is waiting).

## Pictures come from the service, not from the interface

Every thumbnail and every full-size picture is an address the API returned
(`links.thumbnail`, `links.file`), joined with `API_BASE_URL`. **The browser
fetches them from the service directly**, which is why the service has to be
reachable from wherever the browser is, not only from the machine the interface
runs on.

## When something is refused

Refusals are the service's, shown as it worded them — its problem-details
`title` and `detail`, never a traceback and never a bare status code. A page
that was refused stays usable: fix the query, or the file, and try again.

If the service is not running at all, every page says so in one sentence and
still draws itself.

## The screenshots

```console
$ make screenshots
wrote docs/images/search.png
wrote docs/images/browse.png
wrote docs/images/status.png
```

It starts the API and the interface on ports it picks, drives a headless
Chromium through the three pages and stops both servers afterwards — whatever
happened. The first run downloads that browser:

```console
$ uv run --group screenshots playwright install chromium
```

It needs a corpus. Against an empty store it says so and writes nothing, which
is what `make demo` is for. **The integration tests empty the store** (they
truncate the tables), so run `make demo` again before capturing.

## The tests

```console
$ make test-ui
31 passed, 616 deselected
```

They render the real pages against a service that answers from memory, so they
are fast and need neither a database nor a browser. They are not part of
`make check`: Streamlit is in a group the gate floor does not install, and the
test directory is not even collected when it is absent.
