"""Shared helpers for the examples under `e2e/`: data loaders, checks, the result line, Podman.

Plain functions only. Not an example: an example never imports another example, only this file.
"""

import atexit
import json
import os
import shutil
import signal
import subprocess
import sys
import time
import traceback
from contextlib import contextmanager
from pathlib import Path

from pydantic_ai import Embedder
from pydantic_ai.embeddings import EmbeddingResult, TestEmbeddingModel
from pydantic_ai.usage import RequestUsage

import hunches as hn

COMMON = Path(__file__).parent
CACHE = COMMON.parent / ".cache"  # git-ignored, shared by every example
GOLD = COMMON / "gold.jsonl"
MODEL = "anthropic:claude-haiku-5-5"
MAX_COST = 0.50  # dollars, per classification call; a cold run needs about a cent
EMBEDDING_MODEL = "hand-built-2d"
KEY = "ANTHROPIC_API_KEY"
READY_SECONDS = 60  # how long a container gets to answer


class Failed(Exception):
    """A check failed, or something an example needs is missing."""


def say(*parts) -> None:
    print(*parts, flush=True)


def corpus_rows() -> list[dict]:
    lines = (COMMON / "corpus.jsonl").read_text().splitlines()
    return [json.loads(line) for line in lines]


def expected() -> dict:
    return json.loads((COMMON / "expected.json").read_text())


def seeds() -> dict[str, list[float]]:
    return json.loads((COMMON / "seeds.json").read_text())


def taxonomy() -> hn.Taxonomy:
    return hn.Taxonomy.read(COMMON / "taxonomy.yaml")


def prompt() -> str:
    return (COMMON / "prompt.md").read_text().strip()


def hits(candidates) -> list[list]:
    """Keyword candidates as [id, terms_matched, matches], the shape of expected.json."""
    return [[r["id"], r["terms_matched"], r["matches"]] for r in candidates.rows]


def found(candidates) -> list[list]:
    """Seed candidates as [id, similarity to 4 places, best seed], the shape of expected.json."""
    return [
        [r["id"], round(r["max_similarity"], 4), r["best_seed"]]
        for r in candidates.rows
    ]


def check(name: str, got, want) -> None:
    """Stop with the check's name and both values when they differ."""
    if got != want:
        raise Failed(f"{name}: expected {want!r}, got {got!r}")
    say(f"ok  {name}")


class StandIn(Embedder):
    """The embedder for `seeds.json`: a seed phrase maps to its hand-built vector. No key, no model.

    With your own corpus, drop this and pass `embedder="openai:text-embedding-3-small"` (or the model
    your corpus was embedded with) to `hn.get_candidates`.
    """

    def __init__(self):
        super().__init__(TestEmbeddingModel(EMBEDDING_MODEL))
        self.vectors = seeds()

    async def embed_query(self, query, *, settings=None):
        return EmbeddingResult(
            [self.vectors[query]],
            inputs=[query],
            input_type="query",
            model_name=EMBEDDING_MODEL,
            provider_name="test",
            usage=RequestUsage(input_tokens=1),
        )


def run(main) -> None:
    """Run an example. `main()` returns None (pass) or a reason string (skipped); a failed check
    raises `Failed`. The last line printed is always the `RESULT:` line; exit 1 only on failure."""
    start = time.monotonic()
    try:
        skipped = main()
    except Failed as e:
        say(f"RESULT: fail - {e}")
        sys.exit(1)
    except Exception as e:  # noqa: BLE001 - any other error is a failed run, reported the same way
        traceback.print_exc()
        say(f"RESULT: fail - {type(e).__name__}: {e}")
        sys.exit(1)
    say(f"elapsed {time.monotonic() - start:.1f}s")
    say(f"RESULT: skipped - {skipped}" if skipped else "RESULT: pass")


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _podman(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["podman", *args], capture_output=True, text=True, check=False
    )


@contextmanager
def container(example: str, image: str, port: int, env: dict | None = None, ready=None):
    """A throwaway container for one run; yields the host port on 127.0.0.1.

    Stale containers of this example (label `hunches-e2e=<example>`, left by a killed run) are
    removed first. The container is removed on success, failure, Ctrl-C and SIGTERM. `ready(port)`
    returns when the service answers and raises or returns False while it does not.
    """
    if shutil.which("podman") is None:
        raise Failed("podman is required: https://podman.io/docs/installation")
    label = f"hunches-e2e={example}"
    for old in _podman(
        "ps", "-a", "--filter", f"label={label}", "--format", "{{.Names}}"
    ).stdout.split():
        if _alive(int(old.rsplit("-", 1)[1])):
            raise Failed(
                f"another run of {example} is in progress (container {old}); wait for it"
            )
        _podman("rm", "-f", old)  # left by a run that was killed
    name = f"hunches-e2e-{example}-{os.getpid()}"
    command = ["run", "-d", "--rm", "--name", name, "--label", label]
    command += ["-p", f"127.0.0.1::{port}"]
    for key, value in (env or {}).items():
        command += ["-e", f"{key}={value}"]
    started = _podman(*command, image)
    if started.returncode:
        raise Failed(f"podman could not start {image}: {started.stderr.strip()}")

    def remove():
        _podman("rm", "-f", name)

    atexit.register(remove)
    previous = signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))
    try:
        mapped = _podman("port", name, f"{port}/tcp").stdout.split()
        if not mapped:
            raise Failed(f"{image} published no port {port}")
        host_port = int(mapped[0].rsplit(":", 1)[1])
        deadline = time.monotonic() + READY_SECONDS
        while True:
            try:
                answered = ready is None or ready(host_port) is not False
            except Exception:  # noqa: BLE001 - not ready yet
                answered = False
            if answered:
                break
            if time.monotonic() > deadline:
                logs = _podman("logs", "--tail", "20", name)
                raise Failed(
                    f"{image} was not ready after {READY_SECONDS}s; last log lines:\n{logs.stdout}{logs.stderr}"
                )
            time.sleep(0.5)
        yield host_port
    finally:
        remove()
        atexit.unregister(remove)
        signal.signal(signal.SIGTERM, previous)


def classify_and_evaluate(candidates, tmp: Path, cache=CACHE, gold=GOLD) -> str | None:
    """Classify `candidates`, then evaluate the dev split of the committed gold file.

    Returns None, or the reason the model step was skipped. The estimate is printed before the
    first live call. A price is only known after one priced call, so with no price recorded one
    candidate is classified first (about a hundredth of a cent) and the rest run under MAX_COST.
    """
    clf = hn.Classifier(MODEL, taxonomy(), prompt(), cache=cache)
    estimate = clf.estimate(candidates)
    say(estimate)
    if estimate.live and not os.environ.get(KEY):
        return f"no {KEY} in the environment and {estimate.live} items are not cached"
    if estimate.live and estimate.dollars is None:
        say("no price recorded yet: classifying one item to learn it")
        clf.classify(candidates.rows[:1], progress=False)
        say(clf.estimate(candidates))
    predictions = clf.classify(candidates, max_cost=MAX_COST, progress=False)
    say(predictions)
    check("model errors", len(predictions.errors), 0)
    if not gold.exists():
        return (
            "e2e/common/gold.jsonl is not made yet: Chris labels it, see e2e/README.md"
        )
    copy = tmp / "gold.jsonl"
    shutil.copyfile(gold, copy)
    say((COMMON / "GOLD.md").read_text())
    # shortcut: evaluate has no cost cap; safe because every caller classifies the whole corpus first,
    # which caches every gold row, upgrade when an example classifies only a subset
    evaluation = hn.evaluate(
        clf, hn.Gold(copy).dev, target=expected()["score_floor"], log=False
    )
    say(evaluation)
    score = evaluation.score()
    check("score is at least the floor", score >= expected()["score_floor"], True)
    say(f"score={score:.4f}")
    return None
