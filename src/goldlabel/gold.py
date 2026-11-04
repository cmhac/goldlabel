import json
import os
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, ValidationError, field_validator

from goldlabel import _frame, _html
from goldlabel._gold_rule import GOLD_RULE_SHORT, GoldError, GoldTypeError
from goldlabel.candidates import order_by_id
from goldlabel.evaluation import _counts, _history
from goldlabel.settings import resolve
from goldlabel.taxonomy import Taxonomy

NAME = re.compile(r"[a-z0-9_-]+")  # lowercase: dataset names become file names


def check_name(name, what: str = "sample") -> str:
    if not isinstance(name, str) or not NAME.fullmatch(name):
        raise GoldError(
            f"a {what} name is lowercase letters, digits, '-' and '_', not {name!r}"
        )
    return name


def check_size(n, what: str) -> int:
    if isinstance(n, bool) or not isinstance(n, int) or n < 1:
        raise GoldError(f"{what} must be a whole number of at least 1, not {n!r}")
    return n


class GoldRow(BaseModel):
    """One gold item. `labels` is `None` while pending. `sample` is the name of its sample."""

    model_config = ConfigDict(extra="allow")  # a hand-edited file keeps its other keys

    id: str
    text: str
    labels: list[str] | None
    sample: str
    labelled_by: str | None = None  # "goldlabel-ui", "imported" or absent
    labelled_at: str | None = None
    note: str | None = (
        None  # a person's comment on the row, written by the labelling page
    )

    @field_validator("sample")
    @classmethod
    def _sample_name(cls, value: str) -> str:
        if not NAME.fullmatch(value):
            raise ValueError(f"a sample name is [a-z0-9_-]+, not {value!r}")
        return value

    def dump(self) -> dict:
        d = self.model_dump()
        for key in ("labelled_by", "labelled_at", "note"):
            if d[key] is None:
                del d[key]
        return d


def _summary(rows: list[GoldRow]) -> tuple[int, str]:
    labelled = [r for r in rows if r.labels]
    sources = {"goldlabel-ui": 0, "imported": 0, "unstamped": 0}
    for r in labelled:
        key = r.labelled_by if r.labelled_by in sources else "unstamped"
        sources[key] += 1
    return len(labelled), ", ".join(f"{k} {v}" for k, v in sources.items())


def _rows_table(rows: list[GoldRow]) -> str:
    return _html.table(
        ["id", "text", "labels", "sample", "labelled by"],
        [
            (r.id, r.text, r.labels if r.labels else "pending", r.sample, r.labelled_by)
            for r in rows
        ],
    )


@dataclass(frozen=True)
class GoldSet:
    """A read-only snapshot of gold rows."""

    rows: list[GoldRow]
    name: str = "all"
    path: Path | None = None  # the gold file a view of `Gold` came from

    def __len__(self) -> int:
        return len(self.rows)

    def counts(self, taxonomy: Taxonomy) -> dict[str, int]:
        """Rows per label, `off_topic` included; a multi-label row counts once per label."""
        counts = dict.fromkeys(taxonomy.names, 0)
        for r in self.rows:
            for label in r.labels or []:
                if label in counts:
                    counts[label] += 1
        return counts

    def to_polars(self):
        return _frame.to_polars([r.model_dump() for r in self.rows])

    def to_pandas(self):
        return _frame.to_pandas([r.model_dump() for r in self.rows])

    def _summary(self) -> str:
        labelled, by = _summary(self.rows)
        return (
            f"GoldSet {self.name}: {len(self.rows)} rows "
            f"({labelled} labelled, {len(self.rows) - labelled} pending); {by}"
        )

    def _repr_html_(self) -> str:
        return _html.line(self._summary()) + _rows_table(self.rows)

    def __repr__(self) -> str:
        return f"{self._summary()}\n{GOLD_RULE_SHORT}"


class Sample:
    """A live, read-only view of one named sample of a gold dataset, or of several added with `+`.

    It reads the gold file every time it is used, so it never shows stale rows.
    """

    def __init__(self, gold: "Gold", names: tuple[str, ...], drawn: int = 0):
        self.gold, self.names, self.drawn = gold, names, drawn

    @property
    def path(self) -> Path:
        return self.gold.path

    @property
    def rows(self) -> list[GoldRow]:
        return [r for r in self.gold._read() if r.sample in self.names]

    def _set(self) -> GoldSet:
        return GoldSet(self.rows, " + ".join(self.names), self.path)

    def __len__(self) -> int:
        return len(self.rows)

    def counts(self, taxonomy: Taxonomy) -> dict[str, int]:
        return self._set().counts(taxonomy)

    def to_polars(self):
        return self._set().to_polars()

    def to_pandas(self):
        return self._set().to_pandas()

    def __add__(self, other):
        if not isinstance(other, Sample):
            return NotImplemented
        if other.path.resolve() != self.path.resolve():
            raise GoldError(
                f"cannot add samples of two gold datasets ({self.path} and {other.path})"
            )
        new = tuple(n for n in other.names if n not in self.names)
        return Sample(self.gold, self.names + new)

    def _summary(self) -> str:
        rows = self.rows
        labelled, _ = _summary(rows)
        title = " + ".join(f'"{n}"' for n in self.names)
        line = (
            f"Sample {title} of {self.gold.label}: {len(rows)} rows "
            f"({labelled} labelled, {len(rows) - labelled} pending)"
        )
        if len(self.names) == 1:
            line += f"; drew {self.drawn} now" if self.drawn else "; nothing drawn"
        n, prompts = _counts(
            _history(self.path.parent / "evals.jsonl", self.path), self.names
        )
        if not n:
            return line + "; not evaluated"
        return (
            f"{line}; evaluated {n} time{'s' if n != 1 else ''} "
            f"({prompts} prompt{'s' if prompts != 1 else ''})"
        )

    def _repr_html_(self) -> str:
        return _html.line(self._summary()) + _rows_table(self.rows)

    def __repr__(self) -> str:
        return f"{self._summary()}\n{GOLD_RULE_SHORT}"


class Gold:
    """A gold dataset: one file in the storage folder, holding named samples.

    Every property and Sample reads the file again, so nothing shows stale rows.
    """

    def __init__(self, candidates=None, *, name=None, sample_size=50):
        if name is not None:
            check_name(name, "dataset")
        self.candidates, self.name = candidates, name
        self.sample_size = check_size(sample_size, "sample_size")
        self.path = resolve(
            None, "gold.jsonl" if name is None else f"gold-{name}.jsonl"
        )

    @property
    def label(self) -> str:
        return self.name or "default"

    def _samples(self, rows: list[GoldRow]) -> dict[str, list[GoldRow]]:
        by: dict[str, list[GoldRow]] = {}
        for r in rows:
            by.setdefault(r.sample, []).append(r)
        return by

    def __repr__(self) -> str:
        rows = self._read()
        parts = [
            f"{name} {len(rs)} ({sum(1 for r in rs if r.labels)} labelled)"
            for name, rs in self._samples(rows).items()
        ]
        return (
            f"Gold {self.label} ({self.path}): {', '.join(parts) or 'no samples'}; "
            f"{_summary(rows)[1]}\n{GOLD_RULE_SHORT}"
        )

    def _repr_html_(self) -> str:
        table = []
        for name, rs in self._samples(self._read()).items():
            labelled = sum(1 for r in rs if r.labels)
            table.append((name, len(rs), labelled, len(rs) - labelled))
        return _html.line(f"Gold {self.label}: {self.path}") + _html.table(
            ["sample", "rows", "labelled", "pending"], table
        )

    def _read(self) -> list[GoldRow]:
        if not self.path.exists():
            return []
        rows = []
        for n, line in enumerate(self.path.read_text().splitlines(), 1):
            if not line.strip():
                continue
            try:
                rows.append(GoldRow.model_validate(json.loads(line)))
            except (json.JSONDecodeError, ValidationError) as e:
                raise GoldError(f"{self.path}:{n}: not a gold row ({e})") from e
        return rows

    def _write(self, rows: list[GoldRow]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + ".tmp")
        try:
            tmp.write_text("".join(json.dumps(r.dump()) + "\n" for r in rows))
            os.replace(tmp, self.path)
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise

    def _removed(self) -> Path:
        return self.path.with_suffix(".removed.jsonl")

    @property
    def pending(self) -> GoldSet:
        return GoldSet([r for r in self._read() if not r.labels], "pending", self.path)

    @property
    def all(self) -> GoldSet:
        return GoldSet(self._read(), "all", self.path)

    def __getitem__(self, name: str) -> Sample:
        names = list(self._samples(self._read()))
        if name not in names:
            raise KeyError(
                f"no sample {name!r} in {self.path}; samples: {', '.join(names) or 'none'}"
            )
        return Sample(self, (name,))

    def draw_sample(self, name: str, n: int | None = None) -> Sample:
        """Make the sample `name` hold at least `n` rows (default `sample_size`), drawing only the
        shortfall as pending rows, in an order fixed by each candidate's id and this dataset's name.

        Rerunning draws nothing once the sample is full. Never removes rows; never draws an id that
        is already in the file or was removed from it.
        """
        check_name(name)
        n = self.sample_size if n is None else check_size(n, "n")
        rows = self._read()
        need = n - sum(1 for r in rows if r.sample == name)
        if need <= 0:
            return Sample(self, (name,))
        if self.candidates is None:
            raise GoldError(
                f"sample {name!r} needs {need} more rows and this Gold has no candidates: "
                "create it with gl.Gold(candidates)"
            )
        taken = {r.id for r in rows}
        if self._removed().exists():
            taken |= {
                str(json.loads(x)["id"])
                for x in self._removed().read_text().splitlines()
                if x.strip()
            }
        pool = [
            c
            for c in order_by_id(self.candidates.rows, self.name or "")
            if str(c["id"]) not in taken
        ]
        if len(pool) < need:
            raise GoldError(
                f"sample {name!r} needs {need} more rows, but only {len(pool)} candidates "
                f"are not already in {self.path} or removed from it"
            )
        new = [
            GoldRow(id=str(c["id"]), text=c["text"], labels=None, sample=name)
            for c in pool[:need]
        ]
        self._write(rows + new)
        return Sample(self, (name,), drawn=need)

    def import_rows(self, rows, name: str) -> GoldSet:
        """Add rows people already labelled (dicts with `id`, `text`, `labels`) to the sample
        `name`, stamped `imported`. Labels are not checked against a taxonomy here; evaluation does that.
        """
        check_name(name)
        existing = self._read()
        seen = {r.id for r in existing}
        now = datetime.now(UTC).isoformat()
        new = []
        for r in rows:
            missing = [k for k in ("id", "text", "labels") if k not in r]
            if missing or not r["labels"]:
                raise GoldError(
                    f"imported row {r.get('id')!r} needs id, text and labels"
                )
            row = GoldRow.model_validate(
                {**r, "sample": name, "labelled_by": "imported", "labelled_at": now}
            )
            if row.id in seen:
                raise GoldError(f"id {row.id!r} is already in {self.path}")
            seen.add(row.id)
            new.append(row)
        self._write(existing + new)
        return GoldSet(new, "imported")

    def orphaned(self, taxonomy: Taxonomy) -> GoldSet:
        """Labelled rows with a label that is no longer in the taxonomy."""
        names = set(taxonomy.names)
        return GoldSet(
            [r for r in self._read() if r.labels and not set(r.labels) <= names],
            "orphaned",
        )

    def remove(self, ids) -> GoldSet:
        """Move rows to `<gold>.removed.jsonl` (appended) and rewrite the file without them.

        A removed id is never drawn again.
        """
        if isinstance(ids, str):
            raise GoldTypeError("ids must be a list of ids, not a string")
        ids = {str(i) for i in ids}
        rows = self._read()
        unknown = ids - {r.id for r in rows}
        if unknown:
            raise GoldError(f"not in {self.path}: {sorted(unknown)}")
        gone = [r for r in rows if r.id in ids]
        if gone:
            with self._removed().open("a") as f:
                f.write("".join(json.dumps(r.dump()) + "\n" for r in gone))
            self._write([r for r in rows if r.id not in ids])
        return GoldSet(gone, "removed")
