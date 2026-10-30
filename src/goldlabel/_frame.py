"""One place that turns a list of row dicts into a polars or a pandas table, so a result can never export one without the other."""


def _columns(rows: list[dict]) -> dict[str, list]:
    names = list(
        dict.fromkeys(k for r in rows for k in r)
    )  # all keys, first-seen order
    return {name: [r.get(name) for r in rows] for name in names}


def to_polars(rows: list[dict]):
    try:
        import polars
    except ImportError:
        raise ImportError("polars is not installed: pip install polars") from None
    # strict=False lets int and float share a column; the schema is from every row, not the first 100
    return polars.DataFrame(_columns(rows), strict=False)


def to_pandas(rows: list[dict]):
    try:
        import pandas
    except ImportError:
        raise ImportError("pandas is not installed: pip install pandas") from None
    # a column with a missing value stays `object` so it holds None, as polars does (not NaN)
    return pandas.DataFrame(
        {
            name: pandas.Series(values, dtype=object)
            if any(v is None for v in values)
            else values
            for name, values in _columns(rows).items()
        }
    )
