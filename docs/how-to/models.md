# Work with the embedding models

What the service downloads, where it puts it, and how to have it ready
before the first request.

## What this build runs

| Key | Checkpoint | Width | Takes | Answers |
|---|---|---|---|---|
| `clip-vit-l14` | `openai/clip-vit-large-patch14` | 768 | text and pictures | what a picture is *about* |
| `dinov2-large` | `facebook/dinov2-large` | 1024 | pictures | what a picture *looks like* |

Both are enabled by default, so an upload is queued for both and either
kind of search answers. DINOv2 has no text tower at all: asking it for
words is refused (422) rather than approximated, and a search that names
a model this deployment does not run is 503. Inference is CPU only —
there is no device setting.

A deployment may run one model by naming it in `ENABLED_MODELS`. That
halves what an upload costs and gives up the search the other one
answers; the vectors already stored are not touched, and enabling the
model again later is `semanticshelf index missing`.

## The download

The weights come from the Hugging Face hub the first time a model is
loaded, into `MODEL_CACHE` (default `.data/models`, gitignored):

```console
$ du -sh .data/models
2.8G	.data/models
```

That is about 1.6 GB for CLIP and 1.2 GB for DINOv2. The directory is
the hub's own layout (`blobs/`, `models--openai--clip-vit-large-patch14/`,
`models--facebook--dinov2-large/`), so it can be mounted into a container
or copied between machines as a whole.

This is the service's only network egress. Nothing is fetched while the
application is imported, while `--help` runs, or during a request that
does not ask for a model.

## Warm up before taking traffic

```console
$ uv run semanticshelf models warm
clip-vit-l14: 768 dimensions, loaded in 5.7s
```

The command loads every key in `ENABLED_MODELS`, downloading what is
missing, and prints each model's width and load time. It reads the same
settings as the service, so it needs `DATABASE_URL` to be set even
though it never opens a connection.

To have the application itself warm up at start, name the keys in
`MODEL_WARMUP`:

```dotenv
MODEL_WARMUP=clip-vit-l14,dinov2-large
```

The lifespan then loads exactly those keys, on the inference pool rather
than on the event loop, and the process is ready to embed as soon as it
answers. Without it, the first request that needs a model pays for the
load; a key is loaded once per process either way.

## Run offline

Once the cache holds the weights, the hub is not needed:

```console
$ HF_HUB_OFFLINE=1 uv run semanticshelf models warm
clip-vit-l14: 768 dimensions, loaded in 2.2s
```

Set `HF_HUB_OFFLINE=1` in an environment that must not reach the
network. A key whose weights are missing then fails at load instead of
downloading them.

## Tune for the machine

| Setting | When to change it |
|---|---|
| `TORCH_NUM_THREADS` | `0` lets torch decide, which is right on a laptop. In a container with a CPU quota, set it to the quota: oversubscribed threads are slower, not faster. |
| `EMBED_BATCH_SIZE` | Memory, not speed, sets this. A batch is one tensor; lower it on a small container. |
| `INFERENCE_WORKERS` | How many loads or forward passes run at once. Each loaded model is shared by all of them; more workers cost CPU, not weights. |

## Test against the real weights

```console
$ make test-models
19 passed, 745 deselected in 29.43s
```

It loads each checkpoint once and asserts what the rest of the suite
takes on trust: the width the key declares (768 and 1024), unit-length
rows, a batch that keeps its order, and — for DINOv2 — that two
renderings of one picture land nearer each other than either does to a
different picture, which is what image→image search means.

Marked `models`, so neither `make check` nor CI runs it: it downloads
the checkpoints on a cold cache and needs the network. Everything else in
the suite runs against the deterministic stand-in in `app/ml/fake.py`,
which needs no weights and produces the same vectors in every process.

## What can go wrong

| Symptom | Cause |
|---|---|
| Start fails with `ENABLED_MODELS names models this build does not implement` | A key with no adapter. Both keys the schema declares have one; anything else is a typo. |
| A picture search answers 503 | `dinov2-large` is not in `ENABLED_MODELS`. Nothing else can answer a picture, and the service says which key it is missing rather than falling back. |
| A text search answers 422 naming what a model takes | `model=dinov2-large` with words. It has no text tower; that is a fact about the model, not about this deployment. |
| `GET /assets/{id}/similar` answers 409 | The asset has no vector for that model — usually a corpus imported before the model was enabled. `semanticshelf index missing` queues what is missing. |
| Start fails with `MODEL_WARMUP names models that are not enabled` | A warm-up key outside `ENABLED_MODELS`. |
| `CheckpointWidthError` naming two widths | `CLIP_MODEL_NAME` or `DINOV2_MODEL_NAME` points at weights of another width. The adapter refuses them at load, before any vector is stored. |
| `GET /ready` answers 503 with `checks.models` naming two widths | The application and the database schema disagree about a model. Run the migrations, or reconcile `ENABLED_MODELS`. It does not mean the weights are wrong — no probe can see inside a checkpoint. |
| The first request after a restart is slow | Nothing was warmed up. See above. |
