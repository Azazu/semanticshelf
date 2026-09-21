# Work with the embedding models

What the service downloads, where it puts it, and how to have it ready
before the first request.

## What this build runs

| Key | Checkpoint | Width | Towers |
|---|---|---|---|
| `clip-vit-l14` | `openai/clip-vit-large-patch14` | 768 | text and image |

`dinov2-large` (1024) is declared by the schema and by `app/domain.py`,
because migrations are written once, but this build has no adapter for
it: naming it in `ENABLED_MODELS` refuses at start. Inference is CPU
only — there is no device setting.

## The download

The weights come from the Hugging Face hub the first time a model is
loaded, into `MODEL_CACHE` (default `.data/models`, gitignored):

```console
$ du -sh .data/models
1.6G	.data/models
```

That directory is the hub's own layout (`blobs/`,
`models--openai--clip-vit-large-patch14/`), so it can be mounted into a
container or copied between machines as a whole.

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
MODEL_WARMUP=clip-vit-l14
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
7 passed, 131 deselected in 8.79s
```

Marked `models`, so neither `make check` nor CI runs it: it downloads
the checkpoint on a cold cache and needs the network. Everything else in
the suite runs against the deterministic stand-in in `app/ml/fake.py`,
which needs no weights and produces the same vectors in every process.

## What can go wrong

| Symptom | Cause |
|---|---|
| Start fails with `ENABLED_MODELS names models this build does not implement` | A key with no adapter, `dinov2-large` today. |
| Start fails with `MODEL_WARMUP names models that are not enabled` | A warm-up key outside `ENABLED_MODELS`. |
| `CheckpointWidthError` naming two widths | `CLIP_MODEL_NAME` points at weights of another width. The adapter refuses them at load, before any vector is stored. |
| `GET /ready` answers 503 with `checks.models` naming two widths | The application and the database schema disagree about a model. Run the migrations, or reconcile `ENABLED_MODELS`. It does not mean the weights are wrong — no probe can see inside a checkpoint. |
| The first request after a restart is slow | Nothing was warmed up. See above. |
