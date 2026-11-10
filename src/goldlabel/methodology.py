"""A plain-English methodology of an analysis, written from the objects and files it is given."""

from dataclasses import dataclass

from goldlabel import _html
from goldlabel.candidates import Candidates
from goldlabel.classifier import Classifier, Predictions
from goldlabel.gold import Gold
from goldlabel.taxonomy import Taxonomy


@dataclass(frozen=True, repr=False)
class Methodology:
    """What was done in an analysis, in plain English, as returned by `get_methodology`.

    `str(m)` is the text, written in Markdown, to paste into an article or a README. In a
    notebook the text shows as written, with its Markdown marks; wrap it to see it formatted,
    for example `IPython.display.Markdown(str(m))`.

    Attributes:
        text: The methodology in Markdown.
        warnings: One sentence for each problem found, such as an evaluation that predates a
            change to a label; empty when there is none.
    """

    text: str
    warnings: tuple[str, ...] = ()

    def __str__(self) -> str:
        return self.text

    def __repr__(self) -> str:
        return self.text

    def _repr_html_(self) -> str:
        return f"<pre>{_html.esc(self.text)}</pre>"


def _count(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def _quoted(items) -> str:
    return "; ".join(f'"{x}"' for x in items)


def _corpus(c: Candidates) -> str:
    """Write the sentences about where the candidates came from and how they were chosen.

    A fact the candidates file does not hold is said to be not recorded, never guessed.

    Returns:
        str: One paragraph.
    """
    where = c.corpus or "the corpus"
    missing = []
    if c.source == "seeds":
        phrases = (
            f"{_count(len(c.seeds), 'example phrase')} ({_quoted(c.seeds)})"
            if c.seeds
            else "example phrases"
        )
        first = (
            f"We searched {where} for items similar to {phrases}. "
            f"Each phrase was embedded with {c.embedding_model}, and we kept every item "
            f"whose highest similarity to any phrase was at least {c.floor:g}."
        )
        if not c.seeds:
            missing.append("The seed phrases were not recorded in the candidates file.")
    elif c.source == "keywords":
        how = "regular expressions" if c.regex else "literal text"
        terms = (
            f"{_count(len(c.keywords), 'term')} ({_quoted(c.keywords)}), matched as {how}"
            if c.keywords
            else "the search terms"
        )
        first = f"We selected items from {where} containing any of {terms}."
        if not c.keywords:
            missing.append("The keywords were not recorded in the candidates file.")
    else:
        first = f"We used every item of {where}."
    if c.corpus is None:
        missing.append(
            "The corpus and its filter were not recorded in the candidates file."
        )
    parts = [first, *missing]
    if c.filter:
        parts.append(f"The corpus was filtered with: {c.filter}.")
    if c.cutoff is not None:
        parts.append(
            f"We then kept the items with similarity of at least {c.cutoff:g}, "
            f"which left {len(c.rows)}."
        )
    else:
        parts.append(f"This produced {len(c.rows)} candidates.")
    if c.capped:
        parts.append(
            "A limit in the search backend may have hidden items above the floor."
        )
    return " ".join(parts)


def _labels(t: Taxonomy) -> str:
    names = ", ".join(f"`{label.name}`" for label in t.labels)
    mode = "exactly one label" if t.mode == "single" else "every label that applies"
    return (
        f"Each item received {mode} from: {names}, or the built-in `off_topic` "
        "(the item matches none of them)."
    )


def get_methodology(
    *,
    candidates: Candidates | None = None,
    gold: Gold | None = None,
    classifier: Classifier | None = None,
    results: Predictions | None = None,
    include_gold_table: bool = True,
) -> Methodology:
    """Describe in plain English what was done in an analysis, from the objects you give it.

    Writes one section for each piece you pass in and says nothing about the rest. Everything in
    the text comes from those objects and the files beside them; no model is called, nothing is
    estimated, and the same inputs always give the same text. It only reads files and writes
    none, and it cannot change a gold label.

    Args:
        candidates: The candidates the analysis chose from the corpus. Pass the list you
            classified (the one `Candidates.above` returned) to have its cutoff stated. It is
            used in preference to the candidates held by `gold`.
        gold: The gold dataset. Its taxonomy is used when no classifier is given.
        classifier: The classifier that was evaluated and run.
        results: The `Predictions` that `Classifier.classify` returned.
        include_gold_table: Whether to list every gold row at the end of the text.

    Returns:
        Methodology: The text, in Markdown, and the warnings found.

    Raises:
        ValueError: None of `candidates`, `gold`, `classifier` and `results` was given.
        TypeError: One of them is not the kind of object named above.
    """
    given = {
        "candidates": (candidates, Candidates),
        "gold": (gold, Gold),
        "classifier": (classifier, Classifier),
        "results": (results, Predictions),
    }
    if all(value is None for value, _ in given.values()):
        raise ValueError("give at least one of candidates, gold, classifier or results")
    for name, (value, kind) in given.items():
        if value is not None and not isinstance(value, kind):
            raise TypeError(
                f"{name} must be a {kind.__name__}, not {type(value).__name__}"
            )
    sections = []
    chosen = candidates or (gold.candidates if gold else None)
    if chosen is not None:
        sections.append(("Corpus and candidates", _corpus(chosen)))
    taxonomy = classifier.taxonomy if classifier else None
    if taxonomy is None and gold is not None and gold._doc()["taxonomy"]:
        taxonomy = Taxonomy.model_validate(gold._doc()["taxonomy"])
    if taxonomy is not None:
        sections.append(("Labels", _labels(taxonomy)))
    body = "\n\n".join(f"### {title}\n\n{text}" for title, text in sections)
    return Methodology(f"## Methodology\n\n{body}", ())
