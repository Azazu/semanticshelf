"""What a query in another language costs, measured against the corpus itself.

The service states an English-only limit as a boundary, and §9 of the
specification allows lifting it "only with numbers". These are the numbers.

**What is measured.** For a concept the corpus carries as a tag — `zebra`,
`traffic light`, `tennis racket` — a query names it in one language and the
first ten results are compared with what carries that tag:

- **recall@10**: of the assets tagged with the concept, how many reached the
  first ten. Recall rather than precision, because precision@10 is capped at
  `relevant/10` for a concept the corpus holds four pictures of, and a perfect
  answer would score 0.4 and look like a failure.
- **agreement@10**: how much of the *English* page the same concept in another
  language reproduces, as a set intersection. This is the number that answers
  "does it find the same pictures", and it is published without a bound.

**What decides whether a language is claimed.** Two conditions, both:
mean recall@10 of at least `ABSOLUTE_FLOOR`, and at least `RELATIVE_FLOOR` of
the English baseline's mean over the same concepts. The relative one alone
would pass an encoder that finds nothing against a baseline that finds nothing;
the absolute one alone would not say whether the encoder or the corpus is the
limit.

**What the concept set is, and what it is not.** Chosen by rules that look at
no language's results: a tag on at least `MIN_ASSETS` and at most `MAX_ASSETS`
assets (fewer and one picture decides the score, more and recall@10 cannot
reach 1), at least `MIN_CONCEPTS` of them, and the English baseline itself
clearing the absolute floor — a concept set the service's own model cannot
answer measures the corpus, not the encoder.

**How it treats the store.** It reads, in a read-only transaction, and writes
nothing anywhere. It ranks exactly, in memory: the subject here is the encoder,
and what the index gives up is change 14's subject, already published in
`docs/how-to/benchmarks.md`.

    uv run python scripts/multilingual_benchmark.py
    uv run python scripts/multilingual_benchmark.py --languages ru,de
"""

import argparse
import asyncio
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import sqlalchemy as sa

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.settings import Settings  # noqa: E402
from app.db.engine import create_engine  # noqa: E402
from app.domain import CLIP_VIT_L14, MCLIP_XLMR_L14, dimension_of  # noqa: E402

#: How many results a page of this measurement holds.
AT = 10
#: A concept enters the set only within these bounds, for the reasons above.
MIN_ASSETS = 3
MAX_ASSETS = 10
MIN_CONCEPTS = 20
#: The two conditions a language clears to be claimed.
ABSOLUTE_FLOOR = 0.5
RELATIVE_FLOOR = 0.8

ENGLISH = "en"

#: The concepts this measurement can ask about, in the languages it knows.
#: COCO's own labels are the ground truth, so the key is the tag the corpus
#: carries; the phrases are what a person would type. They are printed with the
#: results, because a measurement whose inputs are hidden is an opinion.
CONCEPTS: Mapping[str, Mapping[str, str]] = {
    "zebra": {
        "en": "a zebra",
        "ru": "зебра",
        "de": "ein Zebra",
        "fr": "un zèbre",
        "es": "una cebra",
    },
    "elephant": {
        "en": "an elephant",
        "ru": "слон",
        "de": "ein Elefant",
        "fr": "un éléphant",
        "es": "un elefante",
    },
    "giraffe": {
        "en": "a giraffe",
        "ru": "жираф",
        "de": "eine Giraffe",
        "fr": "une girafe",
        "es": "una jirafa",
    },
    "bear": {"en": "a bear", "ru": "медведь", "de": "ein Bär", "fr": "un ours", "es": "un oso"},
    "horse": {
        "en": "a horse",
        "ru": "лошадь",
        "de": "ein Pferd",
        "fr": "un cheval",
        "es": "un caballo",
    },
    "sheep": {
        "en": "a sheep",
        "ru": "овца",
        "de": "ein Schaf",
        "fr": "un mouton",
        "es": "una oveja",
    },
    "cow": {"en": "a cow", "ru": "корова", "de": "eine Kuh", "fr": "une vache", "es": "una vaca"},
    "dog": {"en": "a dog", "ru": "собака", "de": "ein Hund", "fr": "un chien", "es": "un perro"},
    "cat": {"en": "a cat", "ru": "кошка", "de": "eine Katze", "fr": "un chat", "es": "un gato"},
    "bird": {
        "en": "a bird",
        "ru": "птица",
        "de": "ein Vogel",
        "fr": "un oiseau",
        "es": "un pájaro",
    },
    "bicycle": {
        "en": "a bicycle",
        "ru": "велосипед",
        "de": "ein Fahrrad",
        "fr": "un vélo",
        "es": "una bicicleta",
    },
    "motorcycle": {
        "en": "a motorcycle",
        "ru": "мотоцикл",
        "de": "ein Motorrad",
        "fr": "une moto",
        "es": "una motocicleta",
    },
    "bus": {"en": "a bus", "ru": "автобус", "de": "ein Bus", "fr": "un bus", "es": "un autobús"},
    "train": {"en": "a train", "ru": "поезд", "de": "ein Zug", "fr": "un train", "es": "un tren"},
    "truck": {
        "en": "a truck",
        "ru": "грузовик",
        "de": "ein Lastwagen",
        "fr": "un camion",
        "es": "un camión",
    },
    "boat": {
        "en": "a boat",
        "ru": "лодка",
        "de": "ein Boot",
        "fr": "un bateau",
        "es": "un barco",
    },
    "airplane": {
        "en": "an airplane",
        "ru": "самолёт",
        "de": "ein Flugzeug",
        "fr": "un avion",
        "es": "un avión",
    },
    "traffic-light": {
        "en": "a traffic light",
        "ru": "светофор",
        "de": "eine Ampel",
        "fr": "un feu de circulation",
        "es": "un semáforo",
    },
    "stop-sign": {
        "en": "a stop sign",
        "ru": "знак стоп",
        "de": "ein Stoppschild",
        "fr": "un panneau stop",
        "es": "una señal de stop",
    },
    "fire-hydrant": {
        "en": "a fire hydrant",
        "ru": "пожарный гидрант",
        "de": "ein Hydrant",
        "fr": "une bouche d'incendie",
        "es": "una boca de incendios",
    },
    "bench": {
        "en": "a bench",
        "ru": "скамейка",
        "de": "eine Bank",
        "fr": "un banc",
        "es": "un banco",
    },
    "umbrella": {
        "en": "an umbrella",
        "ru": "зонт",
        "de": "ein Regenschirm",
        "fr": "un parapluie",
        "es": "un paraguas",
    },
    "backpack": {
        "en": "a backpack",
        "ru": "рюкзак",
        "de": "ein Rucksack",
        "fr": "un sac à dos",
        "es": "una mochila",
    },
    "handbag": {
        "en": "a handbag",
        "ru": "сумочка",
        "de": "eine Handtasche",
        "fr": "un sac à main",
        "es": "un bolso",
    },
    "suitcase": {
        "en": "a suitcase",
        "ru": "чемодан",
        "de": "ein Koffer",
        "fr": "une valise",
        "es": "una maleta",
    },
    "tie": {
        "en": "a necktie",
        "ru": "галстук",
        "de": "eine Krawatte",
        "fr": "une cravate",
        "es": "una corbata",
    },
    "frisbee": {
        "en": "a frisbee",
        "ru": "фрисби",
        "de": "eine Frisbeescheibe",
        "fr": "un frisbee",
        "es": "un frisbee",
    },
    "skis": {"en": "skis", "ru": "лыжи", "de": "Skier", "fr": "des skis", "es": "unos esquís"},
    "snowboard": {
        "en": "a snowboard",
        "ru": "сноуборд",
        "de": "ein Snowboard",
        "fr": "un snowboard",
        "es": "una tabla de snowboard",
    },
    "kite": {
        "en": "a kite",
        "ru": "воздушный змей",
        "de": "ein Drachen",
        "fr": "un cerf-volant",
        "es": "una cometa",
    },
    "sports-ball": {
        "en": "a sports ball",
        "ru": "спортивный мяч",
        "de": "ein Sportball",
        "fr": "un ballon de sport",
        "es": "una pelota",
    },
    "baseball-bat": {
        "en": "a baseball bat",
        "ru": "бейсбольная бита",
        "de": "ein Baseballschläger",
        "fr": "une batte de baseball",
        "es": "un bate de béisbol",
    },
    "baseball-glove": {
        "en": "a baseball glove",
        "ru": "бейсбольная перчатка",
        "de": "ein Baseballhandschuh",
        "fr": "un gant de baseball",
        "es": "un guante de béisbol",
    },
    "skateboard": {
        "en": "a skateboard",
        "ru": "скейтборд",
        "de": "ein Skateboard",
        "fr": "une planche à roulettes",
        "es": "un monopatín",
    },
    "surfboard": {
        "en": "a surfboard",
        "ru": "доска для сёрфинга",
        "de": "ein Surfbrett",
        "fr": "une planche de surf",
        "es": "una tabla de surf",
    },
    "tennis-racket": {
        "en": "a tennis racket",
        "ru": "теннисная ракетка",
        "de": "ein Tennisschläger",
        "fr": "une raquette de tennis",
        "es": "una raqueta de tenis",
    },
    "bottle": {
        "en": "a bottle",
        "ru": "бутылка",
        "de": "eine Flasche",
        "fr": "une bouteille",
        "es": "una botella",
    },
    "wine-glass": {
        "en": "a wine glass",
        "ru": "бокал вина",
        "de": "ein Weinglas",
        "fr": "un verre à vin",
        "es": "una copa de vino",
    },
    "cup": {"en": "a cup", "ru": "чашка", "de": "eine Tasse", "fr": "une tasse", "es": "una taza"},
    "banana": {
        "en": "a banana",
        "ru": "банан",
        "de": "eine Banane",
        "fr": "une banane",
        "es": "un plátano",
    },
    "apple": {
        "en": "an apple",
        "ru": "яблоко",
        "de": "ein Apfel",
        "fr": "une pomme",
        "es": "una manzana",
    },
    "sandwich": {
        "en": "a sandwich",
        "ru": "бутерброд",
        "de": "ein Sandwich",
        "fr": "un sandwich",
        "es": "un sándwich",
    },
    "orange": {
        "en": "an orange",
        "ru": "апельсин",
        "de": "eine Orange",
        "fr": "une orange",
        "es": "una naranja",
    },
    "broccoli": {
        "en": "broccoli",
        "ru": "брокколи",
        "de": "Brokkoli",
        "fr": "du brocoli",
        "es": "brócoli",
    },
    "carrot": {
        "en": "a carrot",
        "ru": "морковь",
        "de": "eine Karotte",
        "fr": "une carotte",
        "es": "una zanahoria",
    },
    "pizza": {
        "en": "a pizza",
        "ru": "пицца",
        "de": "eine Pizza",
        "fr": "une pizza",
        "es": "una pizza",
    },
    "donut": {
        "en": "a donut",
        "ru": "пончик",
        "de": "ein Donut",
        "fr": "un beignet",
        "es": "una rosquilla",
    },
    "cake": {
        "en": "a cake",
        "ru": "торт",
        "de": "ein Kuchen",
        "fr": "un gâteau",
        "es": "un pastel",
    },
    "chair": {
        "en": "a chair",
        "ru": "стул",
        "de": "ein Stuhl",
        "fr": "une chaise",
        "es": "una silla",
    },
    "couch": {
        "en": "a couch",
        "ru": "диван",
        "de": "ein Sofa",
        "fr": "un canapé",
        "es": "un sofá",
    },
    "potted-plant": {
        "en": "a potted plant",
        "ru": "комнатное растение",
        "de": "eine Topfpflanze",
        "fr": "une plante en pot",
        "es": "una planta en maceta",
    },
    "bed": {"en": "a bed", "ru": "кровать", "de": "ein Bett", "fr": "un lit", "es": "una cama"},
    "dining-table": {
        "en": "a dining table",
        "ru": "обеденный стол",
        "de": "ein Esstisch",
        "fr": "une table à manger",
        "es": "una mesa de comedor",
    },
    "tv": {
        "en": "a television",
        "ru": "телевизор",
        "de": "ein Fernseher",
        "fr": "une télévision",
        "es": "un televisor",
    },
    "laptop": {
        "en": "a laptop",
        "ru": "ноутбук",
        "de": "ein Laptop",
        "fr": "un ordinateur portable",
        "es": "un portátil",
    },
    "cell-phone": {
        "en": "a mobile phone",
        "ru": "мобильный телефон",
        "de": "ein Handy",
        "fr": "un téléphone portable",
        "es": "un teléfono móvil",
    },
    "keyboard": {
        "en": "a keyboard",
        "ru": "клавиатура",
        "de": "eine Tastatur",
        "fr": "un clavier",
        "es": "un teclado",
    },
    "book": {"en": "a book", "ru": "книга", "de": "ein Buch", "fr": "un livre", "es": "un libro"},
    "clock": {
        "en": "a clock",
        "ru": "часы",
        "de": "eine Uhr",
        "fr": "une horloge",
        "es": "un reloj",
    },
    "vase": {"en": "a vase", "ru": "ваза", "de": "eine Vase", "fr": "un vase", "es": "un jarrón"},
    "teddy-bear": {
        "en": "a teddy bear",
        "ru": "плюшевый мишка",
        "de": "ein Teddybär",
        "fr": "un ours en peluche",
        "es": "un oso de peluche",
    },
    "surfer": {
        "en": "a surfer",
        "ru": "сёрфер",
        "de": "ein Surfer",
        "fr": "un surfeur",
        "es": "un surfista",
    },
}


@dataclass(frozen=True, slots=True)
class Corpus:
    """What the store holds, read once: vectors, and who carries which tag."""

    ids: list[str]
    vectors: np.ndarray
    tagged: Mapping[str, frozenset[str]]


@dataclass(frozen=True, slots=True)
class Measured:
    """One row: a language, and what embedded the query in it."""

    language: str
    #: Which tower asked. The baseline is the storage model's own text side;
    #: every other row is the encoder, including the one that asks in English —
    #: that row separates "the encoder is a different tower" from "the language
    #: costs something".
    asked_by: str
    recall: float
    worst: tuple[str, float]
    agreement: float


def read_corpus(settings: Settings) -> Corpus:
    """Every asset with a vector of the search model, and its tags.

    Read-only, and said so to the database rather than only meant: this
    measurement builds nothing and must not be able to.
    """

    async def read() -> Corpus:
        engine = create_engine(settings)
        try:
            async with engine.connect() as connection:
                await connection.execute(sa.text("SET TRANSACTION READ ONLY"))
                rows = (
                    await connection.execute(
                        sa.text(
                            "SELECT a.id::text AS id, a.tags, e.vector::text AS vector "
                            "FROM assets a JOIN embeddings e ON e.asset_id = a.id "
                            "WHERE e.model = :model ORDER BY a.id"
                        ),
                        {"model": CLIP_VIT_L14},
                    )
                ).all()
        finally:
            await engine.dispose()

        ids = [row.id for row in rows]
        vectors = np.array(
            [np.fromstring(row.vector.strip("[]"), sep=",") for row in rows], dtype=np.float32
        )
        tagged: dict[str, set[str]] = {}
        for row in rows:
            for tag in row.tags or ():
                tagged.setdefault(tag, set()).add(row.id)
        return Corpus(
            ids=ids,
            vectors=vectors,
            tagged={tag: frozenset(assets) for tag, assets in tagged.items()},
        )

    return asyncio.run(read())


def eligible(corpus: Corpus) -> list[str]:
    """The concepts this corpus can be asked about, by size alone."""
    return [
        tag
        for tag in CONCEPTS
        if MIN_ASSETS <= len(corpus.tagged.get(tag, frozenset())) <= MAX_ASSETS
    ]


def top(corpus: Corpus, query: np.ndarray) -> list[str]:
    """The `AT` nearest assets, ranked exactly rather than by the index."""
    scores = corpus.vectors @ query
    return [corpus.ids[index] for index in np.argsort(-scores)[:AT]]


def recall_at(found: Sequence[str], relevant: frozenset[str]) -> float:
    """How many of the pictures that carry the tag reached the page."""
    if not relevant:
        return 0.0
    return len(set(found) & relevant) / len(relevant)


def agreement_at(found: Sequence[str], baseline: Sequence[str]) -> float:
    """How much of the English page this page reproduces."""
    if not baseline:
        return 0.0
    return len(set(found) & set(baseline)) / len(baseline)


def measure(
    corpus: Corpus,
    concepts: Sequence[str],
    pages: Mapping[str, list[str]],
    baseline: Mapping[str, list[str]],
    language: str,
    asked_by: str,
) -> Measured:
    """One row of the table: the mean, the worst concept, the agreement.

    `baseline` is always the English CLIP page, and it is passed rather than
    looked up by language: asking the *encoder* in English is a legitimate row
    (`--languages en`), and it has to be compared with the baseline rather than
    with itself — which would make agreement 1.000 by construction and say
    nothing at all. The first version of this script did exactly that.
    """
    recalls = {concept: recall_at(pages[concept], corpus.tagged[concept]) for concept in concepts}
    agreements = [agreement_at(pages[concept], baseline[concept]) for concept in concepts]
    worst = min(recalls.items(), key=lambda pair: pair[1])
    return Measured(
        language=language,
        asked_by=asked_by,
        recall=float(np.mean(list(recalls.values()))),
        worst=worst,
        agreement=float(np.mean(agreements)),
    )


def claimed(row: Measured, baseline: Measured) -> bool:
    """Both conditions, because either alone can be passed by a bad answer."""
    return row.recall >= ABSOLUTE_FLOOR and row.recall >= RELATIVE_FLOOR * baseline.recall


def enough_concepts(concepts: Sequence[str]) -> bool:
    """Whether the corpus can be asked enough questions to mean anything."""
    return len(concepts) >= MIN_CONCEPTS


def usable_baseline(baseline: Measured) -> bool:
    """Whether the service's own model answers this concept set at all.

    If it does not, the set measures the corpus and its labels rather than any
    encoder, and nothing about the other languages may be published from it.
    """
    return baseline.recall >= ABSOLUTE_FLOOR


def report(
    corpus: Corpus,
    concepts: Sequence[str],
    rows: Sequence[Measured],
    settings: Settings,
) -> None:
    baseline = rows[0]
    print("## Multilingual queries\n")
    print(f"- corpus: {len(corpus.ids)} assets with a `{CLIP_VIT_L14}` vector")
    print(f"- concepts: {len(concepts)} tags carried by {MIN_ASSETS}–{MAX_ASSETS} assets each")
    print(f"- encoder: `{settings.mclip_model_name}` at `{settings.mclip_revision}`")
    print(f"- architecture config at `{settings.mclip_base_revision}`")
    print(
        f"- ranked exactly, at {AT}; a language is claimed at recall ≥ {ABSOLUTE_FLOOR} "
        f"and ≥ {RELATIVE_FLOOR} × the English baseline\n"
    )

    print("| language | asked by | mean recall@10 | worst concept | mean agreement@10 | claimed |")
    print("|---|---|---|---|---|---|")
    for index, row in enumerate(rows):
        # The baseline is the first row by construction rather than by its
        # language: a run may legitimately ask the encoder in English too.
        verdict = "baseline" if index == 0 else ("yes" if claimed(row, baseline) else "**no**")
        worst_tag, worst_value = row.worst
        print(
            f"| {row.language} | `{row.asked_by}` | {row.recall:.3f} "
            f"| {worst_tag} {worst_value:.3f} | {row.agreement:.3f} | {verdict} |"
        )

    print("\n| concept | assets carrying the tag | " + " | ".join(CONCEPTS[concepts[0]]) + " |")
    print("|---" * (2 + len(CONCEPTS[concepts[0]])) + "|")
    for concept in concepts:
        phrases = " | ".join(CONCEPTS[concept][language] for language in CONCEPTS[concept])
        print(f"| {concept} | {len(corpus.tagged[concept])} | {phrases} |")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--languages",
        default="ru,de,fr,es",
        help="Comma-separated, beside the English baseline. Default: ru,de,fr,es",
    )
    arguments = parser.parse_args()
    languages = [one.strip() for one in arguments.languages.split(",") if one.strip()]

    settings = Settings()  # type: ignore[call-arg]
    corpus = read_corpus(settings)
    if not corpus.ids:
        print("the store holds no vectors of the search model — run `make demo` first")
        return 2
    if corpus.vectors.shape[1] != dimension_of(CLIP_VIT_L14):
        print(f"unexpected vector width {corpus.vectors.shape[1]}")
        return 2

    concepts = eligible(corpus)
    if not enough_concepts(concepts):
        print(
            f"only {len(concepts)} of this corpus's tags are carried by "
            f"{MIN_ASSETS}–{MAX_ASSETS} assets, and {MIN_CONCEPTS} are needed: this measures the "
            "corpus rather than the encoder. Index more pictures and run it again."
        )
        return 2

    from app.ml.clip import ClipEmbedder
    from app.ml.mclip import MclipEmbedder

    english = ClipEmbedder.load(settings)
    encoder = MclipEmbedder.load(settings)

    baseline_vectors = english.embed_text([CONCEPTS[c][ENGLISH] for c in concepts]).vectors
    baseline_pages = {
        concept: top(corpus, baseline_vectors[index]) for index, concept in enumerate(concepts)
    }
    by_encoder: dict[str, dict[str, list[str]]] = {}
    for language in languages:
        asked = encoder.embed_text([CONCEPTS[c][language] for c in concepts]).vectors
        by_encoder[language] = {
            concept: top(corpus, asked[index]) for index, concept in enumerate(concepts)
        }

    rows = [
        measure(corpus, concepts, baseline_pages, baseline_pages, ENGLISH, CLIP_VIT_L14),
        *(
            measure(
                corpus, concepts, by_encoder[language], baseline_pages, language, MCLIP_XLMR_L14
            )
            for language in languages
        ),
    ]
    if not usable_baseline(rows[0]):
        print(
            f"the English baseline is {rows[0].recall:.3f}, below the floor of {ABSOLUTE_FLOOR}: "
            "this concept set measures the corpus rather than any encoder, and nothing is "
            "reported about the other languages."
        )
        return 2
    report(corpus, concepts, rows, settings)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
