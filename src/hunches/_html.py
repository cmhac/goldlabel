"""Tiny helpers for the notebook reprs. All text is escaped; no colours are set, so the notebook theme shows through."""

import html
from collections.abc import Sequence

CAP = 50
_RULE = "border-bottom:1px solid currentColor"


def esc(value) -> str:
    return html.escape("" if value is None else str(value))


def _cell(value) -> str:
    if isinstance(value, (list, tuple)):
        value = ", ".join(str(v) for v in value)
    return esc(value)


def table(columns: Sequence[str], rows: Sequence[Sequence], cap: int = CAP) -> str:
    """A table of at most `cap` rows, then a "N more" line."""
    head = "".join(
        f'<th style="text-align:left;{_RULE}">{esc(c)}</th>' for c in columns
    )
    body = "".join(
        "<tr>"
        + "".join(f'<td style="vertical-align:top">{_cell(v)}</td>' for v in row)
        + "</tr>"
        for row in rows[:cap]
    )
    more = f"<p>{len(rows) - cap} more rows</p>" if len(rows) > cap else ""
    return f"<table><tr>{head}</tr>{body}</table>{more}"


def bars(values: Sequence[tuple[str, int]]) -> str:
    """One line per (label, count): a bar (shape) and the count as text."""
    top = max([n for _, n in values] + [1])
    lines = "".join(
        f"<div>{esc(name)} "
        f'<span style="display:inline-block;height:0;width:{100 * n / top:.0f}px;'
        f'border-top:0.8em solid currentColor;opacity:0.35"></span> {n}</div>'
        for name, n in values
    )
    return f"<div>{lines}</div>"


def warning(text: str) -> str:
    return f'<p style="font-weight:bold;{_RULE}">WARNING: {esc(text)}</p>'


def details(summary: str, body: str, open: bool = False) -> str:
    return f"<details{' open' if open else ''}><summary>{esc(summary)}</summary>{body}</details>"


def line(text: str) -> str:
    return f"<p>{esc(text)}</p>"
