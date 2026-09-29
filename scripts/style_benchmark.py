"""Does a style key answer something the keys already here do not?

The roadmap asks for a style embedding as a third key. A key is permanent — it
is part of an embedding's identity, it costs an index and a vector for every
asset, and it queues work for every upload — so before one is added this
repository owes a measurement rather than an argument. These are the numbers,
and ADR-006 is what they decided.

**The corpus** is built rather than found (`style_corpus.py`): every photograph
of a folder under a fixed set of deterministic looks. Two images share a look
because the same function produced them and share a subject because they came
from the same photograph, so nothing has to be labelled and a re-run rebuilds
exactly the same corpus.

**The deciding number is a rank preference.** Over every triple — an anchor,
another photograph under the anchor's look, the anchor's photograph under
another look — it is the fraction where the model scores the look-mate above
the picture-mate, a tie counting a half. 0.5 is indifference. A model that
ranks by subject sits near 0.

**The ratio of averages is printed beside it and decides nothing.** The obvious
statistic — mean "same look, different picture" over mean "same picture,
different look" — is confounded by how widely a model spreads its similarity
scores: a model whose cosines all sit in a narrow high band scores well on it
while ranking the subject first every time. It is published because seeing that
is worth more than not seeing it, and because a reader may want to check the
claim.

**The bound is fixed before the run** and is read on the preference only: a
candidate earns a key when it closes more than half the remaining distance to a
perfect score, against the best of the keys the service already stores. It also
prints `undefined` rather than a number wherever a value would be a division it
cannot justify.

It writes nothing, reads no database, and needs the `style` dependency group:

    uv run --group style python scripts/style_benchmark.py
    uv run --group style python scripts/style_benchmark.py --pictures 120
"""

import argparse
import hashlib
import sys
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import style_candidate  # noqa: E402
import style_corpus  # noqa: E402
from style_corpus import Label  # noqa: E402

from app.core.settings import Settings  # noqa: E402
from app.domain import EMBEDDING_MODELS, IMPLEMENTED_MODELS  # noqa: E402
from app.ml.registry import FACTORIES  # noqa: E402

#: The default corpus and how much of it is measured. A hundred photographs is
#: the floor task 3.1 published against; the bound below it is the corpus's own.
DEFAULT_FOLDER: Final = Path(".data/demo/pictures")
DEFAULT_PICTURES: Final = 100


class NoTriplesError(RuntimeError):
    """A corpus that forms no comparison at all — the preference has no value.

    It takes two photographs and two looks to make one triple. The corpus
    bounds refuse a corpus that small long before this, and this is the second
    line: a number computed from nothing must never be printed as a number.
    """


@dataclass(frozen=True, slots=True)
class Averages:
    """The two sides of the comparison, and how many pairs each rests on."""

    same_look: float | None
    same_picture: float | None
    look_pairs: int
    picture_pairs: int

    @property
    def ratio(self) -> float | None:
        """The diagnostic. `None` — printed as `undefined` — whenever the
        denominator is missing or not positive: a mean cosine similarity can be
        zero or negative, and a ratio through either says nothing at all."""
        if self.same_look is None or self.same_picture is None:
            return None
        if self.same_picture <= 0:
            return None
        return self.same_look / self.same_picture


@dataclass(frozen=True, slots=True)
class Scored:
    """What one model did on one corpus."""

    model: str
    preference: float
    triples: int
    averages: Averages
    per_look: Mapping[str, float]


def similarities(vectors: np.ndarray) -> np.ndarray:
    """Cosine similarity between every pair, which for unit rows is the dot."""
    return np.asarray(vectors @ vectors.T, dtype=np.float32)


def preference(vectors: np.ndarray, labels: Sequence[Label], *, look: str | None = None) -> float:
    """The fraction of triples where the look-mate outscores the picture-mate.

    `look` restricts the anchors to one look, which is the per-look breakdown.
    A tie counts a half: the two candidates are then equally far from the
    anchor, and calling that a win for either would be an opinion.
    """
    scores = similarities(vectors)
    looks = np.array([label.look for label in labels])
    pictures = np.array([label.picture for label in labels])
    wins = 0.0
    triples = 0
    for index, label in enumerate(labels):
        if look is not None and label.look != look:
            continue
        mates = np.flatnonzero((looks == label.look) & (pictures != label.picture))
        twins = np.flatnonzero((pictures == label.picture) & (looks != label.look))
        if mates.size == 0 or twins.size == 0:
            continue
        against = scores[index, mates][:, None] - scores[index, twins][None, :]
        wins += float(np.count_nonzero(against > 0)) + 0.5 * float(np.count_nonzero(against == 0))
        triples += mates.size * twins.size
    if triples == 0:
        raise NoTriplesError(
            "this corpus forms no triple: the preference needs two photographs under "
            "a shared look and one photograph under two looks"
        )
    return wins / triples


def count_triples(labels: Sequence[Label]) -> int:
    """How many comparisons the corpus forms, which the table prints."""
    looks = np.array([label.look for label in labels])
    pictures = np.array([label.picture for label in labels])
    total = 0
    for label in labels:
        mates = int(np.count_nonzero((looks == label.look) & (pictures != label.picture)))
        twins = int(np.count_nonzero((pictures == label.picture) & (looks != label.look)))
        total += mates * twins
    return total


def averages(vectors: np.ndarray, labels: Sequence[Label]) -> Averages:
    """The two means, each `None` when its set of pairs is empty."""
    scores = similarities(vectors)
    same_look: list[float] = []
    same_picture: list[float] = []
    for first in range(len(labels)):
        for second in range(first + 1, len(labels)):
            one, other = labels[first], labels[second]
            value = float(scores[first, second])
            if one.look == other.look and one.picture != other.picture:
                same_look.append(value)
            elif one.picture == other.picture and one.look != other.look:
                same_picture.append(value)
    return Averages(
        same_look=float(np.mean(same_look)) if same_look else None,
        same_picture=float(np.mean(same_picture)) if same_picture else None,
        look_pairs=len(same_look),
        picture_pairs=len(same_picture),
    )


def score(model: str, vectors: np.ndarray, labels: Sequence[Label]) -> Scored:
    """Everything published about one model, computed once."""
    looks = sorted({label.look for label in labels}, key=tuple(style_corpus.LOOKS).index)
    per_look = {}
    for look in looks:
        try:
            per_look[look] = preference(vectors, labels, look=look)
        except NoTriplesError:
            continue
    return Scored(
        model=model,
        preference=preference(vectors, labels),
        triples=count_triples(labels),
        averages=averages(vectors, labels),
        per_look=per_look,
    )


def bound(incumbents: Sequence[float]) -> float:
    """What a candidate has to beat: half the distance the best incumbent still
    has to a perfect score, added to it.

    One condition, not two. The value is `(1 + incumbent) / 2` and a preference
    lies in [0, 1], so the bound is never below 0.5 — a candidate that clears it
    has already been shown to prefer the look rather than the subject.
    """
    if not incumbents:
        raise ValueError("a margin is a margin over something; name the keys already stored")
    best = max(incumbents)
    return best + (1 - best) / 2


def clears(candidate: float, incumbents: Sequence[float]) -> bool:
    """Strictly greater: a tie does not buy a migration, and strictness closes
    the one point — a candidate at 0.5 against an incumbent at 0 — where the
    bound would otherwise coincide with indifference."""
    return candidate > bound(incumbents)


def incumbents() -> tuple[str, ...]:
    """Every key the service stores vectors under, read from the domain.

    Not a list written out here: a key added to `EMBEDDING_MODELS` later has to
    appear in this measurement without anybody remembering to add it.
    """
    return tuple(sorted(EMBEDDING_MODELS))


def embed(
    model: str, corpus: style_corpus.Corpus, settings: Settings
) -> tuple[list[Label], np.ndarray]:
    """One model over the whole corpus, a batch at a time.

    The model is built here and dropped when this returns, so the run holds one
    set of weights and one batch of pictures rather than three models and six
    hundred images.
    """
    embedder = (
        style_candidate.StyleCandidate.load(settings)
        if model == style_candidate.LABEL
        else FACTORIES[model](settings)
    )
    labels: list[Label] = []
    rows: list[np.ndarray] = []
    stream = style_corpus.batched(style_corpus.images(corpus), settings.embed_batch_size)
    started = time.monotonic()
    for batch_labels, pictures in stream:
        labels.extend(batch_labels)
        rows.append(embedder.embed_images(pictures).vectors)
        progress(model, len(labels), corpus.size, time.monotonic() - started)
    print(file=sys.stderr)
    return labels, np.concatenate(rows)


def progress(model: str, done: int, total: int, elapsed: float) -> str:
    """One line, rewritten in place, with what is left to wait for.

    Three model passes over several hundred pictures on a CPU is minutes per
    model. A command that prints nothing until it is finished cannot be told
    apart from one that has hung, and its cost cannot be planned for, so it
    says where it is.
    """
    left = (total - done) * elapsed / done if done else 0.0
    line = f"[{model}] {done}/{total} images, {elapsed:5.0f}s elapsed, ~{left:4.0f}s left"
    print(f"\r{line}", end="", file=sys.stderr, flush=True)
    return line


def corpus_digest(corpus: style_corpus.Corpus) -> str:
    """A name for exactly these bytes.

    "The first hundred pictures of a folder" is not a corpus anyone else can
    obtain, and a reader who re-runs this command has no way to tell whether
    the folder they pointed it at is the folder these numbers came from. The
    digest is over the file names and their contents, so two runs agree on it
    exactly when they measured the same pictures.
    """
    running = hashlib.sha256()
    for path in corpus.paths:
        running.update(path.name.encode("utf-8"))
        running.update(path.read_bytes())
    return running.hexdigest()[:16]


def checkpoints(settings: Settings) -> list[tuple[str, str, str]]:
    """Every checkpoint this build can load, and what it resolved to here.

    Read from the settings fields rather than from a list, for the same reason
    the measured keys are read from `app.domain`. Only the candidate is pinned
    by this repository; the rest are names a deployment configures, so what is
    printed for them is the snapshot the local model cache actually holds —
    reported, never claimed to be fixed.
    """
    from huggingface_hub import scan_cache_dir

    resolved: dict[str, str] = {}
    try:
        for repo in scan_cache_dir(settings.model_cache).repos:
            for ref, revision in repo.refs.items():
                if ref == "main":
                    resolved[repo.repo_id] = revision.commit_hash
    except Exception:  # noqa: BLE001 - provenance is reported, never relied upon
        resolved = {}

    rows = []
    for field in sorted(f for f in type(settings).model_fields if f.endswith("_model_name")):
        name = str(getattr(settings, field))
        rows.append((field, name, resolved.get(name, "unresolved")))
    return rows


def shown(value: float | None) -> str:
    """A number, or the word for the absence of one."""
    return "undefined" if value is None else f"{value:.3f}"


def report(
    corpus: style_corpus.Corpus,
    labels: Sequence[Label],
    rows: Sequence[Scored],
    settings: Settings,
) -> None:
    """The published table. Everything a reader needs to disagree with it."""
    pictures, looks = style_corpus.present(labels)
    refused = corpus.size - len(labels)
    candidate = next(row for row in rows if row.model == style_candidate.LABEL)
    others = [row for row in rows if row.model != style_candidate.LABEL]

    print(f"## Style, measured over {pictures} photographs × {len(looks)} looks\n")
    print(f"Corpus: `{corpus.root}`, looks {', '.join(looks)}.")
    print(f"{len(labels)} images, {refused} refused as one colour, {rows[0].triples} triples.")
    print(f"Corpus digest (names and bytes): `{corpus_digest(corpus)}`.")
    print(
        f"Candidate: `{style_candidate.CHECKPOINT}` at `{style_candidate.REVISION}`, "
        f"tower `{style_candidate.TOWER}`.\n"
    )

    print(
        "| model | prefers the look | same look, diff. picture | same picture, diff. look | ratio |"
    )
    print("|---|---|---|---|---|")
    for row in rows:
        print(
            f"| `{row.model}` | {row.preference:.3f} | {shown(row.averages.same_look)} "
            f"| {shown(row.averages.same_picture)} | {shown(row.averages.ratio)} |"
        )
    print(
        f"\nPairs behind the two averages: {rows[0].averages.look_pairs} sharing a look, "
        f"{rows[0].averages.picture_pairs} sharing a picture.\n"
    )

    print("Per look, the same preference with the anchors restricted to that look:\n")
    print("| look | " + " | ".join(f"`{row.model}`" for row in rows) + " |")
    print("|---" * (len(rows) + 1) + "|")
    for look in looks:
        cells = " | ".join(shown(row.per_look.get(look)) for row in rows)
        print(f"| {look} | {cells} |")

    stored = [row.preference for row in others]
    best = max(others, key=lambda row: row.preference)
    print(
        f"\nBound: more than {bound(stored):.3f} — half the distance `{best.model}` "
        f"({best.preference:.3f}) still has to a perfect score, added to it."
    )
    verdict = "clears the bound" if clears(candidate.preference, stored) else "does not clear it"
    print(f"Verdict: the candidate {verdict}.")

    print("\nCheckpoints this run loaded. Only the candidate is pinned by this repository;")
    print("the rest are configured names, and what is shown is the snapshot found here.\n")
    print("| setting | checkpoint | resolved to |")
    print("|---|---|---|")
    for field, name, revision in checkpoints(settings):
        print(f"| `{field}` | `{name}` | `{revision}` |")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--folder", type=Path, default=DEFAULT_FOLDER)
    parser.add_argument("--pictures", type=int, default=DEFAULT_PICTURES)
    arguments = parser.parse_args()

    missing = sorted(set(incumbents()) - IMPLEMENTED_MODELS)
    if missing:
        print(f"no adapter in this build for {missing}: the comparison would leave a key out")
        return 2

    settings = Settings()  # type: ignore[call-arg]
    try:
        corpus = style_corpus.corpus_of(arguments.folder, limit=arguments.pictures)
    except (OSError, style_corpus.CorpusTooSmallError) as refusal:
        print(f"nothing measured: {refusal}")
        return 2

    rows: list[Scored] = []
    agreed: list[Label] | None = None
    for model in (style_candidate.LABEL, *incumbents()):
        labels, vectors = embed(model, corpus, settings)
        if agreed is None:
            try:
                style_corpus.check_present(labels)
            except style_corpus.CorpusTooSmallError as refusal:
                print(f"nothing measured: {refusal}")
                return 2
            agreed = labels
        elif labels != agreed:
            print("the corpus changed between models, which it cannot: nothing is reported")
            return 2
        rows.append(score(model, vectors, labels))

    assert agreed is not None
    report(corpus, agreed, rows, settings)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
