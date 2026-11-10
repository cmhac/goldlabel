"""Gold datasets: the rows people labelled by hand, kept in one file in the storage folder, in named samples."""

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
_KEEP = object()  # `_write(rows)` keeps the taxonomy already stored in the file


def _check_name(name, what: str = "sample") -> str:
    if not isinstance(name, str) or not NAME.fullmatch(name):
        raise GoldError(
            f"a {what} name is lowercase letters, digits, '-' and '_', not {name!r}"
        )
    return name


def _check_size(n, what: str) -> int:
    if isinstance(n, bool) or not isinstance(n, int) or n < 1:
        raise GoldError(f"{what} must be a whole number of at least 1, not {n!r}")
    return n


class GoldRow(BaseModel):
    """One row of a gold dataset: a text and the labels a person gave it.

    Attributes:
        id: The row's id, a string, taken from the candidate it was drawn from.
        text: The text a person labels.
        labels: The labels a person chose, or None while the row is pending (not yet labelled).
        sample: The name of the sample the row belongs to.
        labelled_by: "goldlabel-ui" (labelled in the labelling page), "imported" (brought in
            with `Gold.import_rows`) or None.
        labelled_at: When the labels were saved, as an ISO date and time.
        note: A comment a person wrote on the row in the labelling page; it is never sent to a model.
        revisions: The earlier labels, notes and stamps of the row, oldest first, kept when a
            person changes an already labelled row in the labelling page.
    """

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
    # the values before each change the labelling page made to an already-labelled row, oldest
    # first: {"at", "labels", "note", "labelled_by"}
    revisions: list[dict] | None = None

    @field_validator("sample")
    @classmethod
    def _sample_name(cls, value: str) -> str:
        if not NAME.fullmatch(value):
            raise ValueError(f"a sample name is [a-z0-9_-]+, not {value!r}")
        return value

    def dump(self) -> dict:
        """Return the row as a plain dict for the gold file, leaving out fields that are empty.

        Returns:
            dict: The row's fields; `labelled_by`, `labelled_at`, `note` and `revisions` are
            left out when they are empty.
        """
        d = self.model_dump()
        for key in ("labelled_by", "labelled_at", "note"):
            if d[key] is None:
                del d[key]
        if not d["revisions"]:
            del d["revisions"]
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
    """A read-only snapshot of gold rows, as they were when it was taken.

    It does not follow later changes to the gold file (a `Sample` does). Get one from
    `Gold.pending`, `Gold.all`, `Gold.orphaned`, `Gold.remove` or `Gold.import_rows`.

    Attributes:
        rows: The `GoldRow`s.
        name: What the snapshot holds, such as "all" or "pending".
        path: The gold file the rows came from, or None.
    """

    rows: list[GoldRow]
    name: str = "all"
    path: Path | None = None  # the gold file a view of `Gold` came from

    def __len__(self) -> int:
        """Return the number of rows, labelled and pending."""
        return len(self.rows)

    def counts(self, taxonomy: Taxonomy) -> dict[str, int]:
        """Count how many rows carry each label.

        `off_topic` is included, and a row with several labels is counted once for each. Pending
        rows count for nothing.

        Args:
            taxonomy: The labels to count; labels not in it are ignored.

        Returns:
            dict[str, int]: Each label in the taxonomy, with its row count.
        """
        counts = dict.fromkeys(taxonomy.names, 0)
        for r in self.rows:
            for label in r.labels or []:
                if label in counts:
                    counts[label] += 1
        return counts

    def to_polars(self):
        """Return the rows as a polars DataFrame.

        Returns:
            polars.DataFrame: One row per gold row.
        """
        return _frame.to_polars([r.model_dump() for r in self.rows])

    def to_pandas(self):
        """Return the rows as a pandas DataFrame.

        Returns:
            pandas.DataFrame: One row per gold row.
        """
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
    """A live, read-only view of one named sample of a gold dataset, or of several joined with `+`.

    It reads the gold file every time it is used, so it never shows stale rows, and it cannot
    change a label: people label in the labelling page (`goldlabel.label`). Get one from
    `Gold.draw_sample` or `gold["name"]`.

    Attributes:
        gold: The `Gold` dataset it reads.
        names: The sample names it covers (more than one after `+`).
        drawn: How many rows `Gold.draw_sample` added when it made this view (0 if none).
    """

    def __init__(self, gold: "Gold", names: tuple[str, ...], drawn: int = 0):
        self.gold, self.names, self.drawn = gold, names, drawn

    @property
    def path(self) -> Path:
        """The gold file this sample is read from."""
        return self.gold.path

    @property
    def rows(self) -> list[GoldRow]:
        """The rows of this sample as they are in the file now, labelled and pending."""
        return [r for r in self.gold._read() if r.sample in self.names]

    def _set(self) -> GoldSet:
        return GoldSet(self.rows, " + ".join(self.names), self.path)

    def __len__(self) -> int:
        """Return the number of rows in the sample now, labelled and pending."""
        return len(self.rows)

    def counts(self, taxonomy: Taxonomy) -> dict[str, int]:
        """Count how many rows of the sample carry each label.

        Args:
            taxonomy: The labels to count; `off_topic` is included.

        Returns:
            dict[str, int]: Each label in the taxonomy, with its row count (a row with several
            labels counts once for each; pending rows count for nothing).
        """
        return self._set().counts(taxonomy)

    def to_polars(self):
        """Return the rows as a polars DataFrame.

        Returns:
            polars.DataFrame: One row per gold row.
        """
        return self._set().to_polars()

    def to_pandas(self):
        """Return the rows as a pandas DataFrame.

        Returns:
            pandas.DataFrame: One row per gold row.
        """
        return self._set().to_pandas()

    def __add__(self, other):
        """Join two samples of the same gold dataset into one view (`dev + test`).

        This is how a test sample that has been used up is added to the samples you tune on.
        Nothing is written; no row is copied or moved.

        Args:
            other: Another `Sample` of the same gold file.

        Returns:
            Sample: A view of the rows of both.

        Raises:
            GoldError: `other` is a sample of a different gold file.
        """
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
    """A gold dataset: one file in the storage folder, holding named samples of rows to label.

    The file is `gold.json` or, with a `name`, `gold-<name>.json`, in the storage folder
    (`goldlabel.settings.root`). Rows are drawn from your candidates with `draw_sample` and are
    labelled only by people, in the labelling page (`goldlabel.label`); this class has no way to
    set a label (see `GOLD_RULE_SHORT`). Every property and `Sample` reads the file again, so
    nothing shows stale rows.

    Args:
        candidates: The `Candidates` to draw rows from; None to open an existing file only.
        name: A name for the dataset (lowercase letters, digits, `-` and `_`), so one folder can
            hold several; None for the default file.
        sample_size: How many rows `draw_sample` makes a sample hold when not told (default 50).

    Attributes:
        candidates: The candidates rows are drawn from.
        name: The dataset's name, or None.
        sample_size: The default sample size.
        path: The gold file.

    Raises:
        GoldError: `name` has characters outside the allowed ones, or `sample_size` is not a
            whole number of at least 1.
    """

    def __init__(self, candidates=None, *, name=None, sample_size=50):
        if name is not None:
            _check_name(name, "dataset")
        self.candidates, self.name = candidates, name
        self.sample_size = _check_size(sample_size, "sample_size")
        self.path = resolve(None, "gold.json" if name is None else f"gold-{name}.json")

    @property
    def label(self) -> str:
        """The dataset's display name: its `name`, or "default" for the unnamed one.

        This is a name for messages and page titles; it does not label anything.
        """
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

    def _doc(self) -> dict:
        """Read the gold file.

        Returns:
            dict: `{"taxonomy": dict | None, "rows": [raw rows]}`; empty when the file does not exist.

        Raises:
            GoldError: The file is not JSON, or is not an object with a `rows` list.
        """
        if not self.path.exists():
            return {"taxonomy": None, "rows": []}
        try:
            doc = json.loads(self.path.read_text())
        except json.JSONDecodeError as e:
            raise GoldError(f"{self.path}: not a gold file ({e})") from e
        if not isinstance(doc, dict) or not isinstance(doc.get("rows"), list):
            raise GoldError(
                f"{self.path}: not a gold file (expected an object with a 'rows' list)"
            )
        return doc

    def _read(self) -> list[GoldRow]:
        rows = []
        for n, raw in enumerate(self._doc()["rows"], 1):
            try:
                rows.append(GoldRow.model_validate(raw))
            except ValidationError as e:
                raise GoldError(f"{self.path}: row {n}: not a gold row ({e})") from e
        return rows

    def _write(self, rows: list[GoldRow], taxonomy=_KEEP) -> None:
        # shortcut: the whole file is rewritten on every save, fine for hundreds of rows, switch to
        # appending changes when a gold set reaches tens of thousands
        if taxonomy is _KEEP:
            taxonomy = self._doc().get("taxonomy")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + ".tmp")
        try:
            tmp.write_text(
                json.dumps(
                    {"taxonomy": taxonomy, "rows": [r.dump() for r in rows]}, indent=2
                )
            )
            os.replace(tmp, self.path)
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise

    def _removed(self) -> Path:
        return self.path.with_suffix(".removed.jsonl")

    @property
    def pending(self) -> GoldSet:
        """The rows in the file that nobody has labelled yet, in every sample.

        Returns:
            GoldSet: A snapshot taken now; for one sample use `gold[name]`.
        """
        return GoldSet([r for r in self._read() if not r.labels], "pending", self.path)

    @property
    def all(self) -> GoldSet:
        """Every row in the file, labelled and pending, in every sample.

        Returns:
            GoldSet: A snapshot taken now; for one sample use `gold[name]`.
        """
        return GoldSet(self._read(), "all", self.path)

    def __getitem__(self, name: str) -> Sample:
        """Get the sample called `name` (`gold["dev"]`) as a live, read-only view.

        Args:
            name: The sample's name.

        Returns:
            Sample: A view of that sample's rows.

        Raises:
            KeyError: The file has no sample of that name; the message lists the ones it has.
        """
        names = list(self._samples(self._read()))
        if name not in names:
            raise KeyError(
                f"no sample {name!r} in {self.path}; samples: {', '.join(names) or 'none'}"
            )
        return Sample(self, (name,))

    def draw_sample(self, name: str, n: int | None = None) -> Sample:
        """Top a sample up to `n` rows, drawing new pending rows from the candidates.

        Only the shortfall is drawn, in an order fixed by each candidate's id and this dataset's
        name, so there is no random seed and rerunning draws nothing once the sample is full.
        Rows are added to the gold file as pending, for a person to label; existing rows are
        never removed, and an id that is already in the file, or was removed from it, is never
        drawn again.

        Args:
            name: The sample's name, such as "dev" or "test" (lowercase letters, digits, `-`, `_`).
            n: How many rows the sample should hold; None uses `sample_size`.

        Returns:
            Sample: A live view of the sample (its `drawn` says how many rows were added now).

        Raises:
            GoldError: `name` or `n` is invalid, rows are needed but this `Gold` was made
                without candidates, or too few candidates are left to draw from.
        """
        _check_name(name)
        n = self.sample_size if n is None else _check_size(n, "n")
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
        """Bring in rows that people have already labelled, unchanged, into a sample.

        Only for labels that people wrote; never labels from a model or written by code (see
        `GOLD_RULE_SHORT`). The rows are added to the gold file and stamped "imported". Labels
        are not checked against a taxonomy here; `evaluate` does that.

        Args:
            rows: Dicts with `id`, `text` and a non-empty `labels` list (any other keys are kept).
            name: The sample to add them to (lowercase letters, digits, `-`, `_`).

        Returns:
            GoldSet: The rows that were added.

        Raises:
            GoldError: `name` is invalid, a row lacks `id`, `text` or labels, or an id is
                already in the file.
        """
        _check_name(name)
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
        """Find labelled rows that use a label the taxonomy no longer has.

        Useful after renaming or removing a label: `evaluate` refuses such rows.

        Args:
            taxonomy: The current taxonomy.

        Returns:
            GoldSet: A snapshot of those rows.
        """
        names = set(taxonomy.names)
        return GoldSet(
            [r for r in self._read() if r.labels and not set(r.labels) <= names],
            "orphaned",
        )

    def remove(self, ids) -> GoldSet:
        """Take rows out of the gold file by id, keeping a copy of them.

        The rows are appended to `<gold file>.removed.jsonl` and the gold file is rewritten
        without them. A removed id is never drawn again.

        Args:
            ids: The ids to remove, as a list (not a single string).

        Returns:
            GoldSet: The rows that were removed.

        Raises:
            GoldTypeError: `ids` is a single string.
            GoldError: An id is not in the file; nothing is removed.
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
