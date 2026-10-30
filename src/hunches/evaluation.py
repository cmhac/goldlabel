import json
import random
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from hunches import _frame, _html, _sync
from hunches.candidates import BANDS, band_of
from hunches.classifier import UNKNOWN_COST, Classifier, _dollars, _model_name
from hunches.gold import _page_stamp
from hunches.metrics import (
    Metrics,
    compute_metrics,
    default_target_metric,
    target_value,
)
from hunches.settings import resolve
from hunches.taxonomy import OFF_TOPIC, validate_labels


def _hunches_version() -> str | None:
    try:
        return version("hunches")
    except PackageNotFoundError:
        return None


@dataclass
class Evaluation:
    """`disagreements` rows are `{id, text, gold, predicted, reasoning}`; `predicted` is None for an item that failed."""

    metrics: Metrics
    metric: str
    target: float | None
    n: int
    skipped_pending: int
    sources: dict[
        str, int
    ]  # labelled rows by `labelled_by`: goldlabel-ui, imported, unstamped
    digest: str
    disagreements: list[dict]
    labels: list[str] = field(
        default_factory=list
    )  # every label incl. off_topic, for the table
    split: str = ""  # "dev", "test", or "mixed" when the rows span both

    def score(self, name: str | None = None) -> float:
        return target_value(self.metrics, name or self.metric)

    @property
    def passed(self) -> bool | None:
        return None if self.target is None else self.score() >= self.target

    def write(self, path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "time": datetime.now(UTC).isoformat(),
            "n": self.n,
            "skipped_pending": self.skipped_pending,
            "sources": self.sources,
            "digest": self.digest,
            "metric": self.metric,
            "target": self.target,
            "score": self.score(),
            "metrics": asdict(self.metrics),
            "disagreements": self.disagreements,
        }
        path.write_text(json.dumps(data, indent=2) + "\n")

    def disagreements_to_polars(self):
        return _frame.to_polars(self.disagreements)

    def disagreements_to_pandas(self):
        return _frame.to_pandas(self.disagreements)

    def _head(self) -> list[str]:
        m = self.metrics
        line = f"{self.metric} {self.score():.4f}"
        if self.target is not None:
            line += f" {'PASS' if self.passed else 'FAIL'} (target {self.target:.4f})"
        return [
            (
                f"Evaluation: {self.n} rows, {self.skipped_pending} pending rows skipped, "
                f"{len(self.disagreements)} disagreements"
            ),
            line,
            f"macro_f1 {m.macro_f1:.4f}, micro_f1 {m.micro_f1:.4f}",
        ]

    def _sources(self) -> str:
        return "sources: " + ", ".join(f"{k} {v}" for k, v in self.sources.items())

    def _repr_html_(self) -> str:
        per_label = [
            (
                name,
                f"{lm.precision:.2f}",
                f"{lm.recall:.2f}",
                f"{lm.f1:.2f}",
                lm.gold_count,
                lm.predicted_count,
            )
            for name, lm in self.metrics.per_label.items()
        ]
        rows = [
            (
                d["id"],
                d["text"],
                d["gold"],
                "ERROR" if d["predicted"] is None else d["predicted"],
                d["reasoning"],
            )
            for d in self.disagreements
        ]
        return (
            "".join(_html.line(x) for x in self._head())
            + _html.table(
                ["label", "precision", "recall", "f1", "gold", "predicted"], per_label
            )
            + _html.line(self._sources())
            + _html.details(
                f"{len(rows)} disagreements",
                _html.table(
                    ["id", "text", "gold", "predicted", "reasoning"], rows, cap=20
                ),
                open=True,
            )
        )

    def __repr__(self) -> str:
        m = self.metrics
        width = max([len(x) for x in self.labels] + [5])
        lines = self._head() + [
            f"{'label'.ljust(width)}  precision  recall  f1    gold  predicted",
        ]
        for name, lm in m.per_label.items():
            lines.append(
                f"{name.ljust(width)}  {lm.precision:9.2f}  {lm.recall:6.2f}  "
                f"{lm.f1:.2f}  {lm.gold_count:4}  {lm.predicted_count:9}"
            )
        lines.append(self._sources())
        return "\n".join(lines)


def evaluate(clf: Classifier, gold_set, **kwargs) -> Evaluation:
    """Same as `aevaluate`, for scripts and notebooks (also inside a running event loop)."""
    return _sync.run(aevaluate(clf, gold_set, **kwargs))


async def aevaluate(
    clf: Classifier, gold_set, *, metric=None, target=None, log=None
) -> Evaluation:
    """Classify the labelled rows of `gold_set` through `clf` (cached) and score them.

    Pending rows (no labels) are skipped and counted. Gold labels that are invalid for the
    taxonomy raise before any call. `target` adds PASS/FAIL to the repr. Every call appends one
    line to the evaluation log (`log=False`: none; a path: that file).
    """
    taxonomy = clf.taxonomy
    rows = [r for r in gold_set.rows if r.labels]
    bad = []
    for r in rows:
        try:
            validate_labels(r.labels or [], taxonomy)
        except ValueError:
            bad.append(r.id)
    if bad:
        raise ValueError(
            f"gold rows with labels that are invalid for the taxonomy: {bad}; "
            "gold.orphaned(taxonomy) lists them"
        )
    metric = metric or default_target_metric(taxonomy)
    preds = await clf.aclassify([{"id": r.id, "text": r.text} for r in rows])
    gold = [set(r.labels or []) for r in rows]
    predicted = [set(p["labels"] or []) for p in preds.rows]
    metrics = compute_metrics(gold, predicted, taxonomy.names)
    sources = {"goldlabel-ui": 0, "imported": 0, "unstamped": 0}
    for r in rows:
        key = _page_stamp(r.labelled_by)
        sources[key if key in sources else "unstamped"] += 1
    splits = {r.split for r in rows}
    split = "mixed" if len(splits) > 1 else (splits.pop() if splits else gold_set.name)
    evaluation = Evaluation(
        metrics=metrics,
        metric=metric,
        target=target,
        n=len(rows),
        skipped_pending=len(gold_set.rows) - len(rows),
        sources=sources,
        digest=clf.digest,
        disagreements=[
            {
                "id": rows[i].id,
                "text": rows[i].text,
                "gold": rows[i].labels,
                "predicted": preds.rows[i]["labels"],
                "reasoning": preds.rows[i].get("reasoning"),
            }
            for i in metrics.disagreements
        ],
        labels=taxonomy.names,
        split=split,
    )
    if log is not False:
        line = {
            "time": datetime.now(UTC).isoformat(),
            "split": split,
            "n": evaluation.n,
            "gold": None if gold_set.path is None else str(gold_set.path),
            "model": _model_name(clf.model),
            "digest": clf.digest,
            "prompt": clf.prompt,
            "taxonomy": taxonomy.model_dump(),
            "metric": metric,
            "target": target,
            "score": evaluation.score(),
            "metrics": asdict(metrics),
            "dollars": preds.cost,
            "live_calls": preds.live,
            "cached_calls": preds.cached,
            "hunches": _hunches_version(),
        }
        path = resolve(log, "evals.jsonl")
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a") as f:
            f.write(json.dumps(line) + "\n")
            f.flush()
    return evaluation


@dataclass
class EvalLog:
    rows: list[dict]

    def to_polars(self):
        return _frame.to_polars(self.rows)

    def to_pandas(self):
        return _frame.to_pandas(self.rows)

    def _test_line(self) -> str:
        test = [r for r in self.rows if r["split"] == "test"]
        return (
            f"test split evaluated {len(test)} times "
            f"({len({r['digest'] for r in test})} distinct prompts)"
        )

    def _repr_html_(self) -> str:
        if not self.rows:
            return _html.line("no evaluations logged yet")
        rows = [
            (
                r["time"][:16],
                r["split"],
                r["n"],
                f"{r['score']:.4f}",
                r["digest"][:8],
                r["model"],
            )
            for r in self.rows
        ]
        return _html.table(
            ["time", "split", "n", "score", "digest", "model"], rows
        ) + _html.line(self._test_line())

    def __repr__(self) -> str:
        lines = ["time              split  n     score   digest    model"]
        for r in self.rows:
            lines.append(
                f"{r['time'][:16]}  {r['split']:5}  {r['n']:<4}  {r['score']:.4f}  "
                f"{r['digest'][:8]}  {r['model']}"
            )
        lines.append(self._test_line())
        return "\n".join(lines)


def eval_log(path=None) -> EvalLog:
    """Read the evaluation log (default `<root>/evals.jsonl`); empty when there is none yet."""
    path = resolve(path, "evals.jsonl")
    if not path.exists():
        return EvalLog([])
    return EvalLog([json.loads(x) for x in path.read_text().splitlines() if x.strip()])


@dataclass
class BandReport:
    """`rows` are `{band, n, off_topic, rate}` for the bands that have candidates; failed items are in `errors`, not `n`."""

    rows: list[dict]
    cost: float | None  # None: a price is unknown (never 0)
    errors: int = 0

    def to_polars(self):
        return _frame.to_polars(self.rows)

    def to_pandas(self):
        return _frame.to_pandas(self.rows)

    def _repr_html_(self) -> str:
        rows = [
            (r["band"], r["n"], r["off_topic"], f"{r['rate']:.0%}") for r in self.rows
        ]
        out = _html.table(["band", "n", "off_topic", "rate"], rows)
        out += _html.line(f"cost {_dollars(self.cost)}, {self.errors} errors")
        return out + (_html.warning(UNKNOWN_COST) if self.cost is None else "")

    def __repr__(self) -> str:
        lines = ["band          n    off_topic  rate"]
        for r in self.rows:
            lines.append(
                f"{r['band']:12}  {r['n']:<3}  {r['off_topic']:<9}  {r['rate']:.0%}"
            )
        lines.append(f"cost {_dollars(self.cost)}, {self.errors} errors")
        if self.cost is None:
            lines.append(f"WARNING: {UNKNOWN_COST}")
        return "\n".join(lines)


def band_sample(clf: Classifier, candidates, *, per_band=30, seed=None) -> BandReport:
    """Classify up to `per_band` random candidates per similarity band and report the off-topic rate.

    Off-topic means the predicted labels are exactly `{off_topic}`. Nothing is written.
    """
    if candidates.source != "seeds":
        raise ValueError(
            f"band_sample needs similarity scores, but this list was built from "
            f"{candidates.source}, not from seeds"
        )
    rng = random.Random(seed)
    names = [
        f"{BANDS[i]:.3f}-{BANDS[i + 1]:.3f}"
        if i + 1 < len(BANDS)
        else f"{BANDS[i]:.3f}+"
        for i in range(len(BANDS))
    ]
    picked: list[tuple[int, dict]] = []
    for band in range(len(BANDS)):
        pool = [r for r in candidates.rows if band_of(r["max_similarity"]) == band]
        picked += [(band, r) for r in rng.sample(pool, min(per_band, len(pool)))]
    preds = clf.classify(
        [{"id": r["id"], "text": r["text"]} for _, r in picked], progress=False
    )
    rows = []
    for band in sorted({b for b, _ in picked}):
        labels = [p["labels"] for (b, _), p in zip(picked, preds.rows) if b == band]
        done = [x for x in labels if x is not None]
        off = sum(set(x) == {OFF_TOPIC} for x in done)
        rows.append(
            {
                "band": names[band],
                "n": len(done),
                "off_topic": off,
                "rate": off / len(done) if done else 0.0,
            }
        )
    return BandReport(rows, preds.cost, len(preds.errors))
