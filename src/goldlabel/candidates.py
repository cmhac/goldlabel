"""Candidate items for classification: from seed phrases (by similarity), keywords, or the whole corpus."""

import asyncio
import csv
import hashlib
import heapq
import io
import json
import random
import re
import warnings
from collections import Counter
from collections.abc import Collection, Sequence
from contextlib import closing
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from itertools import islice
from pathlib import Path

from pydantic_ai import Embedder

from goldlabel import _frame, _html
from goldlabel._sync import run
from goldlabel.cost import cache_get, cache_key, cache_put, embedding_dollars, record
from goldlabel.search import (
    PgCorpus,
    S3Corpus,
    Table,
    check_table_for_seeds,
    pg_items,
    s3_items,
    search_pg_exact,
    search_table,
    search_vectors,
    table_rows,
)
from goldlabel.settings import resolve

FLOOR = 0.60
# Lower edges of the similarity bands; the last band (0.75+) is open-ended.
BANDS = [0.60, 0.625, 0.65, 0.675, 0.70, 0.725, 0.75]


def read_seeds(path) -> list[str]:
    """Read seed phrases from a CSV file.

    Takes the first column, skips blank lines and an optional header cell reading `seed`.

    Args:
        path: The CSV file.

    Returns:
        list[str]: The seed phrases, in file order.
    """
    rows = csv.reader(io.StringIO(Path(path).read_text()))
    seeds = [r[0].strip() for r in rows if r and r[0].strip()]
    return seeds[1:] if seeds and seeds[0].lower() == "seed" else seeds


def seeds_digest(seeds: list[str]) -> str:
    """Fingerprint a list of seed phrases, to tell whether a saved candidate list used the same ones.

    Returns:
        str: A hex digest that changes when any seed, or their order, changes.
    """
    return hashlib.sha256(json.dumps(seeds).encode()).hexdigest()


def band_of(similarity: float) -> int:
    """Find which similarity band a score falls in.

    Args:
        similarity: A similarity score.

    Returns:
        int: The position in `BANDS` of the band containing it (a band includes its lower
        edge), or -1 when it is below the lowest band.
    """
    return max((i for i, edge in enumerate(BANDS) if similarity >= edge), default=-1)


def _band_name(i: int) -> str:
    return (
        f"{BANDS[i]:.3f}-{BANDS[i + 1]:.3f}"
        if i + 1 < len(BANDS)
        else f"{BANDS[i]:.3f}+"
    )


CAPPED_WARNING = "results were capped, so some items above the floor may be missing"


def order_by_id(rows, salt: str = "") -> list[dict]:
    """Put rows in an order that depends only on each row's id (and `salt`).

    The order is the same on every machine and does not change when other rows are added or
    removed, which is how a sample is drawn without a random seed.

    Args:
        rows: Dicts with an `id`.
        salt: Text mixed into the order, so different uses get different orders.

    Returns:
        list[dict]: The rows, reordered.
    """
    return sorted(
        rows, key=lambda r: hashlib.sha256(f"{salt}\0{r['id']}".encode()).hexdigest()
    )


def band_counts(candidates: list[dict]) -> list[int]:
    """Count rows in each similarity band.

    Args:
        candidates: Rows with a `max_similarity`.

    Returns:
        list[int]: One count per band of `BANDS`, lowest band first; rows below the floor are not counted.
    """
    counts = [0] * len(BANDS)
    for c in candidates:
        if (i := band_of(c["max_similarity"])) >= 0:
            counts[i] += 1
    return counts


def top_seeds(rows: list[dict], threshold: float, n: int = 10) -> list[tuple[str, int]]:
    """Rank seeds by how many items they are the best match for.

    Args:
        rows: Rows with `max_similarity` and `best_seed`.
        threshold: Only rows with a `max_similarity` at or above this count.
        n: How many seeds to return.

    Returns:
        list[tuple[str, int]]: `(seed, items won)` pairs, most items first.
    """
    won = Counter(r["best_seed"] for r in rows if r["max_similarity"] >= threshold)
    return won.most_common(n)


@dataclass(frozen=True)
class Candidates:
    """The items chosen from a corpus for classification, with how they were chosen.

    You get one from `get_candidates`, or load a saved one with `Candidates.read`.

    Attributes:
        rows: One dict per item. The fields depend on `source` (below).
        capped: True when a limit in the search backend may have hidden items above the floor.
        floor: The lowest similarity kept; None unless the source is "seeds".
        seeds_digest: A fingerprint of the seed phrases used; None unless the source is "seeds".
        embedding_model: The model that embedded the seeds; None unless the source is "seeds".
        source: Where the items came from. "seeds": `{id, text, max_similarity, best_seed}`,
            most similar first. "keywords": `{id, text, terms_matched, matches}`, best first.
            "all": `{id, text}`, in the corpus's own order.
    """

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
        """Keep only the candidates whose similarity is at least `t`.

        This candidate list is unchanged; nothing is written to a file.

        Args:
            t: The lowest `max_similarity` to keep.

        Returns:
            Candidates: A new, shorter list.

        Raises:
            ValueError: The list was not built from seeds, so it has no similarity scores.
        """
        self._need_seeds("above")
        return replace(self, rows=[r for r in self.rows if r["max_similarity"] >= t])

    def bands(self) -> list[int]:
        """Count the candidates in each similarity band.

        The bands start at 0.60 and rise in steps of 0.025; the last one, 0.75+, is open-ended.
        This is what the bar chart shown for a candidate list is drawn from.

        Returns:
            list[int]: One count per band, lowest first.

        Raises:
            ValueError: The list was not built from seeds, so it has no similarity scores.
        """
        self._need_seeds("bands")
        return band_counts(self.rows)

    def sample(self, n: int, seed=None, exclude: Collection[str] = ()) -> "Candidates":
        """Pick `n` random candidates without repeats.

        Gives every remaining candidate if fewer than `n` are left. The same `seed` always gives
        the same pick. This list is unchanged; nothing is written to a file.

        Args:
            n: How many to pick.
            seed: Seeds the random choice; None for a different pick each time.
            exclude: Ids to leave out of the pool.

        Returns:
            Candidates: A new list of the picked rows.
        """
        pool = [r for r in self.rows if r["id"] not in set(exclude)]
        return replace(self, rows=random.Random(seed).sample(pool, min(n, len(pool))))

    def top_seeds(self, threshold: float, n: int = 10) -> list[tuple[str, int]]:
        """Show which seed phrases found the most candidates.

        Each candidate counts for the one seed it is most similar to.

        Args:
            threshold: Only candidates with a `max_similarity` at or above this count.
            n: How many seeds to return.

        Returns:
            list[tuple[str, int]]: `(seed, number of candidates)` pairs, most first.

        Raises:
            ValueError: The list was not built from seeds, so it has no similarity scores.
        """
        self._need_seeds("top_seeds")
        return top_seeds(self.rows, threshold, n)

    @classmethod
    def read(cls, path) -> "Candidates":
        """Load a candidate list saved by `write` (or by `get_candidates`).

        Args:
            path: The `.jsonl` file. Its settings (floor, seed fingerprint and so on) are read
                from the `.meta.json` file beside it when there is one.

        Returns:
            Candidates: The saved rows and settings.
        """
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
        """Save the candidates so they can be reloaded with `Candidates.read`.

        Writes the rows as one JSON object per line to `path`, and the settings to a
        `.meta.json` file beside it. Existing files of those names are overwritten and missing
        folders are created. This is only the candidate list; it never touches a gold file.

        Args:
            path: The `.jsonl` file to write.
        """
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
        """Return the rows as a polars DataFrame.

        Returns:
            polars.DataFrame: One row per candidate.
        """
        return _frame.to_polars(self.rows)

    def to_pandas(self):
        """Return the rows as a pandas DataFrame.

        Returns:
            pandas.DataFrame: One row per candidate.
        """
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
    """Turn each seed phrase into an embedding vector, for comparing with the corpus.

    Seeds already in the cache cost nothing; the others are sent to the embedding model and their
    cost is recorded.

    Returns:
        list[list[float]]: One vector per seed, in order.
    """
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


def _items(corpus, guard: bool = False, limit: int | None = None, match=None):
    """Read every item of the corpus in its own order, as a generator to close.

    Returns:
        Iterator[tuple]: `(id, text)` pairs.
    """
    if isinstance(corpus, Table):
        return ((r["id"], r["text"]) for r in table_rows(corpus))
    if isinstance(corpus, PgCorpus):
        return pg_items(corpus, guard, limit, match)
    return s3_items(corpus)


def _compile(keywords, regex: bool, uncompiled: list | None = None) -> list[re.Pattern]:
    """Turn keyword terms into compiled patterns.

    With `uncompiled`, a string Python cannot compile is added to it and skipped instead of
    raising (server-side regexes are in the database's syntax).

    Returns:
        list[re.Pattern]: One pattern per term.

    Raises:
        ValueError: A term is blank or would match the empty string.
        TypeError: A term is neither a string nor a compiled pattern.
        re.error: A string is not a valid regular expression and `uncompiled` is None.
    """
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
                if uncompiled is None:
                    raise re.error(
                        f"invalid regular expression {term!r}: {e}"
                    ) from None
                uncompiled.append(term)
                continue
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


def _rank(
    items, patterns: list[re.Pattern], limit: int | None, keep_zero: bool = False
) -> list[dict]:
    """Rank the items matching any pattern, best first.

    Order: distinct patterns matched, then total matches, then corpus order. With a limit only
    that many are held at a time. `keep_zero` also keeps items that match none (the database
    said they match), last.

    Returns:
        list[dict]: `{id, text, terms_matched, matches}` rows.
    """

    def hits():
        for index, (id, text) in enumerate(items):
            counts = [sum(1 for _ in p.finditer(text)) for p in patterns]
            if (terms := sum(c > 0 for c in counts)) or keep_zero:
                yield -terms, -sum(counts), index, id, text

    ranked = heapq.nsmallest(limit, hits()) if limit else sorted(hits())
    return [
        {"id": id, "text": text, "terms_matched": -t, "matches": -m}
        for t, m, _, id, text in ranked
    ]


def _warn_if_recount_differs(rows: list[dict], uncompiled: list[str]) -> None:
    zero = sum(r["terms_matched"] == 0 for r in rows)
    notes = []
    if uncompiled:
        notes.append(
            f"Python could not compile {uncompiled!r}, so they are not counted"
        )
    if zero:
        notes.append(
            f"{zero} returned row{'s' * (zero > 1)} matched on the server but not in Python "
            "(case folding or regular-expression syntax differ) and rank last"
        )
    if notes:
        warnings.warn(
            "server-side ranking is approximate: " + "; ".join(notes), stacklevel=3
        )


async def aget_candidates(
    corpus: Table | S3Corpus | PgCorpus,
    *,
    seeds: Sequence[str] | None = None,
    embedder: str | Embedder | None = None,
    floor: float | None = None,
    keywords: Sequence[str | re.Pattern] | None = None,
    regex: bool = False,
    server_side: bool = False,
    limit: int | None = None,
    out=None,
    cache=None,
) -> Candidates:
    """Choose the items of a corpus to classify (async).

    Use at most one filter. With none, every item is returned in the corpus's own order. With
    `seeds`, the items similar to your example phrases are returned, most similar first (this
    calls an embedding model for seeds not in the cache, which costs money). With `keywords`,
    the items containing any of the terms are returned, best match first (distinct terms
    matched, then total matches, then corpus order). Nothing is written to the corpus.

    Args:
        corpus: A `Table`, `S3Corpus` or `PgCorpus`; `where=` on it has already limited what is seen.
        seeds: Example phrases. Keep items whose highest similarity to any seed is at least
            `floor`; on a tie the earlier seed gets the credit.
        embedder: With `seeds`, the model that embeds them: a "provider:model" string or an
            `Embedder`. Required with `seeds`; must match how the corpus was embedded.
        floor: With `seeds`, the lowest similarity kept; None means 0.60.
        keywords: Terms to look for. A string is matched literally, ignoring case; a compiled
            `re.Pattern` keeps its own flags.
        regex: With `keywords`, treat each string as a regular expression, as written.
        server_side: With `keywords` on a `PgCorpus`, let the database do the matching (plain
            terms with ILIKE, regular-expression strings with `~` in Postgres syntax, no compiled
            patterns). Ranking is still done here, so it can differ slightly; a warning says when.
        limit: Keep only the first N items, or the best N when ranked. At least 1.
        out: Where to save the list as JSONL (with a `.meta.json` beside it). False saves
            nothing. None saves to `<settings.root>/candidates.jsonl` for seeds only, and
            nothing for keywords or the whole corpus.
        cache: With `seeds`, where seed embeddings are remembered: a directory, None for
            `<settings.root>/cache`, or False for none.

    Returns:
        Candidates: The chosen items and how they were chosen.

    Raises:
        TypeError: `corpus` is not a corpus, or `seeds` or `keywords` is a single string, or a
            keyword is neither a string nor a pattern.
        ValueError: Both `seeds` and `keywords` were given, a list is empty, an option is used
            without the filter it belongs to, `server_side` is used without a `PgCorpus`, a
            keyword is blank or matches the empty string, `embedder` is missing with `seeds`,
            or `limit` is below 1.
    """
    if not isinstance(corpus, (Table, S3Corpus, PgCorpus)):
        raise TypeError(
            f"corpus must be a Table, S3Corpus or PgCorpus, not {type(corpus).__name__}"
        )
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
    if keywords is None and (regex or server_side):
        raise ValueError(
            f"{'regex' if regex else 'server_side'} is only used with keywords"
        )
    if server_side and not isinstance(corpus, PgCorpus):
        raise ValueError(
            "server_side needs a PgCorpus: only Postgres can filter on the server"
        )
    for term in keywords or () if server_side else ():
        if isinstance(term, re.Pattern):
            raise ValueError(  # noqa: TRY004  an argument rule, a ValueError like the others
                f"server_side cannot use the compiled pattern {term.pattern!r}: server-side "
                "regular expressions are strings with regex=True, in Postgres syntax"
            )
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
        uncompiled: list[str] = []
        patterns = (
            _compile(keywords, regex, uncompiled if server_side else None)
            if keywords is not None
            else None
        )
        match = (list(keywords), regex) if server_side and keywords else None

        def read():
            with closing(_items(corpus, patterns is None, limit, match)) as items:
                if patterns is None:
                    return [{"id": i, "text": t} for i, t in islice(items, limit)]
                return _rank(items, patterns, limit, keep_zero=server_side)

        rows = await asyncio.to_thread(read)
        if server_side:
            _warn_if_recount_differs(rows, uncompiled)
        result = Candidates(
            rows, floor=None, source="all" if patterns is None else "keywords"
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
    if isinstance(corpus, Table):
        check_table_for_seeds(corpus, model)  # before the embedding calls cost anything
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
    server_side: bool = False,
    limit: int | None = None,
    out=None,
    cache=None,
) -> Candidates:
    """Choose the items of a corpus to classify, for scripts and notebooks.

    The same as `aget_candidates` (see it for what each argument means and for the cost of
    using `seeds`), and also works inside a running event loop.

    Args:
        corpus: A `Table`, `S3Corpus` or `PgCorpus`.
        seeds: Example phrases to find similar items for.
        embedder: The model that embeds the seeds; required with `seeds`.
        floor: The lowest similarity kept; None means 0.60.
        keywords: Terms to look for.
        regex: Treat keyword strings as regular expressions.
        server_side: Let a Postgres database do the keyword matching.
        limit: Keep only the first or best N items.
        out: Where to save the list; False for nowhere.
        cache: Where seed embeddings are remembered.

    Returns:
        Candidates: The chosen items and how they were chosen.

    Raises:
        TypeError: As `aget_candidates`.
        ValueError: As `aget_candidates`.
    """
    return run(
        aget_candidates(
            corpus,
            seeds=seeds,
            embedder=embedder,
            floor=floor,
            keywords=keywords,
            regex=regex,
            server_side=server_side,
            limit=limit,
            out=out,
            cache=cache,
        )
    )
