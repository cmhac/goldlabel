import asyncio
import hashlib
import json
import sys
import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal

from pydantic import BaseModel
from pydantic_ai import Agent, ModelRetry
from pydantic_ai.exceptions import (
    ModelAPIError,
    ModelHTTPError,
    UnexpectedModelBehavior,
)
from pydantic_ai.models import Model

from hunches import _sync
from hunches.cost import (
    cache_get,
    cache_key,
    cache_put,
    items_per_second,
    messages_dollars,
    per_call_dollars,
    record,
    record_timing,
)
from hunches.taxonomy import Taxonomy, all_labels, validate_labels


@dataclass
class Prediction:
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
    """prompt.md plus the label list and mode rule. This whole string is what the cache key hashes."""
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
    """Normalise `items`: strings (id = position), dicts with `id` and `text`, or an object with `.rows`."""
    if hasattr(items, "rows"):
        items = items.rows
    return [
        {"id": i, "text": item} if isinstance(item, str) else dict(item)
        for i, item in enumerate(items)
    ]


@dataclass(frozen=True)
class Estimate:
    n: int
    cached: int
    live: int
    dollars: float | None  # None: the price is unknown (never 0)
    seconds: float | None  # None: no timing recorded yet

    def __repr__(self) -> str:
        cost = "?" if self.dollars is None else f"~${self.dollars:.4f}"
        time = "?" if self.seconds is None else f"~{self.seconds:.0f}s"
        lines = [
            f"Estimate: {self.n} items, {self.cached} cached, {self.live} live calls",
            f"cost {cost}, time {time}",
        ]
        if self.dollars is None:
            lines.append(
                "WARNING: the price is unknown (no priced call recorded for this model), "
                "so the cost is unknown, not zero"
            )
        return "\n".join(lines)


@dataclass
class Predictions:
    """`rows` are in input order. `labels` lists each row's labels (None where the item failed)."""

    rows: list[dict]
    live: int = 0  # calls made now
    cached: int = 0  # answered from the cache
    resumed: int = 0  # already in `out` under this run, not asked again
    cost: float | None = (
        0.0  # dollars spent by the live calls; None if any price is unknown
    )

    @property
    def errors(self) -> list[dict]:
        return [r for r in self.rows if r.get("error")]

    @property
    def labels(self) -> list[list[str] | None]:
        return [r["labels"] for r in self.rows]

    def __repr__(self) -> str:
        counts = (
            f"{len(self.rows)} items, {self.live} live, {self.cached} cached, "
            f"{self.resumed} resumed from out, {len(self.errors)} errors"
        )
        lines = [f"Predictions: {counts}", f"cost {_dollars(self.cost)}"]
        if self.cost is None:
            lines.append(
                "WARNING: the price is unknown, so the cost is unknown, not zero"
            )
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
    """`cache`: a directory, None for `<settings.root>/cache`, or False for none."""

    model: str | Model
    taxonomy: Taxonomy
    prompt: str
    cache: object = None

    def with_prompt(self, text: str) -> "Classifier":
        return replace(self, prompt=text)

    def with_taxonomy(self, taxonomy: Taxonomy) -> "Classifier":
        return replace(self, taxonomy=taxonomy)

    @property
    def digest(self) -> str:
        """What the cache key hashes minus the item text: equal digests mean cache hits."""
        data = [_model_name(self.model), system_prompt(self.prompt, self.taxonomy)]
        return hashlib.sha256(json.dumps(data).encode()).hexdigest()

    def _key(self, text: str) -> str:
        system = system_prompt(self.prompt, self.taxonomy)
        return cache_key(_model_name(self.model), system, text)

    def _hit(self, text: str) -> dict | None:
        """The cache entry's output dict; an old-shape entry (a bare label list) is a miss."""
        hit = cache_get(self.cache, self._key(text))
        return (
            hit["output"]
            if hit is not None and isinstance(hit["output"], dict)
            else None
        )

    def estimate(self, items) -> Estimate:
        """Count cached vs live calls and price the live ones from recorded usage. Calls no model."""
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
        """Classify one text. Cache hits cost nothing; failures are not cached."""
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

    def classify(self, items, **kwargs) -> Predictions:
        """Same as `aclassify`, for scripts and notebooks (also inside a running event loop)."""
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
        """Classify `items`; failures are returned as rows with `error`, never raised or cached.

        `items`: strings (id = position), dicts with `id` and `text`, or an object with `.rows`.
        `out`: a JSONL path. Each finished item appends `{id, text, labels, reasoning, run, ...other
        input fields}` (flushed per line); failed items are not written. Ids already there with a
        successful row under this classifier's `digest` are skipped. Rows under another `run` are
        classified again and the old row stays in the file, so readers must take the last row per id.
        `max_cost`: raise `CostLimit` before starting when the estimate is over it or the price is
        unknown; stop with `CostLimit` mid-run when live spend crosses it (finished rows are kept).
        A model API error (HTTP 429/5xx, timeout, connection error) is an error row too, but 401/403
        raise at once and `MAX_API_ERRORS_IN_A_ROW` of them in a row raise `ModelAPIError`; finished
        rows are kept. `progress`: True prints one updating line on a terminal or in a notebook, False is silent,
        a callable gets `(done, total, info)` with `info` = live, cached, errors, cost.
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
