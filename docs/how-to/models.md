# Work with the embedding models

What the service downloads, where it puts it, and how to have it ready
before the first request.

## What this build runs

| Key | Checkpoint | Commit | Width | Takes | Answers |
|---|---|---|---|---|---|
| `clip-vit-l14` | `openai/clip-vit-large-patch14` | `32bd6428…` | 768 | text and pictures | what a picture is *about* |
| `dinov2-large` | `facebook/dinov2-large` | `47b73eef…` | 1024 | pictures | what a picture *looks like* |

**A key names a commit, not just a repository.** A checkpoint name points at
whatever its repository holds today; a stored vector has to mean the same thing
a year from now, so each key is read at a fixed commit
([ADR-007](../adr/ADR-007-pinned-checkpoint-revisions.md)). The commits above
are the defaults of `CLIP_REVISION` and `DINOV2_REVISION`, and nothing needs
setting to get them.

Both are enabled by default, so an upload is queued for both and either
kind of search answers. DINOv2 has no text tower at all: asking it for
words is refused (422) rather than approximated, and a search that names
a model this deployment does not run is 503. Inference is CPU only —
there is no device setting.

A deployment may run one model by naming it in `ENABLED_MODELS`. That
halves what an upload costs and gives up the search the other one
answers; the vectors already stored are not touched, and enabling the
model again later is `semanticshelf index missing`.

### Substituting a checkpoint

`CLIP_MODEL_NAME` and `DINOV2_MODEL_NAME` take a mirror or a compatible
fine-tune — same space, same width, which the width check enforces at load.
**Set its commit with it.** A revision this repository ships is a commit of the
repository it ships, so a substituted name inherits none of it: the checkpoint
is then read the way every checkpoint was read before commits were pinned, and
what it answers can change under you. The service starts either way and says
which it did:

```json
{"event": "checkpoint is unpinned", "model": "clip-vit-l14", "checkpoint": "someone/clip-fine-tune"}
```

To pin it, give both:

```console
$ CLIP_MODEL_NAME=someone/clip-fine-tune \
  CLIP_REVISION=<the full 40-character commit> uv run semanticshelf models warm
```

A branch or a tag will not do — `CLIP_REVISION=main` is refused at startup,
because it resolves at load time and would read as pinned while pinning nothing.

**Changing a commit means re-indexing.** Vectors already stored were built with
the previous weights, and nothing records which; they are comparable with each
other and not with what the new ones produce. ADR-007 says what that does and
does not guarantee.

### And one query encoder

| Key | Checkpoint | Answers in | Takes |
|---|---|---|---|
| `mclip-xlmr-l14` | `M-CLIP/XLM-Roberta-Large-Vit-L-14` | `clip-vit-l14`'s space | text, in 48 languages |

A **query encoder** embeds a question into a space it does not own. This one is
a multilingual text tower trained against CLIP ViT-L/14's images, so a query in
Russian, German, French or Spanish is ranked against the vectors `clip-vit-l14`
already stored — **nothing is re-indexed, and nothing is ever written under the
encoder's key**: no vector, no queued work, no row in `/stats`.

It is **off by default**: 2.24 GB of weights for a question many deployments
never ask. `ENABLED_QUERY_ENCODERS=mclip-xlmr-l14` turns it on, and the service
refuses to start if `clip-vit-l14` is not enabled too — its vectors would have
nothing to be compared with. Which languages are claimed, and on what evidence:
[ADR-005](../adr/ADR-005-multilingual-query-encoder.md).

Three things about this checkpoint are worth knowing before you enable it.

- **It is pinned by two revisions, and unlike the two models there is no setting
  to move them.** One revision is the checkpoint with its config and splitter,
  the other the `xlm-roberta-large` config the architecture is built from; both
  are constants in `app/ml/mclip.py`. The two storage models have a setting for
  their checkpoint *and* for its commit, because a mirror or a compatible
  fine-tune is your choice and the width check keeps it honest. This key is
  different in kind: it claims to land in another model's space, nothing at
  runtime can check that, and what backs it is a measurement of these bytes.
  Other weights are another encoder, with a key and numbers of their own — which
  is why the commit is not yours to move here (ADR-005, and ADR-007 on why the
  two differ).
- **A checkpoint that does not fill the architecture is refused at load.** A
  tensor the model expects and the file does not carry would stay randomly
  initialised and answer anyway, at the right width; the adapter compares what
  the load reports against one known leftover and refuses everything else.
- **Its weights are a pickle, and are read as data.** The repository has no
  safetensors copy on its main revision (the one that exists is an unmerged
  pull request), so the adapter loads it with `weights_only=True`: tensors are
  read and no code from the file runs.
- **Its licence is not declared.** The model card states none and the hub's API
  returns none; the project that produced it
  ([FreddeFrallan/Multilingual-CLIP](https://github.com/FreddeFrallan/Multilingual-CLIP))
  is MIT. If your deployment needs certainty about the weights themselves, ask
  the model's authors — this repository records the question rather than
  answering it for you.

## Replacing or repairing a model

Two different jobs, and the difference matters before you type anything.

**Repairing** is one key whose weights moved: you changed `CLIP_REVISION`, or
you are cleaning up a corpus indexed before revisions were pinned at all
([ADR-007](../adr/ADR-007-pinned-checkpoint-revisions.md)). The key stays,
every vector under it is recomputed.

**Replacing** is a new key taking over from an old one — a different model, a
different width, its own index. The old key's vectors stay until you retire
them, and searches keep answering from whichever key they name.

Both commands report first and do nothing without `--apply`. The report is three
statements and loads no model, so it is the cheap answer to "how long will this
take and can I afford it now":

```console
$ uv run semanticshelf models reembed clip-vit-l14
plan: rebuild clip-vit-l14
vectors to compute: 0
already waiting: 0
nothing was queued or computed; pass --apply to do it
```

`vectors to compute` is how many that key holds — one per indexed picture, so
on the 500-picture demo corpus it is 500 and on an empty store, as above, it is
nothing. That number times a few seconds is the wait.

### Repairing a key, in this order

1. **Change the configuration** — the revision, or whatever moved.
2. **Restart every process that writes this key**: the API, and the worker if
   your deployment has one. This step is not optional and nothing enforces it.
   A process that loaded the model before the change keeps it for its whole
   life, and a queued job carries a key, never a revision — so a writer you did
   not restart can finish outstanding work with the old weights, or overwrite a
   repaired vector after you are done.
3. **Repair**: `uv run semanticshelf models reembed clip-vit-l14 --apply`.

The command refuses to begin while another runner holds a live claim on the key,
because that is a writer working right now whose weights nothing can see. It
does **not** refuse on work that is merely waiting, or on a claim whose lease has
expired — that is what an interrupted repair leaves, and finishing it is the
point. A runner that wakes after its lease has gone cannot overwrite anything:
its finish matches only the lease expiry its own claim wrote.

**While it runs, the key holds vectors from two checkpoints.** Their scores are
comparable within each group and not across, and the search ranking them cannot
tell them apart. There is no way to avoid that window; there is only finishing
it. Run it when a slightly worse ranking for a while is acceptable.

### Replacing a key

```console
$ uv run semanticshelf models migrate clip-vit-l14 some-new-key --apply
$ uv run semanticshelf models migrate clip-vit-l14 some-new-key --apply --retire
```

The first fills. Searches keep answering from `clip-vit-l14` throughout, because
which key answers is the request's own `model` and its default is a constant in
the code — nothing repoints itself while you are not looking.

The second fills and then deletes the old key's vectors. That deletion is
refused unless every asset the old key answers for has a vector under the new
one, tested inside the statement that deletes, and unless the queue owes nothing
for the new key. Run the fill first, let it finish, then retire.

**Retiring deletes vectors and disables nothing.** A key left in
`ENABLED_MODELS` will be queued for on the next upload; removing it is
configuration and yours to change. The command says so rather than deciding for
you.

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

$ ENABLED_QUERY_ENCODERS=mclip-xlmr-l14 uv run semanticshelf models warm
dinov2-large: 1024 dimensions, loaded in 4.3s
mclip-xlmr-l14: 768 dimensions, loaded in 5.0s
```

The command loads every key in `ENABLED_MODELS` **and every enabled query
encoder**, downloading what is missing, and prints each one's width and load
time. An encoder prints the width of the space it answers in, because that is
the width of what it produces. It reads the same settings as the service, so it
needs `DATABASE_URL` to be set even though it never opens a connection.

In the container stack the same thing is `make stack-warm`, which runs it
inside the service image and fills the model volume.

To have the application itself warm up at start, name the keys in
`MODEL_WARMUP`:

```dotenv
MODEL_WARMUP=clip-vit-l14,dinov2-large
```

A query encoder may be named there too, once it is enabled — it is the largest
download this service has, and a first query in another language that waits for
all of it is the thing warming exists to prevent.

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
