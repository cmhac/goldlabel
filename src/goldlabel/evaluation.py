import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from goldlabel import _frame, _html
from goldlabel.candidates import BANDS, band_of, order_by_id
from goldlabel.classifier import UNKNOWN_COST, Classifier, _dollars, _model_name
from goldlabel.metrics import (
    Metrics,
    compute_metrics,
    default_target_metric,
    target_value,
)
from goldlabel.taxonomy import OFF_TOPIC, validate_labels


def _goldlabel_version() -> str | None:
    try:
        return version("goldlabel")
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
    samples: tuple[str, ...] = ()  # the names of the samples it scored

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


def _rows_digest(rows) -> str:
    """What the evaluation saw of the gold rows: their ids and labels, in a fixed order."""
    data = sorted((r.id, sorted(r.labels)) for r in rows if r.labels)
    return hashlib.sha256(json.dumps(data).encode()).hexdigest()


def _history(log: Path, gold: Path) -> list[dict]:
    """The evaluation lines of `log` that scored samples of the gold file `gold`."""
    if not log.exists():
        return []
    target = gold.resolve()
    lines = [json.loads(x) for x in log.read_text().splitlines() if x.strip()]
    return [
        r
        for r in lines
        if "samples" in r and r.get("gold") and Path(r["gold"]).resolve() == target
    ]


def _counts(history: list[dict], names) -> tuple[int, int]:
    """Evaluations of exactly these samples, and how many distinct prompts they used."""
    mine = [r for r in history if r["samples"] == list(names)]
    return len(mine), len({r["digest"] for r in mine})


async def _aevaluate(
    clf: Classifier, sample, *, metric=None, target=None
) -> Evaluation:
    """Classify the labelled rows of `sample` through `clf` (cached) and score them.

    Pending rows (no labels) are skipped and counted. Gold labels that are invalid for the
    taxonomy raise before any call. `target` adds PASS/FAIL to the repr. Every evaluation is
    appended to `evals.jsonl` beside the gold file, unless the identical one is already there.
    """
    taxonomy = clf.taxonomy
    every = sample.rows
    rows = [r for r in every if r.labels]
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
        sources[r.labelled_by if r.labelled_by in sources else "unstamped"] += 1
    evaluation = Evaluation(
        metrics=metrics,
        metric=metric,
        target=target,
        n=len(rows),
        skipped_pending=len(every) - len(rows),
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
        samples=tuple(sample.names),
    )
    line = {
        "time": datetime.now(UTC).isoformat(),
        "samples": list(sample.names),
        "rows_digest": _rows_digest(rows),
        "n": evaluation.n,
        "skipped_pending": evaluation.skipped_pending,
        "gold": str(sample.path),
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
        "goldlabel": _goldlabel_version(),
        # the page joins each id to its text in the gold file, so the text is not copied here
        "disagreements": [
            {k: d[k] for k in ("id", "gold", "predicted", "reasoning")}
            for d in evaluation.disagreements
        ],
    }
    path = sample.path.parent / "evals.jsonl"
    same = ("samples", "rows_digest", "digest", "model", "metric", "target")
    if not any(
        all(r.get(k) == line[k] for k in same) for r in _history(path, sample.path)
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a") as f:
            f.write(json.dumps(line) + "\n")
            f.flush()
    return evaluation


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


async def _aband_sample(clf: Classifier, candidates, *, per_band=30) -> BandReport:
    """Classify up to `per_band` candidates per similarity band and report the off-topic rate.

    The rows of a band are picked in the id-fixed order (`order_by_id`), so a rerun picks the same
    ones. Off-topic means the predicted labels are exactly `{off_topic}`. Nothing is written.
    """
    if isinstance(per_band, bool) or not isinstance(per_band, int) or per_band < 1:
        raise ValueError(
            f"per_band must be a whole number of at least 1, not {per_band!r}"
        )
    if candidates.source != "seeds":
        raise ValueError(
            f"band_sample needs similarity scores, but this list was built from "
            f"{candidates.source}, not from seeds"
        )
    names = [
        f"{BANDS[i]:.3f}-{BANDS[i + 1]:.3f}"
        if i + 1 < len(BANDS)
        else f"{BANDS[i]:.3f}+"
        for i in range(len(BANDS))
    ]
    picked: list[tuple[int, dict]] = []
    for band in range(len(BANDS)):
        pool = [r for r in candidates.rows if band_of(r["max_similarity"]) == band]
        picked += [(band, r) for r in order_by_id(pool)[:per_band]]
    preds = await clf.aclassify(
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
