import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

import numpy as np

# Max results per QueryVectors request: 10,000 (100 per page, followed via nextToken).
# Source: https://docs.aws.amazon.com/AmazonS3/latest/userguide/s3-vectors-limitations.html
S3_TOP_K = 10_000
PG_TOP_K = 10_000
# hnsw.max_scan_tuples for index mode: the pgvector default (20,000; README, "Iterative Scan
# Options"), set explicitly so the result does not depend on the server's configuration.
# Raising it alone did not help (specs/005-pgvector/spec.md, "Verified in task 06").
PG_MAX_SCAN = 20_000
PG_BATCH = 5_000  # rows per round trip of the server-side cursors
# bytes added to every received row (id + text) when sizing a result: Python's tuple, float
# and str headers; a deliberately round estimate, not a measurement
PG_ROW_OVERHEAD = 128
MB = 1024 * 1024


@dataclass(frozen=True, eq=False)
class Table:
    """Items in a table: a `.csv`, `.parquet` or `.jsonl` path, a list of row dicts, or a pandas or
    polars DataFrame. `id_column` None means the row's position. Seed search also needs
    `vector_column` (a list of numbers per row; not in a CSV) and `embedding_model`, the model
    that made them; keyword search and the whole corpus need neither."""

    source: Any
    text_column: str = "text"
    id_column: str | None = None
    vector_column: str | None = None
    embedding_model: str | None = None

    def __post_init__(self):
        if not self.text_column:
            raise ValueError("Table: text_column is required")
        is_path = isinstance(self.source, (str, Path))
        if (
            self.vector_column
            and is_path
            and Path(self.source).suffix.lower() == ".csv"
        ):
            raise ValueError(
                "Table: a CSV file cannot hold vectors, so vector_column cannot be used; "
                "use a .parquet or .jsonl file or a DataFrame"
            )


def table_rows(table: Table, with_vectors: bool = False) -> list[dict]:
    """The table as `{id, text}` rows in table order (plus `vector` when asked for), checked.

    Every source is read with polars. Raises ValueError naming the column or the first offending
    row (counting from 0); rows are never dropped, repaired or invented."""
    import polars as pl

    src = table.source
    try:
        if isinstance(src, (str, Path)):
            path = Path(src)
            suffix = path.suffix.lower()
            if suffix == ".csv":
                df = pl.read_csv(
                    path, infer_schema=False
                )  # text, as written: "007" stays
            elif suffix == ".jsonl":
                df = pl.read_ndjson(path, infer_schema_length=None)
            elif suffix == ".parquet":
                df = pl.read_parquet(path)
            else:
                raise ValueError(
                    f"Table: cannot read {path.name!r}; use a .csv, .parquet or .jsonl file"
                )
        elif isinstance(src, pl.DataFrame):
            df = src
        elif type(src).__module__.startswith("pandas"):
            df = pl.from_pandas(src)
        else:
            # every row, so a key first seen after row 100 is still a column; strict=False lets
            # int and float share a column (vectors like [1, 0.71]), as JSONL reading does
            df = pl.DataFrame(list(src), infer_schema_length=None, strict=False)
    except (pl.exceptions.PolarsError, TypeError) as e:
        raise ValueError(f"Table: polars could not read the source: {e}") from None
    if df.height == 0:
        return []
    rows = df.to_dicts()
    columns = [table.text_column]
    columns += [c for c in (table.id_column, with_vectors and table.vector_column) if c]
    out, seen = [], set()
    for i, row in enumerate(rows):
        for column in columns:
            if column not in row:
                raise ValueError(f"Table row {i}: no column {column!r}")
        text = row[table.text_column]
        if not (isinstance(text, str) and text.strip()):
            raise ValueError(
                f"Table row {i}: column {table.text_column!r} is not a non-empty string"
            )
        id_ = row[table.id_column] if table.id_column else i
        if id_ is None or str(id_) == "":
            raise ValueError(f"Table row {i}: column {table.id_column!r} is empty")
        if str(id_) in seen:
            raise ValueError(f"Table row {i}: repeated id {str(id_)!r}")
        seen.add(str(id_))
        item = {"id": str(id_), "text": text}
        if with_vectors and table.vector_column:
            item["vector"] = row[table.vector_column]
        out.append(item)
    return out


def check_table_for_seeds(table: Table, embedding_model: str) -> None:
    """Refuse a table that cannot answer a seed search. Cheap, so callers run it before they
    spend money embedding the seeds."""
    if table.vector_column is None:
        raise ValueError(
            "the table has no embedding column; seed search needs Table(vector_column=...) "
            "(keywords and the whole corpus need none)"
        )
    if table.embedding_model is None:
        raise ValueError(
            "the table has no embedding_model; seed search needs the model that made the vectors"
        )
    if table.embedding_model != embedding_model:
        raise ValueError(
            f"embedding model mismatch: table uses {table.embedding_model!r}, "
            f"the embedder is {embedding_model!r}"
        )


def search_table(
    table: Table, vectors, floor: float, embedding_model: str
) -> tuple[list[list[tuple[str, str, float]]], bool]:
    """One pass over the table for every seed: ([(id, text, similarity) per seed], False), best
    first, all with similarity >= floor. Never capped."""
    check_table_for_seeds(table, embedding_model)
    rows = table_rows(table, with_vectors=True)
    if not rows:
        return [[] for _ in vectors], False
    matrix = []
    for i, row in enumerate(rows):
        try:
            v = np.asarray(row["vector"], dtype=np.float32)
        except (TypeError, ValueError):
            v = None
        if (
            v is None
            or v.ndim != 1
            or v.size == 0
            or v.size != len(matrix[0] if matrix else v)
        ):
            raise ValueError(
                f"Table row {i}: column {table.vector_column!r} is not a list of numbers "
                "of the same length as row 0"
            )
        matrix.append(v)
    unit = np.stack(matrix)
    if unit.shape[1] != len(vectors[0]):
        raise ValueError(
            f"the embedder's vectors have {len(vectors[0])} numbers, "
            f"the table's have {unit.shape[1]}"
        )
    norms = np.linalg.norm(unit, axis=1)
    norms[norms == 0] = 1
    unit = unit / norms[:, None]
    queries = np.asarray(vectors, dtype=np.float32)
    sims = unit @ (queries / np.linalg.norm(queries, axis=1, keepdims=True)).T
    per_seed = []
    for j in range(len(vectors)):
        order = np.argsort(-sims[:, j], kind="stable")
        per_seed.append(
            [
                (rows[i]["id"], rows[i]["text"], float(sims[i, j]))
                for i in order
                if sims[i, j] >= floor
            ]
        )
    return per_seed, False


@dataclass(frozen=True)
class S3Corpus:
    bucket: str
    index: str
    region: str | None = None  # None: boto3's default resolution

    def __post_init__(self):
        if not (self.bucket and self.index):
            raise ValueError("S3Corpus: bucket and index are required")


@dataclass(frozen=True)
class PgCorpus:
    """A pgvector table. The database URL is read from the environment variable `url_env`,
    never stored. With `text_table` the text lives in a second table joined on
    `text_id_column` (default: `id_column`) = `id_column`."""

    table: str
    id_column: str = "id"
    text_column: str = "text"
    vector_column: str = "embedding"
    text_table: str | None = None
    text_id_column: str | None = None
    url_env: str = "GOLDLABEL_PG_URL"
    search: str = "exact"  # "exact" or "index"
    statement_timeout_s: int | None = None  # None: the server's own; 0: no limit
    auth: str = "url"  # "url" or "rds_iam"
    aws_region: str | None = None
    aws_profile: str | None = None
    max_result_mb: int = 512  # 0: no limit

    def __post_init__(self):
        if not self.table:
            raise ValueError("PgCorpus: table is required")
        if not self.url_env:
            raise ValueError("PgCorpus: url_env is required")
        if self.search not in ("exact", "index"):
            raise ValueError('PgCorpus: search must be "exact" or "index"')
        if self.auth not in ("url", "rds_iam"):
            raise ValueError('PgCorpus: auth must be "url" or "rds_iam"')
        if self.max_result_mb < 0:
            raise ValueError("PgCorpus: max_result_mb must be 0 or more")
        if self.statement_timeout_s is not None and self.statement_timeout_s < 0:
            raise ValueError("PgCorpus: statement_timeout_s must be 0 or more")

    def check(self, seeds: int | None = None) -> dict:
        """Read-only report on the table (see _check); does not raise."""
        return _check(self, seeds)


class SearchCancelled(Exception):
    """The search was stopped with Stop.stop()."""


class Stop:
    """Handle for stopping a search from another thread: pass it to search_pg_exact and call
    stop(). Cancelling the calling thread alone would leave the driver blocked in the query."""

    def __init__(self):
        self.conn = None
        self.stopped = False

    def stop(self):
        self.stopped = True
        if self.conn is not None:
            _cancel(self.conn)


def _cancel(conn):
    # cancel_safe() is psycopg 3.2+; the extras do not pin a version, so fall back plainly
    (getattr(conn, "cancel_safe", None) or conn.cancel)()


def _too_large(
    text: str, limit_mb: int, hint: str = "Use fewer seeds or raise the limit"
) -> RuntimeError:
    return RuntimeError(
        f"{text} which exceeds the result limit of {limit_mb} MB. "
        f"{hint} in PgCorpus(max_result_mb=...)."
    )


IAM_CHECK = (
    "Check: the database user has the rds_iam role, the AWS identity may rds-db:connect "
    "on this DbiResourceId/user, and the URL host is the instance endpoint "
    "(not a custom DNS name)."
)


def pg_message(e: Exception, corpus: PgCorpus, token: str | None = None) -> str:
    """An exception's text with the URL, password and IAM token replaced by ***, plus a hint."""
    text = str(e)
    url = os.environ.get(corpus.url_env) or ""
    password = urlsplit(url).password or ""
    secrets = [url, password, unquote(password), token or ""]
    for secret in sorted(set(secrets), key=len, reverse=True):
        if secret:
            text = text.replace(secret, "***")
    hint = None
    if "conflict with recovery" in text:
        hint = (
            "Fix: run the search against the primary/writer endpoint, or a replica "
            "configured for long queries."
        )
    elif "statement timeout" in text:
        hint = (
            "Fix: raise statement_timeout for this role, or set "
            "PgCorpus(statement_timeout_s=...)"
        )
    elif re.search(r"different \w+ dimensions", text):
        hint = "Fix: the embedder must be the model the table was embedded with."
    elif token and "authentication failed" in text:
        hint = IAM_CHECK
    return f"{text}\n{hint}" if hint else text


def pg_connect(corpus: PgCorpus):
    """Open a read-only connection; the caller owns it and the one transaction it starts."""
    try:
        import psycopg
    except ImportError as e:
        raise ImportError(
            "The pgvector backend needs psycopg: pip install goldlabel[pg]"
        ) from e
    url = os.environ.get(corpus.url_env)
    if not url:
        raise ValueError(
            "The database URL is not set: set the environment variable "
            f"{corpus.url_env}"
        )
    kwargs: dict = {"prepare_threshold": None}
    token = None
    if corpus.auth == "rds_iam":
        token = _iam_token(corpus, url)
        kwargs["password"] = token  # a keyword, never inside the URL string
        if "sslmode" not in url:
            kwargs["sslmode"] = "require"
    try:
        conn = psycopg.connect(url, **kwargs)
        conn.read_only = True
        conn.isolation_level = psycopg.IsolationLevel.REPEATABLE_READ
        if corpus.statement_timeout_s is not None:  # 0 is a value: no limit
            with conn.cursor() as cur:
                cur.execute(  # ty: ignore[no-matching-overload]  int() cast, not user text
                    f"SET LOCAL statement_timeout = {int(corpus.statement_timeout_s) * 1000}"
                )
    except Exception as e:  # noqa: BLE001  the driver's own classes are not imported here
        raise RuntimeError(pg_message(e, corpus, token)) from None
    return conn


def _iam_token(corpus: PgCorpus, url: str) -> str:
    try:
        import boto3
        from botocore.exceptions import BotoCoreError, ClientError
    except ImportError as e:
        raise ImportError(
            "IAM authentication needs boto3: pip install goldlabel[rds]"
        ) from e
    parts = urlsplit(url)
    if not (parts.hostname and parts.username):
        raise ValueError("the rds_iam URL needs a host and a user")
    try:
        session = boto3.Session(profile_name=corpus.aws_profile)
        region = corpus.aws_region or session.region_name
        if not region:
            raise ValueError("aws_region is not set and boto3 found no default region")
        return session.client("rds", region_name=region).generate_db_auth_token(
            DBHostname=parts.hostname,
            Port=parts.port or 5432,
            DBUsername=unquote(parts.username),
            Region=region,
        )
    except (BotoCoreError, ClientError) as e:
        raise ValueError(f"AWS: {e}") from None


def _regclass(table: str) -> str:
    """`schema.table` or `table` as a quoted name for a `%s::regclass` parameter."""
    schema, dot, name = table.partition(".")
    parts = [schema, name] if dot else [schema]
    return ".".join('"' + p.replace('"', '""') + '"' for p in parts)


def text_source(corpus: PgCorpus) -> tuple[str, str]:
    """(table, id column) the text is read from: text_table in the two-table layout."""
    if corpus.text_table:
        return corpus.text_table, corpus.text_id_column or corpus.id_column
    return corpus.table, corpus.id_column


def _texts_query(corpus: PgCorpus):
    """SELECT id, text for a list of ids (the one parameter), from the text table."""
    from psycopg import sql

    table, id_column = text_source(corpus)
    return sql.SQL("SELECT {id}, {text} FROM {table} WHERE {id} = ANY(%s)").format(
        id=sql.Identifier(id_column),
        text=sql.Identifier(corpus.text_column),
        table=sql.Identifier(*table.split(".", 1)),
    )


def extension_version(conn) -> tuple[tuple[int, int, int], str]:
    """((major, minor, patch), schema) of the vector extension."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT e.extversion, n.nspname FROM pg_extension e "
            "JOIN pg_namespace n ON n.oid = e.extnamespace WHERE e.extname = 'vector'"
        )
        row = cur.fetchone()
    if not row:
        raise RuntimeError(
            "The vector extension is not installed in this database "
            "(CREATE EXTENSION vector needs a DBA)."
        )
    # a suffix such as 0.8.0rc1 or 1.0.0-beta is ignored
    parts = re.match(r"(\d+)(?:\.(\d+))?(?:\.(\d+))?", row[0])
    major, minor, patch = (int(g or 0) for g in parts.groups()) if parts else (0, 0, 0)
    return (major, minor, patch), row[1]


def require_index_mode_version(version: tuple[int, int, int], mode: str) -> None:
    if mode == "index" and version < (0, 8, 0):
        raise RuntimeError(
            f'search="index" needs pgvector 0.8.0 or newer (found '
            f"{'.'.join(map(str, version))}). "
            'Use search="exact", or upgrade the extension.'
        )


def column_type(conn, table: str, column: str) -> tuple[str, str, int | None]:
    """(type name, type schema, dimension or None) of a vector or halfvec column."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT t.typname, tn.nspname, a.atttypmod FROM pg_attribute a "
            "JOIN pg_type t ON t.oid = a.atttypid "
            "JOIN pg_namespace tn ON tn.oid = t.typnamespace "
            "WHERE a.attrelid = %s::regclass AND a.attname = %s AND NOT a.attisdropped",
            (_regclass(table), column),
        )
        row = cur.fetchone()
    if not row:
        raise RuntimeError(f'column "{column}" of relation "{table}" does not exist')
    typename, schema, typmod = row
    if typename not in ("vector", "halfvec"):
        raise RuntimeError(
            f'Column "{column}" has type {typename}; goldlabel supports vector and halfvec.'
        )
    return typename, schema, typmod if typmod > 0 else None  # -1: no dimension declared


def table_estimates(
    conn, table: str, text_column: str
) -> tuple[int | None, int | None]:
    """(planner row estimate, average text width in bytes); None where there are no statistics."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT reltuples FROM pg_class WHERE oid = %s::regclass",
            (_regclass(table),),
        )
        row = cur.fetchone()
        rows = int(row[0]) if row and row[0] >= 0 else None  # -1: never analysed
        cur.execute(
            "SELECT max(s.avg_width) FROM pg_stats s "
            "JOIN pg_class c ON c.relname = s.tablename "
            "JOIN pg_namespace n ON n.oid = c.relnamespace AND n.nspname = s.schemaname "
            "WHERE c.oid = %s::regclass AND s.attname = %s",
            (_regclass(table), text_column),
        )
        row = cur.fetchone()
    return rows, row[0] if row and row[0] is not None else None


def search_pg_exact(
    corpus: PgCorpus, vectors, floor: float, progress=None, stop: Stop | None = None
) -> tuple[list[list[tuple[str, str, float]]], bool]:
    """One pass over the table for every seed: ([hits per seed], capped), best first.

    Runs in the one read-only REPEATABLE READ transaction pg_connect opened. Step 1 returns
    ids only (a narrow sort), step 2 the text of the distinct ids. `capped` is True when some
    seed has exactly PG_TOP_K hits. The result size is limited by corpus.max_result_mb
    (0 = none): refused up front from the planner statistics, or aborted while streaming.
    `progress(received, 0, "")` is called per row received (a zero total is unknown); `stop`
    is a Stop whose stop() cancels the running query, after which SearchCancelled is raised.
    """
    limit_mb = corpus.max_result_mb
    limit = limit_mb * MB
    conn = pg_connect(corpus)
    if stop:
        stop.conn = conn
    received = rows_in = 0

    def count(id_, text=""):
        nonlocal received, rows_in
        received += len(str(id_)) + len(text.encode()) + PG_ROW_OVERHEAD
        rows_in += 1
        if progress:
            progress(rows_in, 0, "")
        if limit and received > limit:
            _cancel(conn)
            conn.close()
            raise _too_large(
                f"Search has already received {received / MB:.1f} MB ({rows_in:,} rows),",
                limit_mb,
            )

    try:
        from psycopg import sql

        if stop and stop.stopped:
            raise SearchCancelled
        extension_version(conn)  # for its "not installed" error
        table_name = corpus.table
        table = sql.Identifier(*table_name.split(".", 1))
        id_col = sql.Identifier(corpus.id_column)
        vec_col = sql.Identifier(corpus.vector_column)
        typename, type_schema, _ = column_type(conn, table_name, corpus.vector_column)
        step1 = sql.SQL(
            "WITH seeds AS MATERIALIZED (SELECT u.i - 1 AS i, u.q::{vtype} AS q "
            "FROM unnest(%s::text[]) WITH ORDINALITY AS u(q, i)), "
            "pairs AS (SELECT t.{id} AS id, d.i, d.sim FROM {table} t "
            "CROSS JOIN LATERAL (SELECT s.i, 1 - (t.{vec} OPERATOR({schema}.<=>) s.q) AS sim "
            "FROM seeds s OFFSET 0) d "
            "WHERE t.{vec} IS NOT NULL AND d.sim >= %s AND d.sim <> 'NaN'), "
            "ranked AS (SELECT *, row_number() OVER "
            "(PARTITION BY i ORDER BY sim DESC, id) AS rn FROM pairs) "
            "SELECT id, i, sim FROM ranked WHERE rn <= %s"
        ).format(
            vtype=sql.Identifier(type_schema, typename),
            id=id_col,
            table=table,
            vec=vec_col,
            schema=sql.Identifier(type_schema),
        )
        if limit:
            _, width = table_estimates(conn, text_source(corpus)[0], corpus.text_column)
            if width is not None:  # no statistics: nothing to check
                per_row = width + PG_ROW_OVERHEAD
                worst = len(vectors) * PG_TOP_K * per_row
                if worst > limit:
                    raise _too_large(
                        f"Search could return up to ~{worst / MB:.0f} MB "
                        f"({len(vectors)} seeds × {PG_TOP_K:,} hits × ~{per_row} bytes)",
                        limit_mb,
                    )
        literals = ["[" + ",".join(repr(float(x)) for x in v) + "]" for v in vectors]
        per_seed: list[list[tuple]] = [[] for _ in literals]
        with conn.cursor(name="goldlabel_pairs") as cur:
            cur.itersize = PG_BATCH
            cur.execute(step1, (literals, floor, PG_TOP_K))
            for id_, i, sim in cur:
                count(id_)
                per_seed[i].append((id_, sim))
        ids = list(dict.fromkeys(id_ for rows in per_seed for id_, _ in rows))
        texts = {}
        if ids:
            with conn.cursor(name="goldlabel_texts") as cur:
                cur.itersize = PG_BATCH
                cur.execute(_texts_query(corpus), (ids,))
                for id_, text in cur:
                    count(id_, text)
                    texts[id_] = text
        hits = []
        for rows in per_seed:
            rows.sort(key=lambda r: (-r[1], r[0]))
            for id_, _ in rows:
                if id_ not in texts:
                    raise RuntimeError(f"no text row for id {str(id_)!r}")
            hits.append([(str(id_), texts[id_], sim) for id_, sim in rows])
        return hits, any(len(rows) == PG_TOP_K for rows in per_seed)
    except SearchCancelled:
        raise
    except Exception as e:  # noqa: BLE001  the driver's own classes are not imported here
        if stop and stop.stopped:
            raise SearchCancelled from None
        raise RuntimeError(pg_message(e, corpus)) from None
    finally:
        conn.close()


def pg_items(
    corpus: PgCorpus,
    guard: bool = False,
    limit: int | None = None,
    match: tuple[list[str], bool] | None = None,
):
    """Yield (id, text) of every item in ascending id order, never touching the vectors.

    `guard`: the caller keeps everything it reads, so refuse up front from the planner statistics
    (rows, or `limit` if smaller) and abort while streaming past corpus.max_result_mb (0 = none).
    `match` = (terms, regex): only rows whose text matches any term, filtered by the database
    (ILIKE for plain terms, `~` for regex strings); the terms are bound parameters only.
    Close the generator to close the connection."""
    limit_mb = corpus.max_result_mb
    hint = "Use a keyword filter, a limit, or raise the limit"
    conn = pg_connect(corpus)
    try:
        from psycopg import sql

        table = sql.Identifier(*corpus.table.split(".", 1))
        text_table, text_id = text_source(corpus)
        if guard and limit_mb:
            rows, width = table_estimates(conn, text_table, corpus.text_column)
            if (
                rows is not None and width is not None
            ):  # no statistics: only the stream checks
                per_row = width + PG_ROW_OVERHEAD
                worst = min(rows, limit or rows) * per_row
                if worst > limit_mb * MB:
                    raise _too_large(
                        f"Reading the corpus would return up to ~{worst / MB:.0f} MB "
                        f"({min(rows, limit or rows):,} rows × ~{per_row} bytes)",
                        limit_mb,
                        hint,
                    )
        names: dict[str, Any] = {
            "id": sql.Identifier(corpus.id_column),
            "text": sql.Identifier(corpus.text_column),
            "table": table,
            "text_table": sql.Identifier(*text_table.split(".", 1)),
            "text_id": sql.Identifier(text_id),
        }
        params = None
        if match:
            terms, is_regex = match
            names["op"] = sql.SQL("~" if is_regex else "ILIKE")
            # LIKE's default escape character is the backslash
            params = (
                terms
                if is_regex
                else ["%" + re.sub(r"([\\%_])", r"\\\1", t) + "%" for t in terms],
            )
        if corpus.text_table and match:
            query = sql.SQL(
                "SELECT t.{id}, x.{text} FROM {table} t JOIN {text_table} x "
                "ON x.{text_id} = t.{id} WHERE x.{text} {op} ANY(%s::text[]) ORDER BY t.{id}"
            )
        elif corpus.text_table:
            query = sql.SQL(
                "SELECT t.{id}, x.{text} FROM {table} t LEFT JOIN {text_table} x "
                "ON x.{text_id} = t.{id} ORDER BY t.{id}"
            )
        elif match:
            query = sql.SQL(
                "SELECT {id}, {text} FROM {table} WHERE {text} {op} ANY(%s::text[]) "
                "ORDER BY {id}"
            )
        else:
            query = sql.SQL("SELECT {id}, {text} FROM {table} ORDER BY {id}")
        query = query.format(**names)
        received = rows_in = 0
        with conn.cursor(name="goldlabel_items") as cur:
            cur.itersize = PG_BATCH
            cur.execute(query, params)
            for id_, text in cur:
                if text is None:
                    raise RuntimeError(f"no text row for id {str(id_)!r}")
                rows_in += 1
                received += len(str(id_)) + len(text.encode()) + PG_ROW_OVERHEAD
                if guard and limit_mb and received > limit_mb * MB:
                    raise _too_large(
                        f"Reading has already received {received / MB:.1f} MB "
                        f"({rows_in:,} rows),",
                        limit_mb,
                        hint,
                    )
                yield str(id_), text
    except Exception as e:  # noqa: BLE001  the driver's own classes are not imported here
        message = pg_message(e, corpus)
        if match and match[1]:
            message += f"\nServer-side regular expressions use Postgres syntax; the terms were {match[0]!r}."
        raise RuntimeError(message) from None
    finally:
        conn.close()


def is_approximate(corpus) -> bool:
    """True when the pgvector search may hide hits above the floor (index mode)."""
    return isinstance(corpus, PgCorpus) and corpus.search == "index"


def _search_pg_index(
    corpus: PgCorpus, query_vector: list[float], floor: float
) -> tuple[list[tuple[str, str, float]], bool]:
    """One ANN-index query for one seed; the caller (search) has checked the mode."""
    conn = pg_connect(corpus)
    try:
        from psycopg import sql

        version, _ = extension_version(conn)
        require_index_mode_version(version, "index")  # before any SET
        table_name = corpus.table
        vec_name = corpus.vector_column
        typename, type_schema, _ = column_type(conn, table_name, vec_name)
        dist = sql.SQL("1 - ({vec} OPERATOR({schema}.<=>) %s::{vtype})").format(
            vec=sql.Identifier(vec_name),
            schema=sql.Identifier(type_schema),
            vtype=sql.Identifier(type_schema, typename),
        )
        two_tables = bool(corpus.text_table)
        query = sql.SQL(
            "SELECT {id}, {text}, {dist} AS sim FROM {table} "
            "WHERE {dist} >= %s AND {dist} <> 'NaN' "
            "ORDER BY {vec} OPERATOR({schema}.<=>) %s::{vtype} LIMIT %s"
        ).format(
            id=sql.Identifier(corpus.id_column),
            # two tables: the text comes from a second query, as in exact step 2
            text=sql.SQL("NULL") if two_tables else sql.Identifier(corpus.text_column),
            dist=dist,
            table=sql.Identifier(*table_name.split(".", 1)),
            vec=sql.Identifier(vec_name),
            schema=sql.Identifier(type_schema),
            vtype=sql.Identifier(type_schema, typename),
        )
        literal = "[" + ",".join(repr(float(x)) for x in query_vector) + "]"
        with conn.cursor() as cur:
            cur.execute("SET LOCAL hnsw.iterative_scan = relaxed_order")
            cur.execute(f"SET LOCAL hnsw.max_scan_tuples = {int(PG_MAX_SCAN)}")
            cur.execute(query, (literal, literal, floor, literal, literal, PG_TOP_K))
            rows = cur.fetchall()
            if two_tables and rows:
                cur.execute(_texts_query(corpus), ([r[0] for r in rows],))
                texts = dict(cur.fetchall())
                missing = [r[0] for r in rows if r[0] not in texts]
                if missing:
                    raise RuntimeError(f"no text row for id {str(missing[0])!r}")
                rows = [(i, texts[i], sim) for i, _, sim in rows]
        # relaxed order: the index may return rows slightly out of order
        hits = sorted(
            ((str(i), t, float(sim)) for i, t, sim in rows), key=lambda h: -h[2]
        )
        return hits, len(rows) == PG_TOP_K
    except Exception as e:  # noqa: BLE001  the driver's own classes are not imported here
        raise RuntimeError(pg_message(e, corpus)) from None
    finally:
        conn.close()


def search_vectors(
    corpus: S3Corpus | PgCorpus,
    vector: list[float],
    floor: float,
    *,
    embedding_model: str,
) -> tuple[list[tuple[str, str, float]], bool]:
    """Return ([(id, text, similarity)], capped), best first, all with similarity >= floor.

    `capped` is True when the S3 per-query topK limit may have hidden hits above the floor
    (the highest-scoring hits are returned); show a warning. pgvector `exact` search answers
    every seed at once: use search_pg_exact; a Table: use search_table.
    """
    if isinstance(corpus, PgCorpus):
        if corpus.search != "index":
            raise RuntimeError(
                'search_vectors() runs search="index" only; exact search is search_pg_exact'
            )
        return _search_pg_index(corpus, vector, floor)

    try:
        import boto3
    except ImportError as e:
        raise ImportError(
            "The S3 backend needs boto3: pip install goldlabel[s3]"
        ) from e
    client = boto3.client("s3vectors", region_name=corpus.region)
    params = {
        "vectorBucketName": corpus.bucket,
        "indexName": corpus.index,
        "queryVector": {"float32": [float(x) for x in vector]},
        "topK": S3_TOP_K,
        "returnDistance": True,
        "returnMetadata": True,
    }
    hits: list[tuple[str, str, float]] = []
    below_floor = False
    response = client.query_vectors(**params)
    while True:
        for v in response["vectors"]:
            # Cosine distance is taken as 1 - cosine similarity; the AWS docs do not state
            # this definition explicitly (see task 05 notes).
            sim = 1.0 - v["distance"]
            if sim < floor:
                below_floor = True
                break
            hits.append((v["key"], v["metadata"]["text"], sim))
        if below_floor or not response.get("nextToken"):
            break
        response = client.query_vectors(**params, nextToken=response["nextToken"])
    return hits, len(hits) >= S3_TOP_K and not below_floor


def s3_items(corpus: S3Corpus):
    """Yield (key, text) of every vector in the index, in the service's own order, with the
    vectors themselves never requested."""
    try:
        import boto3
        from botocore.exceptions import ClientError
    except ImportError as e:
        raise ImportError(
            "The S3 backend needs boto3: pip install goldlabel[s3]"
        ) from e
    client = boto3.client("s3vectors", region_name=corpus.region)
    params = {
        "vectorBucketName": corpus.bucket,
        "indexName": corpus.index,
        "returnMetadata": True,
        "maxResults": 1000,
    }
    while True:
        try:
            response = client.list_vectors(**params)
        except ClientError as e:
            if e.response["Error"]["Code"] != "AccessDeniedException":
                raise
            raise RuntimeError(
                f"Access denied listing {corpus.bucket}/{corpus.index}: reading every item "
                "needs the permissions s3vectors:ListVectors and s3vectors:GetVectors"
            ) from None
        for v in response["vectors"]:
            yield v["key"], v["metadata"]["text"]
        if not response.get("nextToken"):
            return
        params["nextToken"] = response["nextToken"]


POOLER_HINT = (
    "The URL looks like a transaction pooler (port 6543 or a pooler. host). Long "
    "searches can be cut off there; consider the direct or session-mode URL."
)


def _check(corpus: PgCorpus, seeds: int | None = None) -> dict:
    """Read-only report on the table (PgCorpus.check); does not raise.

    Each piece runs in its own savepoint, so a failing query (its scrubbed text goes in
    "errors" under the piece's name) does not hide the others. No count(*)."""
    from psycopg import sql

    out: dict = {
        "version": None,
        "schema": None,
        "encrypted": None,
        "type": None,
        "dimension": None,
        "rows": None,
        "indexes": [],
        "sample": None,
        "warnings": [],
        "notes": [],
        "errors": {},
    }
    try:
        conn = pg_connect(corpus)
    except Exception as e:  # noqa: BLE001  pg_connect has already scrubbed the text
        out["errors"]["connect"] = str(e)
        return out
    table = corpus.table
    column = corpus.vector_column
    text_column = corpus.text_column
    mode = corpus.search
    parts = urlsplit(os.environ.get(corpus.url_env) or "")
    if parts.port == 6543 or "pooler." in (parts.hostname or ""):
        out["notes"].append(POOLER_HINT)

    def version():
        out["version"], out["schema"] = extension_version(conn)
        try:
            require_index_mode_version(out["version"], mode)
        except RuntimeError as e:
            out["warnings"].append(str(e))

    def encryption():
        with conn.cursor() as cur:
            cur.execute("SELECT ssl FROM pg_stat_ssl WHERE pid = pg_backend_pid()")
            row = cur.fetchone()
        out["encrypted"] = bool(row[0]) if row else None

    def vector_column():
        try:
            out["type"], _, out["dimension"] = column_type(conn, table, column)
        except RuntimeError as e:
            if not str(e).startswith(
                "Column "
            ):  # an unsupported type; else it is missing
                raise
            out["warnings"].append(str(e))

    def estimates():
        out["rows"] = table_estimates(conn, table, text_column)[0]

    def indexes():
        with conn.cursor() as cur:
            # indkey and indclass are parallel arrays; an expression index has attnum 0,
            # never matches the column, and so is not listed
            cur.execute(
                "SELECT i.relname, am.amname, oc.opcname FROM pg_index x "
                "JOIN pg_class i ON i.oid = x.indexrelid "
                "JOIN pg_am am ON am.oid = i.relam "
                "JOIN pg_attribute a ON a.attrelid = x.indrelid AND a.attname = %s "
                "AND NOT a.attisdropped "
                "CROSS JOIN LATERAL unnest(x.indkey::int2[], x.indclass::oid[]) "
                "AS k(attnum, opc) JOIN pg_opclass oc ON oc.oid = k.opc "
                "WHERE x.indrelid = %s::regclass AND k.attnum = a.attnum "
                "ORDER BY i.relname",
                (column, _regclass(table)),
            )
            out["indexes"] = [tuple(r) for r in cur.fetchall()]

    def sample():
        id_column = sql.Identifier(corpus.id_column)
        vectors = sql.Identifier(*table.split(".", 1))
        if corpus.text_table:
            # one joined row proves both tables, all four columns and comparable id types
            text_table, text_id = text_source(corpus)
            query = sql.SQL(
                "SELECT v.{}, left(t.{}, 60) FROM {} v JOIN {} t ON t.{} = v.{} LIMIT 1"
            ).format(
                id_column,
                sql.Identifier(text_column),
                vectors,
                sql.Identifier(*text_table.split(".", 1)),
                sql.Identifier(text_id),
                id_column,
            )
        else:
            query = sql.SQL("SELECT {}, left({}, 60) FROM {} LIMIT 1").format(
                id_column, sql.Identifier(text_column), vectors
            )
        with conn.cursor() as cur:
            cur.execute(query)
            row = cur.fetchone()
        out["sample"] = (row[0], row[1] or "") if row else None

    try:
        for name, fn in [
            ("version", version),
            ("encryption", encryption),
            ("column", vector_column),
            ("estimates", estimates),
            ("indexes", indexes),
            ("sample", sample),
        ]:
            try:
                with conn.transaction():
                    fn()
            except Exception as e:  # noqa: BLE001  whatever the driver raises
                out["errors"][name] = pg_message(e, corpus)
    finally:
        conn.close()

    if corpus.text_table and out["sample"] is None and "sample" not in out["errors"]:
        out["warnings"].append(
            "No row of the table has a matching row in the text table: check the "
            "id col and text id col."
        )
    rows = "?" if out["rows"] is None else out["rows"]
    if "indexes" not in out["errors"]:
        cosine = f"{out['type'] or 'vector'}_cosine_ops"  # halfvec has its own class
        if mode == "index" and not any(i[2] == cosine for i in out["indexes"]):
            out["warnings"].append(
                f'search="index" but no index on "{column}" uses {cosine}; '
                "the search orders by <=> (cosine), so Postgres would not use it."
            )
        if mode == "exact" and not out["indexes"]:
            out["notes"].append(
                f"No index: the search scans the whole table (~{rows} rows)."
            )
    if seeds is not None:
        pairs = "?" if out["rows"] is None else f"{seeds * out['rows']:,}"
        shown = "?" if out["rows"] is None else f"{out['rows']:,}"
        out["notes"].append(
            f"Worst case {pairs} pairs ({seeds} seeds x {shown} rows). A low floor on a "
            "large table sorts up to this many pairs on the server (spills to temporary "
            "files). Ask your DBA about temp_file_limit."
        )
    return out
