"""A plain-English methodology of an analysis, written from the objects and files it is given."""

from collections import Counter
from dataclasses import dataclass

from goldlabel import _html
from goldlabel._label import _revised_after, _when
from goldlabel.candidates import Candidates
from goldlabel.classifier import Classifier, Predictions, _model_name
from goldlabel.evaluation import _history
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


def _gold(gold: Gold) -> str:
    """Write the paragraph about who labelled what, from the gold file.

    Returns:
        str: The section text; no row text and no note text is copied.
    """
    rows = gold._read()
    if not rows:
        return f'The gold dataset "{gold.label}" holds no samples yet.'
    samples = gold._samples(rows)
    bullets = "\n".join(
        f"- **{name}**: {_count(len(rs), 'row')}, "
        f"{sum(1 for r in rs if r.labels)} labelled, {sum(1 for r in rs if not r.labels)} pending."
        for name, rs in samples.items()
    )
    labelled = [r for r in rows if r.labels]
    how = Counter(
        r.labelled_by if r.labelled_by in ("goldlabel-ui", "imported") else "none"
        for r in labelled
    )
    return (
        "People labelled items by hand, and the classifier was measured against their "
        f'labels. The gold dataset "{gold.label}" holds {_count(len(samples), "sample")}:'
        f"\n\n{bullets}\n\n"
        f"The {_count(len(labelled), 'labelled row')} by how they were labelled: "
        f"{how['goldlabel-ui']} in the labelling page, {how['imported']} imported "
        f"(labelled elsewhere), {how['none']} with no record. "
        f"Rows with a revised label or note: {sum(1 for r in rows if r.revisions)}. "
        f"Rows with a note: {sum(1 for r in rows if r.note)}. "
        "The number of people who labelled is not recorded."
    )


def _dollars(total: float) -> str:
    return f"${total:.2f}" if total == 0 or total >= 0.01 else f"${total:.4f}"


def _pick(history: list[dict], classifier: Classifier | None) -> list[tuple]:
    """Group the evaluation log by the samples scored and choose the line to report for each.

    A classifier is given the evaluation of its own prompt, not just the latest one; without
    one, or when none of its own was logged for a group, the latest line is used.

    Returns:
        list[tuple]: One `(sample names, every line of the group, the chosen line, whether the
        chosen line is the classifier's own)` per group, in the order the log first mentions them.
    """
    groups: dict[tuple, list[dict]] = {}
    for x in history:
        groups.setdefault(tuple(x["samples"]), []).append(x)
    picked = []
    for names, lines in groups.items():
        own = [x for x in lines if classifier and x.get("digest") == classifier.digest]
        chosen = max(own or lines, key=lambda x: str(x.get("time")))
        picked.append((names, lines, chosen, bool(own)))
    return picked


def _evaluation(history: list[dict], classifier: Classifier | None) -> str | None:
    """Write the paragraph on how the classifier scored against the gold labels.

    Returns:
        str | None: The section text, or None when there is no evaluation to describe.
    """
    intro = "The classifier was scored against the gold labels:\n\n"
    if not history:
        saved = classifier.evaluation if classifier else None
        if not saved:
            return None
        return (
            f"{intro}- **{' + '.join(saved['samples'])}**: {saved['metric']} "
            f"{saved['score']:.2f} on {_count(saved['n'], 'labelled row')}, evaluated "
            f"{saved['date'][:10]} (read from the classifier's saved bundle)."
        )
    bullets = []
    for names, lines, x, _ in _pick(history, classifier):
        target = x.get("target")
        if target is None:
            goal = "no target"
        else:
            goal = f"target {target:g}, {'met' if x['score'] >= target else 'not met'}"
        prompts = len({y.get("prompt") for y in lines})
        bullets.append(
            f"- **{' + '.join(names)}**: {x['metric']} {x['score']:.2f} on "
            f"{_count(x['n'], 'labelled row')} "
            f"({_count(x.get('skipped_pending', 0), 'pending row')} not scored), {goal}. "
            f"Latest evaluation {str(x['time'])[:10]}. Evaluated {_count(len(lines), 'time')} "
            f"with {_count(prompts, 'different prompt')}."
        )
    prices = [x.get("dollars") for x in history]
    known = [p for p in prices if p is not None]
    cost = (
        f"{_dollars(sum(known))} in total"
        if len(known) == len(prices)
        else "? (a price is unknown)"
    )
    return f"{intro}" + "\n".join(bullets) + f"\n\nEvaluation calls cost {cost}."


def _run(results: Predictions, cutoff: float | None) -> str:
    """Write the paragraph on the classification run, from the result rows.

    Returns:
        str: The section text. The model and times come from the stamps `classify` puts on
        each row.
    """
    n = len(results.rows)
    models = sorted({r["run_model"] for r in results.rows if r.get("run_model")})
    times = sorted(r["run_at"][:10] for r in results.rows if r.get("run_at"))
    by = f" by {', '.join(f'`{m}`' for m in models)}" if models else ""
    when = ""
    if times:
        when = (
            f" on {times[0]}"
            if times[0] == times[-1]
            else f" between {times[0]} and {times[-1]}"
        )
    cost = "? (a price is unknown)" if results.cost is None else _dollars(results.cost)
    text = (
        f"{_count(n, 'item')} {'was' if n == 1 else 'were'} classified{by}{when}: "
        f"{results.live} by live model calls, {results.cached} from the cache, "
        f"{results.resumed} resumed from an earlier run, {len(results.errors)} failed. "
        f"The live model calls cost {cost}."
    )
    bare = sum(1 for r in results.rows if not (r.get("run_model") and r.get("run_at")))
    if bare:
        text += f" The model and time were not recorded on {bare} of the {n} rows."
    scores = [r["max_similarity"] for r in results.rows if "max_similarity" in r]
    lowest = (
        f"lowest similarity among the items was {min(scores):g}" if scores else None
    )
    if cutoff is not None or scores:
        was = "was not recorded" if cutoff is None else f"was {cutoff:g}"
        text += f" The similarity cutoff {was}" + (
            f"; the {lowest}." if lowest else "."
        )
    return text


def _other_run(classifier: Classifier | None, results: Predictions | None) -> bool:
    """Ask whether the result rows were stamped by a classifier other than the one given.

    Returns:
        bool: True when a row's `run` digest differs from the classifier's.
    """
    if classifier is None or results is None:
        return False
    return bool({r["run"] for r in results.rows if "run" in r} - {classifier.digest})


def _cell(value) -> str:
    """Make a value safe inside one Markdown table cell: a pipe is escaped, a line break becomes `<br>`.

    Returns:
        str: The value as one line of text.
    """
    # shortcut: a backslash in a row's text is not escaped, upgrade if a text can end in one before a pipe
    text = str(value).replace("|", "\\|")
    return text.replace("\r\n", "<br>").replace("\n", "<br>").replace("\r", "<br>")


def _appendix(
    gold: Gold | None,
    classifier: Classifier | None,
    results: Predictions | None,
    include_gold_table: bool,
) -> str | None:
    """Write the appendix: the model, the exact prompt, the labels and the gold dataset.

    Returns:
        str | None: The text, or None when there is nothing to put in it. A note is never copied.
    """
    parts = []
    if classifier is not None:
        parts.append(f"**Model**: `{_model_name(classifier.model)}`")
        if _other_run(classifier, results):
            parts.append(
                "**Prompt**: not given, because the results were produced by a different "
                "classifier from the one passed in, so its prompt is not the prompt of the run."
            )
        else:
            quoted = "\n".join(
                f"> {x}" if x else ">" for x in classifier.prompt.split("\n")
            )
            parts.append(f"**Prompt** (exactly as stored):\n\n{quoted}")
        labels = [
            f"- `{label.name}`: {label.description}"
            if label.description
            else f"- `{label.name}`"
            for label in classifier.taxonomy.labels
        ]
        labels.append("- `off_topic`: The item matches none of the labels above.")
        parts.append("**Labels**\n\n" + "\n".join(labels))
    rows = gold._read() if gold is not None and include_gold_table else []
    if rows:
        by = {"goldlabel-ui": "labelling page", "imported": "imported"}
        lines = [
            "| sample | id | text | label | labelled by |",
            "|---|---|---|---|---|",
        ]
        for r in rows:
            cells = (
                r.sample,
                r.id,
                r.text,
                ", ".join(r.labels) if r.labels else "(pending)",
                by.get(r.labelled_by, "unstamped") if r.labels else "",
            )
            lines.append("| " + " | ".join(_cell(x) for x in cells) + " |")
        parts.append("**Gold dataset**\n\n" + "\n".join(lines))
    return "\n\n".join(parts) or None


def _warnings(
    gold: Gold | None,
    classifier: Classifier | None,
    results: Predictions | None,
    candidates: Candidates | None,
    history: list[dict],
) -> list[str]:
    """Find the real problems: a stale score, and pieces that do not belong together.

    Evaluating a sample many times is not one; tuning does that.

    Returns:
        list[str]: One sentence for each problem, in a fixed order.
    """
    found = []
    rows = gold._read() if gold is not None else []
    for names, _, x, _ in _pick(history, classifier):
        when = _when(x.get("time"))
        revised = sum(1 for r in rows if r.sample in names and _revised_after(r, when))
        if revised:
            found.append(
                f"The {' + '.join(names)} evaluation of {str(x['time'])[:10]} predates a "
                f"revision of {_count(revised, 'gold label')}; its score may no longer match "
                "the labels."
            )
    if classifier is not None and history:
        if classifier.digest not in {x.get("digest") for x in history}:
            found.append(
                "The classifier passed in is not the one that was evaluated: its prompt, "
                "model or labels differ from every logged evaluation."
            )
        else:
            found += [
                f"The {' + '.join(names)} score shown is from a different prompt than the "
                "classifier passed in (no evaluation of it was logged for that sample)."
                for names, _, _, own in _pick(history, classifier)
                if not own
            ]
    stored = gold._doc()["taxonomy"] if gold is not None else None
    if classifier is not None and stored and classifier.taxonomy.model_dump() != stored:
        found.append(
            "The classifier's labels differ from the labels stored in the gold file."
        )
    if _other_run(classifier, results):
        found.append(
            "The results were produced by a different classifier from the one passed in."
        )
    if gold is not None and candidates is not None and candidates.cutoff is None:
        ids = {str(r["id"]) for r in candidates.rows}
        missing = sum(1 for r in rows if r.id not in ids)
        if missing:
            found.append(f"Gold rows not among the candidates passed in: {missing}.")
    return found


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
    history = _history(gold.path.parent / "evals.jsonl", gold.path) if gold else []
    if gold is not None:
        sections.append(("Gold labels", _gold(gold)))
    if classifier is not None:
        text = f"The classifier uses the model `{_model_name(classifier.model)}`."
        if history:
            prompts = len({x.get("prompt") for x in history})
            text += f" Different prompts evaluated against the gold labels: {prompts}."
        sections.append(("Classifier", text))
    evaluation = _evaluation(history, classifier)
    if evaluation:
        sections.append(("Evaluation", evaluation))
    if results is not None:
        sections.append(("Run", _run(results, chosen.cutoff if chosen else None)))
    found = _warnings(gold, classifier, results, chosen, history)
    if found:
        sections.append(("Warnings", "\n".join(f"- {w}" for w in found)))
    appendix = _appendix(gold, classifier, results, include_gold_table)
    if appendix:
        sections.append(("Appendix", appendix))
    body = "\n\n".join(f"### {title}\n\n{text}" for title, text in sections)
    return Methodology(f"## Methodology\n\n{body}", tuple(found))
