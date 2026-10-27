import asyncio
import csv
import hashlib
import heapq
import io
import json
import random
import re
from collections import Counter
from collections.abc import Collection, Sequence
from contextlib import closing
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from itertools import islice
from pathlib import Path

from pydantic_ai import Embedder

from hunches import _frame, _html
from hunches._sync import run
from hunches.cost import cache_get, cache_key, cache_put, embedding_dollars, record
from hunches.search import (
    PgCorpus,
    S3Corpus,
    Table,
    pg_items,
    search_pg_exact,
    search_table,
    search_vectors,
    table_rows,
)
from hunches.settings import resolve

FLOOR = 0.60
# Lower edges of the similarity bands; the last band (0.75+) is open-ended.
BANDS = [0.60, 0.625, 0.65, 0.675, 0.70, 0.725, 0.75]


def read_seeds(path) -> list[str]:
    """Seed phrases from a seeds.csv: first column, blank lines and an optional `seed` header skipped."""
    rows = csv.reader(io.StringIO(Path(path).read_text()))
    seeds = [r[0].strip() for r in rows if r and r[0].strip()]
    return seeds[1:] if seeds and seeds[0].lower() == "seed" else seeds


def seeds_digest(seeds: list[str]) -> str:
    return hashlib.sha256(json.dumps(seeds).encode()).hexdigest()


def band_of(similarity: float) -> int:
    """Index into BANDS of the band containing `similarity` (lower-inclusive); -1 below the floor."""
    return max((i for i, edge in enumerate(BANDS) if similarity >= edge), default=-1)


def _band_name(i: int) -> str:
    return (
        f"{BANDS[i]:.3f}-{BANDS[i + 1]:.3f}"
        if i + 1 < len(BANDS)
        else f"{BANDS[i]:.3f}+"
    )


CAPPED_WARNING = "results were capped, so some items above the floor may be missing"


def band_counts(candidates: list[dict]) -> list[int]:
    counts = [0] * len(BANDS)
    for c in candidates:
        if (i := band_of(c["max_similarity"])) >= 0:
            counts[i] += 1
    return counts


def top_seeds(rows: list[dict], threshold: float, n: int = 10) -> list[tuple[str, int]]:
    """Seeds ranked by items won among rows at or above `threshold` (best_seed is each item's argmax)."""
    won = Counter(r["best_seed"] for r in rows if r["max_similarity"] >= threshold)
    return won.most_common(n)


@dataclass(frozen=True)
class Candidates:
    """Candidate items. `source` says where they came from: "seeds" (rows `{id, text, max_similarity,
    best_seed}`, best first), "keywords" (`{id, text, terms_matched, matches}`, best first) or
    "all" (`{id, text}`, corpus order). Floor, digest and model are None outside seeds."""

    rows: list[dict]
    capped: bool = False  # a backend cap may have hidden hits above the floor
    floor: float | None = FLOOR
    seeds_digest: str | None = None
    embedding_model: str | None = None
    source: str = "seeds"

    def _need_seeds(self, name: str) -> None:
        if self.source != "seeds":
            raise ValueError(
                f"{name} needs similarity scores, but this list was built from "
                f"{self.source}, not from seeds"
            )

    def above(self, t: float) -> "Candidates":
        self._need_seeds("above")
        return replace(self, rows=[r for r in self.rows if r["max_similarity"] >= t])

    def bands(self) -> list[int]:
        self._need_seeds("bands")
        return band_counts(self.rows)

    def sample(self, n: int, seed=None, exclude: Collection[str] = ()) -> "Candidates":
        """`n` rows without replacement (all that remain if fewer), deterministic for a seed."""
        pool = [r for r in self.rows if r["id"] not in set(exclude)]
        return replace(self, rows=random.Random(seed).sample(pool, min(n, len(pool))))

    def top_seeds(self, threshold: float, n: int = 10) -> list[tuple[str, int]]:
        self._need_seeds("top_seeds")
        return top_seeds(self.rows, threshold, n)

    @classmethod
    def read(cls, path) -> "Candidates":
        path = Path(path)
        rows = [json.loads(x) for x in path.read_text().splitlines() if x.strip()]
        meta_path = path.with_suffix(".meta.json")
        meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
        return cls(
            rows,
            capped=meta.get("capped", False),
            floor=meta.get("floor", FLOOR),
            seeds_digest=meta.get("seeds_digest"),
            embedding_model=meta.get("embedding_model"),
            source=meta.get("source", "seeds"),
        )

    def write(self, path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(json.dumps(r) + "\n" for r in self.rows))
        meta = {
            "seeds_digest": self.seeds_digest,
            "written_at": datetime.now(UTC).isoformat(),
            "floor": self.floor,
            "embedding_model": self.embedding_model,
            "capped": self.capped,
            "source": self.source,
        }
        path.with_suffix(".meta.json").write_text(json.dumps(meta))

    def to_polars(self):
        return _frame.to_polars(self.rows)

    def to_pandas(self):
        return _frame.to_pandas(self.rows)

    def _headline(self) -> str:
        if self.source == "keywords":
            return f"{len(self.rows)} candidates (from keywords)"
        if self.source == "all":
            return f"{len(self.rows)} candidates (whole corpus)"
        return f"{len(self.rows)} candidates (floor {self.floor:.2f})"

    def _repr_html_(self) -> str:
        if self.source == "keywords":
            return _html.line(self._headline()) + _html.table(
                ["id", "text", "terms matched", "matches"],
                [
                    (r["id"], r["text"], r["terms_matched"], r["matches"])
                    for r in self.rows
                ],
            )
        if self.source == "all":
            return _html.line(self._headline()) + _html.table(
                ["id", "text"], [(r["id"], r["text"]) for r in self.rows]
            )
        rows = [
            (r["id"], r["text"], f"{r['max_similarity']:.3f}", r["best_seed"])
            for r in self.rows
        ]
        out = [
            _html.line(self._headline()),
            _html.bars([(_band_name(i), n) for i, n in enumerate(self.bands())]),
        ]
        if self.capped:
            out.append(_html.warning(CAPPED_WARNING))
        out.append(_html.table(["id", "text", "similarity", "best seed"], rows))
        return "".join(out)

    def __repr__(self) -> str:
        if self.source != "seeds":
            return self._headline()
        lines = [self._headline()]
        for i, count in enumerate(self.bands()):
            lines.append(f"  {_band_name(i)}  {count}")
        if self.capped:
            lines.append(f"WARNING: {CAPPED_WARNING}")
        return "\n".join(lines)


def _model_name(embedder: Embedder) -> str:
    model = embedder.model
    return model if isinstance(model, str) else model.model_name


async def embed_seeds(
    seeds: list[str], embedder: Embedder, model: str, cache=None
) -> list[list[float]]:
    """Query embeddings, one per seed. Cache hits cost nothing; live calls are recorded."""
    vectors = []
    for seed in seeds:
        key = cache_key(model, "embed_query", seed)
        hit = cache_get(cache, key)
        if hit:
            vectors.append(hit["output"])
            continue
        result = await embedder.embed_query(seed)
        vector = [float(x) for x in result.embeddings[0]]
        cache_put(cache, key, vector, result.usage)
        record(cache, model, result.usage, embedding_dollars(result))
        vectors.append(vector)
    return vectors


def _items(corpus, guard: bool = False, limit: int | None = None):
    """(id, text) of every item in the corpus's own order, as a generator to close."""
    if isinstance(corpus, Table):
        return ((r["id"], r["text"]) for r in table_rows(corpus))
    if isinstance(corpus, PgCorpus):
        return pg_items(corpus, guard, limit)
    raise NotImplementedError("whole-corpus reads arrive with the Postgres/S3 reader")


def _compile(keywords, regex: bool) -> list[re.Pattern]:
    patterns = []
    for term in keywords:
        if isinstance(term, re.Pattern):
            pattern = term
        elif isinstance(term, str):
            if not term.strip():
                raise ValueError("keywords has a blank term")
            try:
                pattern = (
                    re.compile(term)
                    if regex
                    else re.compile(re.escape(term), re.IGNORECASE)
                )
            except re.error as e:
                raise re.error(f"invalid regular expression {term!r}: {e}") from None
        else:
            raise TypeError(
                f"keywords must be strings or compiled patterns, not {type(term).__name__}"
            )
        # shortcut: only patterns matching the empty string are refused, zero-width ones like \b
        # still match every word, tell the user in the docs
        if pattern.match(""):
            raise ValueError(
                f"keyword {pattern.pattern!r} matches the empty string, so it would match every item"
            )
        patterns.append(pattern)
    return patterns


def _rank(items, patterns: list[re.Pattern], limit: int | None) -> list[dict]:
    """Items matching any pattern, best first: distinct patterns matched, then total matches, then
    corpus order. With a limit only that many are held at a time."""

    def hits():
        for index, (id, text) in enumerate(items):
            counts = [sum(1 for _ in p.finditer(text)) for p in patterns]
            if terms := sum(c > 0 for c in counts):
                yield -terms, -sum(counts), index, id, text

    ranked = heapq.nsmallest(limit, hits()) if limit else sorted(hits())
    return [
        {"id": id, "text": text, "terms_matched": -t, "matches": -m}
        for t, m, _, id, text in ranked
    ]


async def aget_candidates(
    corpus: Table | S3Corpus | PgCorpus,
    *,
    seeds: Sequence[str] | None = None,
    embedder: str | Embedder | None = None,
    floor: float | None = None,
    keywords: Sequence[str | re.Pattern] | None = None,
    regex: bool = False,
    limit: int | None = None,
    out=None,
    cache=None,
) -> Candidates:
    """The corpus's candidate items, filtered by at most one of `seeds` or `keywords`.

    No filter: every item in the corpus's order. `seeds`: the items whose maximum similarity to
    any seed is at least `floor` (None: 0.60), best first; ties go to the earlier seed.
    `keywords`: the items containing any term, best first (distinct terms matched, then total
    matches, then corpus order). A term is a plain string (literal, case-insensitive) or a
    compiled `re.Pattern` that keeps its own flags; `regex=True` makes strings patterns, as written.

    `embedder` (a pydantic-ai model string or an `Embedder`), `floor` and `cache` (a directory,
    None for `<settings.root>/cache`, False for none) belong to `seeds`. `limit` keeps the first N
    items, or the best N. `out`: a path writes the list there (+ `.meta.json`), False writes
    nothing, None writes `<settings.root>/candidates.jsonl` for seeds only.
    """
    if isinstance(seeds, str):
        raise TypeError(
            "seeds must be a list of strings; use read_seeds(path) for a CSV"
        )
    if isinstance(keywords, str):
        raise TypeError("keywords must be a list; use keywords=['term'] for one term")
    if seeds is not None and keywords is not None:
        raise ValueError("give seeds or keywords, not both: one filter per call")
    if keywords is not None and not keywords:
        raise ValueError("keywords is empty; give at least one term")
    if keywords is None and regex:
        raise ValueError("regex is only used with keywords")
    if seeds is None:
        for name, value in (("embedder", embedder), ("floor", floor), ("cache", cache)):
            if value is not None:
                raise ValueError(f"{name} is only used with seeds")
    else:
        seeds = list(seeds)
        if not seeds:
            raise ValueError("seeds is empty; give at least one seed phrase")
    if limit is not None and limit < 1:
        raise ValueError("limit must be 1 or more")
    if seeds is None:
        patterns = _compile(keywords, regex) if keywords is not None else None

        def read():
            with closing(_items(corpus, patterns is None, limit)) as items:
                if patterns is None:
                    return [{"id": i, "text": t} for i, t in islice(items, limit)]
                return _rank(items, patterns, limit)

        result = Candidates(
            await asyncio.to_thread(read),
            floor=None,
            source="all" if patterns is None else "keywords",
        )
        if out is not None and out is not False:
            result.write(resolve(out, "candidates.jsonl"))
        return result
    if embedder is None:
        raise ValueError("embedder is required with seeds")
    floor = FLOOR if floor is None else floor
    if isinstance(embedder, str):
        model, embedder = embedder, Embedder(embedder)
    else:
        model = _model_name(embedder)
    vectors = await embed_seeds(seeds, embedder, model, cache)
    if isinstance(corpus, Table):
        per_seed, capped = await asyncio.to_thread(
            search_table, corpus, vectors, floor, model
        )
    elif isinstance(corpus, PgCorpus) and corpus.search == "exact":
        per_seed, capped = await asyncio.to_thread(
            search_pg_exact, corpus, vectors, floor
        )
    else:
        per_seed, capped = [], False
        for vector in vectors:
            hits, seed_capped = search_vectors(
                corpus, vector, floor, embedding_model=model
            )
            capped = capped or seed_capped
            per_seed.append(hits)
    best: dict[str, dict] = {}
    for seed, hits in zip(seeds, per_seed):
        for id, text, sim in hits:
            if id not in best or sim > best[id]["max_similarity"]:
                best[id] = {
                    "id": id,
                    "text": text,
                    "max_similarity": sim,
                    "best_seed": seed,
                }
    rows = sorted(best.values(), key=lambda r: (-r["max_similarity"], r["id"]))[:limit]
    result = Candidates(rows, capped, floor, seeds_digest(seeds), model)
    if out is not False:
        result.write(resolve(out, "candidates.jsonl"))
    return result


def get_candidates(
    corpus: Table | S3Corpus | PgCorpus,
    *,
    seeds: Sequence[str] | None = None,
    embedder: str | Embedder | None = None,
    floor: float | None = None,
    keywords: Sequence[str | re.Pattern] | None = None,
    regex: bool = False,
    limit: int | None = None,
    out=None,
    cache=None,
) -> Candidates:
    """`aget_candidates` for scripts and notebooks; also works inside a running event loop."""
    return run(
        aget_candidates(
            corpus,
            seeds=seeds,
            embedder=embedder,
            floor=floor,
            keywords=keywords,
            regex=regex,
            limit=limit,
            out=out,
            cache=cache,
        )
    )
