"""The classifier: an LLM that sorts texts into the labels of a taxonomy, with its cache and cost limit."""

import asyncio
import hashlib
import json
import sys
import time
import warnings
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel
from pydantic_ai import Agent, ModelRetry
from pydantic_ai.exceptions import (
    ModelAPIError,
    ModelHTTPError,
    UnexpectedModelBehavior,
)
from pydantic_ai.models import Model

from goldlabel import _frame, _html, _sync
from goldlabel._gold_rule import GoldError
from goldlabel.cost import (
    cache_get,
    cache_key,
    cache_put,
    items_per_second,
    messages_dollars,
    per_call_dollars,
    record,
    record_timing,
)
from goldlabel.taxonomy import Taxonomy, all_labels, validate_labels


@dataclass
class Prediction:
    """The model's answer for one text: the labels, or the error that stopped it."""

    labels: list[str] | None  # None when `error` is set
    error: str | None = None  # validation retries exhausted or the model call failed
    cached: bool = False
    reasoning: str | None = None  # None when `error` is set
    dollars: float | None = (
        0.0  # what this call cost; 0.0 for a cache hit, None if unpriced
    )
    api_error: bool = False  # `error` is a model API error (not a validation failure)


# Stop a run after this many model API errors in a row (completion order, cache hits ignored): an
# outage or a bad setting would otherwise fail, and bill the retries of, every remaining item.
MAX_API_ERRORS_IN_A_ROW = 5
# These statuses mean every item would fail the same way, so the run stops at the first one.
FATAL_STATUSES = (401, 403)


class CostLimit(Exception):
    """`max_cost` would be (or was) exceeded, or cannot be honoured because the price is unknown."""


def system_prompt(prompt: str, taxonomy: Taxonomy) -> str:
    """Build the instructions sent to the model: the prompt, then the labels and the rules.

    This whole string is what the cache key hashes.

    Returns:
        str: The prompt text, the label list with descriptions, the one-or-many-labels rule,
        the `off_topic` rule and the reasoning instruction.
    """
    lines = [prompt.strip(), "", "Labels:"]
    lines += [f"- {label.name}: {label.description}" for label in taxonomy.labels]
    lines.append("- off_topic: the item matches none of the labels above")
    rule = (
        "Return exactly one label."
        if taxonomy.mode == "single"
        else "Return every label that applies."
    )
    lines.append(f"{rule} off_topic must never be combined with another label.")
    lines.append(
        "First give a short reasoning (one to three sentences) that names the "
        "evidence in the text, then the labels."
    )
    return "\n".join(lines)


def _model_name(model: str | Model) -> str:
    return model if isinstance(model, str) else model.model_name


def _dollars(value: float | None) -> str:
    return "?" if value is None else f"${value:.4f}"


def _rows(items) -> list[dict]:
    """Normalise `items`: strings (id = position), dicts with `id` and `text`, or an object with `.rows`.

    Returns:
        list[dict]: One dict with `id` and `text` (and any other fields) per item.
    """
    if hasattr(items, "rows"):
        items = items.rows
    return [
        {"id": i, "text": item} if isinstance(item, str) else dict(item)
        for i, item in enumerate(items)
    ]


UNKNOWN_COST = "the price is unknown, so the cost is unknown, not zero"
PREVIEW_LINES = 12
PRICE_UNKNOWN = (
    "the price is unknown (no priced call recorded for this model), "
    "so the cost is unknown, not zero"
)


@dataclass(frozen=True)
class Estimate:
    """What `Classifier.estimate` expects a run to cost, before any model is called.

    Attributes:
        n: Number of items.
        cached: Items already answered in the cache (free).
        live: Items that would need a model call.
        dollars: Expected cost of the live calls, or None when the price of the
            model is unknown (never 0, which would look free).
        seconds: Expected run time, or None until a run has been timed.
    """

    n: int
    cached: int
    live: int
    dollars: float | None  # None: the price is unknown (never 0)
    seconds: float | None  # None: no timing recorded yet

    def _lines(self) -> list[str]:
        cost = "?" if self.dollars is None else f"~${self.dollars:.4f}"
        time = "?" if self.seconds is None else f"~{self.seconds:.0f}s"
        return [
            f"Estimate: {self.n} items, {self.cached} cached, {self.live} live calls",
            f"cost {cost}, time {time}",
        ]

    def _repr_html_(self) -> str:
        out = "".join(_html.line(x) for x in self._lines())
        return out + (_html.warning(PRICE_UNKNOWN) if self.dollars is None else "")

    def __repr__(self) -> str:
        lines = self._lines()
        if self.dollars is None:
            lines.append(f"WARNING: {PRICE_UNKNOWN}")
        return "\n".join(lines)


@dataclass
class Predictions:
    """The result of `Classifier.classify`: one row per item, in the order given.

    Attributes:
        rows: One dict per item with `id`, `text`, `labels`, `reasoning` (or `error` when the
            item failed) and any other fields of the input.
        live: Model calls made in this run.
        cached: Items answered from the cache, which cost nothing.
        resumed: Items already in the `out` file from an earlier run, not asked again.
        cost: Dollars spent by the live calls, or None if any price is unknown.
    """

    rows: list[dict]
    live: int = 0  # calls made now
    cached: int = 0  # answered from the cache
    resumed: int = 0  # already in `out` under this run, not asked again
    cost: float | None = (
        0.0  # dollars spent by the live calls; None if any price is unknown
    )

    @property
    def errors(self) -> list[dict]:
        """The rows of the items that failed, each with an `error` message."""
        return [r for r in self.rows if r.get("error")]

    @property
    def labels(self) -> list[list[str] | None]:
        """Each row's list of labels, in row order; None for an item that failed."""
        return [r["labels"] for r in self.rows]

    def to_polars(self):
        """Return the rows as a polars DataFrame.

        Returns:
            polars.DataFrame: One row per item.
        """
        return _frame.to_polars(self.rows)

    def to_pandas(self):
        """Return the rows as a pandas DataFrame.

        Returns:
            pandas.DataFrame: One row per item.
        """
        return _frame.to_pandas(self.rows)

    def _lines(self) -> list[str]:
        counts = (
            f"{len(self.rows)} items, {self.live} live, {self.cached} cached, "
            f"{self.resumed} resumed from out, {len(self.errors)} errors"
        )
        return [f"Predictions: {counts}", f"cost {_dollars(self.cost)}"]

    def _repr_html_(self) -> str:
        rows = [
            (
                r["id"],
                r["text"],
                f"ERROR: {r['error']}" if r.get("error") else r["labels"],
                r.get("reasoning"),
            )
            for r in self.rows
        ]
        out = "".join(_html.line(x) for x in self._lines())
        if self.cost is None:
            out += _html.warning(UNKNOWN_COST)
        return out + _html.table(["id", "text", "labels", "reasoning"], rows)

    def __repr__(self) -> str:
        lines = self._lines()
        if self.cost is None:
            lines.append(f"WARNING: {UNKNOWN_COST}")
        return "\n".join(lines)


def _stderr_line(done: int, total: int, info: dict) -> None:
    sys.stderr.write(
        f"\r{done}/{total}  {info['live']} live, {info['cached']} cached, "
        f"{info['errors']} errors, cost {_dollars(info['cost'])}"
    )
    if done == total:
        sys.stderr.write("\n")
    sys.stderr.flush()


def _reporter(progress):
    if callable(progress):
        return progress
    if progress and (sys.stderr.isatty() or "ipykernel" in sys.modules):
        return _stderr_line
    return None


@dataclass(frozen=True)
class Classifier:
    """An LLM that sorts texts into the labels of a taxonomy, following a prompt.

    A classifier is never changed in place: `with_prompt` and `with_taxonomy` return a new one.

    Attributes:
        model: The model name as "provider:model-name" (for example "openai:gpt-6-luna") or a model object.
        taxonomy: The labels the model chooses from, and whether an item gets one label or several.
        prompt: The instructions the model follows. The label list is added after it
            automatically; see `with_prompt`.
        cache: Where answers are remembered: a directory, None for `<settings.root>/cache`,
            or False for no cache. A cached answer costs nothing and is reused only for the
            same model, prompt, taxonomy and text.
        evaluation: The evaluation recorded in a bundle by `save`, set by `load`; None otherwise.
    """

    model: str | Model
    taxonomy: Taxonomy
    prompt: str
    cache: object = None
    evaluation = (
        None  # set by `load` from evaluation.json; not a field, so `replace` drops it
    )

    def save(self, dir, evaluation=None) -> None:
        """Write the classifier to a folder so it can be reloaded with `load`.

        Writes `classifier.yaml` (the model), `taxonomy.yaml`, `prompt.md` and, when an
        evaluation is given, `evaluation.json`. Existing files of those names are overwritten;
        anything else in the folder is left alone. The cache location is not saved.

        Args:
            dir: The folder to write; created if it does not exist.
            evaluation: An `Evaluation` (from `evaluate`) to record beside the classifier, or
                None to write no `evaluation.json`.
        """
        dir = Path(dir)
        dir.mkdir(parents=True, exist_ok=True)
        (dir / "classifier.yaml").write_text(
            yaml.safe_dump({"model": _model_name(self.model)}, sort_keys=False)
        )
        self.taxonomy.write(dir / "taxonomy.yaml")
        (dir / "prompt.md").write_text(self.prompt.rstrip("\n") + "\n")
        if evaluation is not None:
            data = {
                "samples": list(evaluation.samples),
                "n": evaluation.n,
                "score": evaluation.score(),
                "metric": evaluation.metric,
                "metrics": asdict(evaluation.metrics),
                "digest": evaluation.digest,
                "date": datetime.now(UTC).isoformat(),
                "sources": evaluation.sources,
            }
            (dir / "evaluation.json").write_text(json.dumps(data, indent=2) + "\n")

    @classmethod
    def load(cls, dir, *, cache=None) -> "Classifier":
        """Read a classifier from a folder written by `save`.

        Args:
            dir: The folder holding `classifier.yaml`, `taxonomy.yaml` and `prompt.md`.
            cache: Where to remember answers; as the `cache` field of `Classifier`.

        Returns:
            Classifier: The saved model, taxonomy and prompt. Its `evaluation` is the one
            recorded in the folder, if any. A warning is raised when that evaluation no longer
            matches the model, prompt and taxonomy (the files were edited after it ran).
        """
        dir = Path(dir)
        spec = yaml.safe_load((dir / "classifier.yaml").read_text())
        clf = cls(
            spec["model"],
            Taxonomy.read(dir / "taxonomy.yaml"),
            (dir / "prompt.md").read_text(),
            cache=cache,
        )
        path = dir / "evaluation.json"
        evaluation = json.loads(path.read_text()) if path.exists() else None
        if evaluation is not None and evaluation["digest"] != clf.digest:
            warnings.warn(
                f"the evaluation recorded in {path} no longer matches this prompt, model and "
                "taxonomy (the bundle was edited after it was evaluated)",
                UserWarning,
                stacklevel=2,
            )
        object.__setattr__(clf, "evaluation", evaluation)
        return clf

    def _repr_html_(self) -> str:
        names = ", ".join(self.taxonomy.names)
        lines = self.prompt.strip().splitlines()
        preview = "\n".join(lines[:PREVIEW_LINES])
        out = [
            _html.line(
                f"Classifier: model {_model_name(self.model)}, digest {self.digest[:12]}"
            ),
            _html.line(f"{self.taxonomy.mode}-label: {names}"),
            f"<pre>{_html.esc(preview)}</pre>",
        ]
        if len(lines) > PREVIEW_LINES:
            out.append(
                _html.line(f"{len(lines) - PREVIEW_LINES} more lines in the prompt")
            )
        ev = self.evaluation
        if ev is None:
            out.append(_html.line("no evaluation recorded"))
        else:
            out.append(
                _html.line(
                    f"evaluation: {ev['metric']} {ev['score']:.4f} on {' + '.join(ev['samples'])} "
                    f"({ev['n']} rows, {ev['date'][:10]})"
                )
            )
        return "".join(out)

    def with_prompt(self, text: str) -> "Classifier":
        """Return a copy of this classifier that follows different instructions.

        `text` replaces the current prompt; it is not added to it. The model always receives
        your text first, then, added by goldlabel: the list of labels with their descriptions,
        the rule for one label or several, the rule that `off_topic` is never combined with
        another label, and an instruction to give a short reasoning first. Write only the
        task instructions in `text`; do not repeat the labels.

        This classifier is unchanged. The copy has the same model, taxonomy and cache, but no
        recorded `evaluation`. Because the prompt is part of the cache key, answers cached under
        the old prompt are not reused: the next `classify` or `evaluate` calls the model again
        for every item (use `estimate` first to see the cost).

        Args:
            text: The new instructions, as plain text.

        Returns:
            Classifier: A new classifier with `prompt` equal to `text`.
        """
        return replace(self, prompt=text)

    def with_taxonomy(self, taxonomy: Taxonomy) -> "Classifier":
        """Return a copy of this classifier that chooses from different labels.

        Replaces the whole taxonomy (labels, descriptions and the one-or-many-labels mode), not
        just one label. The prompt text is kept as it is; the new label list is added after it.
        This classifier is unchanged, and the copy has no recorded `evaluation`. Answers cached
        under the old labels are not reused, so the next run calls the model again for every item.

        Args:
            taxonomy: The new `Taxonomy`.

        Returns:
            Classifier: A new classifier with `taxonomy` replaced.
        """
        return replace(self, taxonomy=taxonomy)

    @property
    def digest(self) -> str:
        """A fingerprint of the model, prompt and taxonomy.

        Two classifiers with the same digest give the same cached answers; a different digest
        means a changed prompt, label list or model, so nothing is reused from the cache.
        """
        data = [_model_name(self.model), system_prompt(self.prompt, self.taxonomy)]
        return hashlib.sha256(json.dumps(data).encode()).hexdigest()

    def _key(self, text: str) -> str:
        system = system_prompt(self.prompt, self.taxonomy)
        return cache_key(_model_name(self.model), system, text)

    def _hit(self, text: str) -> dict | None:
        """Look a text up in the cache; an old-shape entry (a bare label list) is a miss.

        Returns:
            dict | None: The cached output, or None when there is none.
        """
        hit = cache_get(self.cache, self._key(text))
        return (
            hit["output"]
            if hit is not None and isinstance(hit["output"], dict)
            else None
        )

    def estimate(self, items) -> Estimate:
        """Say what classifying `items` would cost, without calling a model.

        Counts the items already in the cache (free) and the ones that need a live call, and
        prices the live ones from the cost of earlier calls recorded in the cache folder.

        Args:
            items: Strings (their id is their position), dicts with `id` and `text`, or an
                object with `.rows`, such as `Candidates`.

        Returns:
            Estimate: Item counts, expected dollars (None if the price is unknown) and seconds.
        """
        return self._estimate([r["text"] for r in _rows(items)])

    def _estimate(self, texts: list[str]) -> Estimate:
        cached = sum(self._hit(t) is not None for t in texts)
        live = len(texts) - cached
        name = _model_name(self.model)
        if live == 0:
            return Estimate(len(texts), cached, 0, 0.0, 0.0)
        per_call, _ = per_call_dollars(self.cache, name)
        rate = items_per_second(self.cache, "classify")
        return Estimate(
            len(texts),
            cached,
            live,
            None if per_call is None else per_call * live,
            None if rate is None else live / rate,
        )

    async def _predict(self, text: str) -> Prediction:
        """Classify one text. Cache hits cost nothing; failures are not cached.

        Returns:
            Prediction: The labels, or the error that stopped the call.

        Raises:
            ModelAPIError: The service refused the key (HTTP 401 or 403): every item would fail
                the same way, so the run stops.
        """
        system = system_prompt(self.prompt, self.taxonomy)
        name = _model_name(self.model)
        key = self._key(text)
        taxonomy = self.taxonomy
        if (out := self._hit(text)) is not None:
            return Prediction(out["labels"], cached=True, reasoning=out["reasoning"])

        # a Literal built at runtime from the taxonomy; the type checker can't see through it
        label_type = Literal[tuple(all_labels(taxonomy))]  # ty: ignore[invalid-type-form]

        class Classification(BaseModel):
            reasoning: str  # declared first so the model explains before it decides
            labels: list[label_type]

        agent = Agent(self.model, output_type=Classification, system_prompt=system)

        @agent.output_validator
        def check(out: Classification) -> Classification:
            try:
                validate_labels(out.labels, taxonomy)
            except ValueError as e:
                raise ModelRetry(str(e)) from e
            return out

        try:
            result = await agent.run(text)
        except UnexpectedModelBehavior as e:
            return Prediction(None, error=e.message)
        except ModelAPIError as e:
            if isinstance(e, ModelHTTPError) and e.status_code in FATAL_STATUSES:
                raise
            return Prediction(None, error=e.message, api_error=True)
        usage = result.usage
        dollars = messages_dollars(result.new_messages())
        record(self.cache, name, usage, dollars)
        out = result.output
        cache_put(
            self.cache,
            key,
            {"labels": list(out.labels), "reasoning": out.reasoning},
            usage,
        )
        return Prediction(list(out.labels), reasoning=out.reasoning, dollars=dollars)

    def evaluate(self, sample, *, metric=None, target=None):
        """Score this classifier against the people's labels in a gold sample.

        Same as `aevaluate`, for scripts and notebooks (also inside a running event loop).
        This makes live model calls (cached answers are free) and, unless the same evaluation
        was already logged, appends a line to `evals.jsonl` beside the gold file.

        Args:
            sample: A `Sample` from `gold.draw_sample(...)`; its labelled rows are classified
                and its pending rows are skipped and counted.
            metric: The score to report: "accuracy", "exact_match" (the same number),
                "macro_f1" or "micro_f1". None picks accuracy for single-label taxonomies and
                macro_f1 for multi-label ones.
            target: A score between 0 and 1 the classifier should reach; `Evaluation.passed` and
                the printout then say PASS or FAIL. None for no target.

        Returns:
            Evaluation: The score, per-label results and the rows the model got wrong.

        Raises:
            GoldError: `sample` is not a `Sample`.
            ValueError: A labelled row uses a label that is not in this taxonomy.
        """
        return _sync.run(self.aevaluate(sample, metric=metric, target=target))

    async def aevaluate(self, sample, *, metric=None, target=None):
        """Score this classifier against the people's labels in a gold sample (async).

        The async form of `evaluate`: it classifies the labelled rows of `sample` (cached answers
        are free) and scores them. Every evaluation is appended to `evals.jsonl` beside the gold
        file, except an identical rerun. Pending rows are skipped and counted.

        Args:
            sample: A `Sample` from `gold.draw_sample(...)`.
            metric: The score to report: "accuracy", "exact_match" (the same number),
                "macro_f1" or "micro_f1". None picks accuracy for single-label taxonomies and
                macro_f1 for multi-label ones.
            target: A score between 0 and 1 the classifier should reach; `Evaluation.passed` and
                the printout then say PASS or FAIL. None for no target.

        Returns:
            Evaluation: The score, per-label results and the rows the model got wrong.

        Raises:
            GoldError: `sample` is not a `Sample`.
            ValueError: A labelled row uses a label that is not in this taxonomy.
        """
        from goldlabel.evaluation import _aevaluate  # evaluation imports this module
        from goldlabel.gold import Sample

        if not isinstance(sample, Sample):
            raise GoldError(
                f"evaluate a Sample, not {type(sample).__name__}: "
                'dev = gold.draw_sample("dev"), then clf.evaluate(dev)'
            )
        return await _aevaluate(self, sample, metric=metric, target=target)

    def band_sample(self, candidates, *, per_band=30):
        """Measure how many candidates are off topic in each similarity band.

        Classifies up to `per_band` candidates from each band of `candidates` (live model calls,
        cached answers are free) so you can see where similarity stops being useful. Writes no
        file.

        Args:
            candidates: A `Candidates` from `get_candidates(seeds=...)`; lists built from
                keywords or the whole corpus have no similarity scores and are refused.
            per_band: How many candidates to classify in each band (a whole number, at least 1).

        Returns:
            BandReport: The off-topic rate for each band that has candidates.

        Raises:
            ValueError: `per_band` is not a whole number of at least 1, or `candidates` was not
                built from seeds.
        """
        return _sync.run(self.aband_sample(candidates, per_band=per_band))

    async def aband_sample(self, candidates, *, per_band=30):
        """Measure how many candidates are off topic in each similarity band (async).

        The async form of `band_sample`; see it for what is classified and written.

        Args:
            candidates: A `Candidates` from `get_candidates(seeds=...)`.
            per_band: How many candidates to classify in each band (a whole number, at least 1).

        Returns:
            BandReport: The off-topic rate for each band that has candidates.

        Raises:
            ValueError: `per_band` is not a whole number of at least 1, or `candidates` was not
                built from seeds.
        """
        from goldlabel.evaluation import _aband_sample  # evaluation imports this module

        return await _aband_sample(self, candidates, per_band=per_band)

    def classify(self, items, **kwargs) -> Predictions:
        """Classify texts with the model, for scripts and notebooks.

        Same as `aclassify` (see it for every argument), and also works inside a running event
        loop. Makes live model calls for items not in the cache, which costs money: use
        `estimate` first, or pass `max_cost`.

        Args:
            items: Strings, dicts with `id` and `text`, or an object with `.rows`.
            **kwargs: `out`, `max_cost`, `concurrency` and `progress`, as for `aclassify`.

        Returns:
            Predictions: One row per item.

        Raises:
            CostLimit: `max_cost` was given and would be, or was, exceeded.
            ModelAPIError: The model's service refused the key (401/403) or failed five times
                in a row; rows finished before that are kept.
        """
        return _sync.run(self.aclassify(items, **kwargs))

    async def aclassify(
        self,
        items,
        *,
        out=None,
        max_cost: float | None = None,
        concurrency: int = 8,
        progress=True,
    ) -> Predictions:
        """Classify texts with the model (async); failures come back as rows, not exceptions.

        Items not in the cache are sent to the model, which costs money; cached answers are free.
        A failed item (the model gave an invalid answer, or its service returned an error such as
        a rate limit or timeout) is returned as a row with an `error` message and is never cached.

        Args:
            items: Strings (their id is their position), dicts with `id` and `text`, or an object
                with `.rows`, such as `Candidates`.
            out: A JSONL file to save the answers to, or None. Each finished item is appended
                as `{id, text, labels, reasoning, run, ...other input fields}`, one line at a
                time; failed items are not written. Running again with the same file skips ids
                already there under this classifier's `digest`. Rows written under a different
                prompt or taxonomy are classified again and the old row stays in the file, so
                when reading the file take the last row of each id.
            max_cost: A dollar limit, or None for none. The run is refused before it starts if
                the estimate is over it or the model's price is unknown, and stops part-way if
                the spend crosses it; rows finished by then are kept.
            concurrency: How many items to send to the model at once.
            progress: True prints one updating line in a terminal or notebook, False prints
                nothing, and a function is called as `progress(done, total, info)` where `info`
                holds `live`, `cached`, `errors` and `cost`.

        Returns:
            Predictions: One row per item, in the order given.

        Raises:
            CostLimit: `max_cost` was given and the run would be, or was, over it, or the price
                is unknown so the limit cannot be honoured.
            ModelAPIError: The service refused the key (HTTP 401/403), or failed five times in a
                row; rows finished before that are kept.
        """
        run = self.digest
        rows = _rows(items)
        path = Path(out) if out else None
        done_rows: dict = {}
        if path is not None and path.exists():
            for line in path.read_text().splitlines():
                if not line.strip():
                    continue
                row = json.loads(line)
                if row.get("run") == run and row.get("labels") is not None:
                    done_rows[row["id"]] = row
        results: list[dict | None] = [done_rows.get(r["id"]) for r in rows]
        todo = [i for i, row in enumerate(results) if row is None]

        if max_cost is not None:
            est = self._estimate([rows[i]["text"] for i in todo])
            if est.live and est.dollars is None:
                raise CostLimit(
                    f"cannot honour max_cost={max_cost}: the price of "
                    f"{_model_name(self.model)} is unknown (no priced call recorded)"
                )
            if est.dollars is not None and est.dollars > max_cost:
                raise CostLimit(
                    f"estimated cost ${est.dollars:.4f} is over max_cost={max_cost}"
                )

        report = _reporter(progress)
        counts = {"live": 0, "cached": 0, "errors": 0, "cost": 0.0}
        semaphore = asyncio.Semaphore(concurrency)

        async def one(i: int) -> tuple[int, Prediction]:
            async with semaphore:
                return i, await self._predict(rows[i]["text"])

        tasks = [asyncio.create_task(one(i)) for i in todo]
        start = time.monotonic()
        last_live = start
        finished = len(rows) - len(todo)
        api_errors = 0  # model API errors in a row
        try:
            for waiting in asyncio.as_completed(tasks):
                i, prediction = await waiting
                item = rows[i]
                row = {
                    "id": item["id"],
                    "text": item["text"],
                    "labels": prediction.labels,
                    **(
                        {"error": prediction.error}
                        if prediction.error
                        else {"reasoning": prediction.reasoning}
                    ),
                    "run": run,
                    **{k: v for k, v in item.items() if k not in ("id", "text")},
                }
                results[i] = row
                finished += 1
                if prediction.cached:
                    counts["cached"] += 1
                else:
                    counts["live"] += 1
                    last_live = time.monotonic()
                    if prediction.dollars is None or counts["cost"] is None:
                        counts["cost"] = None
                    else:
                        counts["cost"] += prediction.dollars
                if prediction.api_error:
                    api_errors += 1
                elif not prediction.cached:
                    api_errors = 0
                if prediction.error:
                    counts["errors"] += 1
                elif path is not None:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    with path.open("a") as f:
                        f.write(json.dumps(row) + "\n")
                        f.flush()
                if report:
                    report(finished, len(rows), dict(counts))
                if api_errors >= MAX_API_ERRORS_IN_A_ROW:
                    raise ModelAPIError(
                        _model_name(self.model),
                        f"stopped: {api_errors} model API errors in a row; last: "
                        f"{prediction.error}",
                    )
                if max_cost is not None and not prediction.cached:
                    if counts["cost"] is None:
                        raise CostLimit(
                            "stopped: a live call's price is unknown, so max_cost "
                            f"{max_cost} cannot be honoured"
                        )
                    if counts["cost"] > max_cost:
                        raise CostLimit(
                            f"stopped: spent ${counts['cost']:.4f}, over max_cost={max_cost}"
                        )
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            if counts["live"]:
                record_timing(self.cache, "classify", counts["live"], last_live - start)
        return Predictions(
            [r for r in results if r is not None],
            live=counts["live"],
            cached=counts["cached"],
            resumed=len(rows) - len(todo),
            cost=counts["cost"],
        )
