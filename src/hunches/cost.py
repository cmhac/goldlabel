import hashlib
import json
import os
import threading
from decimal import Decimal
from pathlib import Path
from typing import Literal

from pydantic_ai.embeddings import EmbeddingResult
from pydantic_ai.messages import ModelMessage, ModelResponse
from pydantic_ai.usage import RequestUsage, RunUsage

from hunches.settings import resolve

# `cache` below is a directory (str or Path), None for the default `<settings.root>/cache`,
# or False for no cache: nothing is read or written and the ledger stays empty.
_LEDGER_LOCK = (
    threading.Lock()
)  # read-modify-write of cost.json; threads only, not processes


def cache_dir(cache) -> Path | Literal[False]:
    if cache is False:
        return False
    return Path(cache) if cache is not None else resolve(None, "cache")


def cache_key(model: str, prompt: str, text: str) -> str:
    # JSON-encoding the tuple keeps ("ab", "c") and ("a", "bc") distinct
    return hashlib.sha256(json.dumps([model, prompt, text]).encode()).hexdigest()


def cache_get(cache, key: str) -> dict | None:
    """Return {"output": ..., "usage": {...}} or None. A hit must not be recorded as cost or timing."""
    directory = cache_dir(cache)
    if directory is False:
        return None
    path = directory / f"{key}.json"
    return json.loads(path.read_text()) if path.exists() else None


def cache_put(cache, key: str, output, usage: RunUsage | RequestUsage) -> None:
    """Store a JSON-serialisable output plus its original usage (for estimates)."""
    directory = cache_dir(cache)
    if directory is False:
        return
    directory.mkdir(parents=True, exist_ok=True)
    entry = {
        "output": output,
        "usage": {
            "input_tokens": usage.input_tokens,
            "output_tokens": usage.output_tokens,
        },
    }
    (directory / f"{key}.json").write_text(json.dumps(entry))


def messages_dollars(messages: list[ModelMessage]) -> float | None:
    """Dollars for the model responses in `messages` (use `result.new_messages()`); None if any price is unknown."""
    total = Decimal(0)
    for message in messages:
        if isinstance(message, ModelResponse):
            try:
                total += message.cost().total_price
            except LookupError:
                return None
    return float(total)


def embedding_dollars(result: EmbeddingResult) -> float | None:
    try:
        return float(result.cost().total_price)
    except LookupError:
        return None


def _read(cache) -> dict:
    directory = cache_dir(cache)
    path = directory / "cost.json" if directory is not False else None
    if path is None or not path.exists():
        return {"models": {}, "timings": []}
    return json.loads(path.read_text())


def _write(directory: Path, data: dict) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    temp = directory / f"cost.json.{os.getpid()}.{threading.get_ident()}.tmp"
    temp.write_text(json.dumps(data, indent=2) + "\n")
    os.replace(temp, directory / "cost.json")


def record(
    cache, model: str, usage: RunUsage | RequestUsage, dollars: float | None
) -> None:
    """Add one live call. `dollars` None means the price is unknown; it is stored as null, never 0."""
    directory = cache_dir(cache)
    if directory is False:
        return
    with _LEDGER_LOCK:
        data = _read(directory)
        entry = data["models"].setdefault(
            model, {"input_tokens": 0, "output_tokens": 0, "calls": 0, "dollars": 0.0}
        )
        entry["input_tokens"] += usage.input_tokens
        entry["output_tokens"] += usage.output_tokens
        entry["calls"] += 1
        # once any call of a model is unknown, the model's dollars stay unknown
        if dollars is None or entry["dollars"] is None:
            entry["dollars"] = None
        else:
            entry["dollars"] += dollars
        _write(directory, data)


def total(cache) -> tuple[float, bool]:
    """(dollars over models with a known price, unknown flag). If the flag is set the dollars are only a lower bound; show "?"."""
    models = _read(cache)["models"].values()
    known = sum(m["dollars"] for m in models if m["dollars"] is not None)
    return known, any(m["dollars"] is None for m in models)


def breakdown(cache) -> dict[str, dict]:
    return _read(cache)["models"]


def per_call_dollars(cache, model: str) -> tuple[float | None, bool]:
    """(average dollars per recorded live call, whether any call is recorded).

    None with True: the price is unknown; with False: there is no sample to price from.
    """
    entry = breakdown(cache).get(model)
    if not entry or not entry["calls"]:
        return None, False
    if entry["dollars"] is None:
        return None, True
    return entry["dollars"] / entry["calls"], True


def record_timing(cache, label: str, n_items: int, seconds: float) -> None:
    """Live (non-cached) work only; used for items/sec estimates."""
    directory = cache_dir(cache)
    if directory is False:
        return
    with _LEDGER_LOCK:
        data = _read(directory)
        data["timings"].append({"label": label, "n_items": n_items, "seconds": seconds})
        _write(directory, data)


def items_per_second(cache, label: str | None = None) -> float | None:
    rows = [t for t in _read(cache)["timings"] if label is None or t["label"] == label]
    seconds = sum(t["seconds"] for t in rows)
    return sum(t["n_items"] for t in rows) / seconds if seconds > 0 else None


class Cost:
    """The running spend from a ledger. `total` is None (shown as `?`) when any recorded price is unknown."""

    def __init__(self, by_model: dict[str, dict]):
        self.by_model = by_model
        self.unknown = any(m["dollars"] is None for m in by_model.values())
        self.total = (
            None if self.unknown else sum(m["dollars"] for m in by_model.values())
        )

    def __repr__(self) -> str:
        lines = [f"cost {_dollars(self.total)}"]
        for name, m in self.by_model.items():
            lines.append(
                f"  {name}: {_dollars(m['dollars'])}, {m['calls']} calls, "
                f"{m['input_tokens']} in / {m['output_tokens']} out"
            )
        if self.unknown:
            unknown = [n for n, m in self.by_model.items() if m["dollars"] is None]
            known = sum(
                m["dollars"] for m in self.by_model.values() if m["dollars"] is not None
            )
            lines.append(
                f"WARNING: the price of {', '.join(unknown)} is unknown, so the total "
                f"is unknown (at least ${known:.4f} is known)"
            )
        return "\n".join(lines)


def _dollars(value: float | None) -> str:
    return "?" if value is None else f"${value:.4f}"


def cost(cache=None) -> Cost:
    """The total and per-model breakdown recorded in the cache directory's ledger."""
    return Cost(breakdown(cache))
