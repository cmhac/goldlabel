import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationError

from goldlabel import _frame, _html
from goldlabel._gold_rule import GOLD_RULE_SHORT, GoldError, GoldTypeError
from goldlabel.settings import resolve
from goldlabel.taxonomy import Taxonomy

SPLITS = ("dev", "test")


class GoldRow(BaseModel):
    """One gold item. `labels` is `None` while pending (`[]` in pre-006 files means the same)."""

    model_config = ConfigDict(extra="allow")  # a hand-edited file keeps its other keys

    id: str
    text: str
    labels: list[str] | None
    split: Literal["dev", "test"]
    labelled_by: str | None = None  # "goldlabel-ui", "imported" or absent
    labelled_at: str | None = None

    def dump(self) -> dict:
        d = self.model_dump()
        for key in ("labelled_by", "labelled_at"):
            if d[key] is None:
                del d[key]
        return d


@dataclass(frozen=True)
class GoldSet:
    """A read-only view of gold rows."""

    rows: list[GoldRow]
    name: str = "all"
    path: Path | None = (
        None  # the gold file a view of `Gold` came from (the evaluation log records it)
    )

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
        labelled = [r for r in self.rows if r.labels]
        sources = {"goldlabel-ui": 0, "imported": 0, "unstamped": 0}
        for r in labelled:
            key = r.labelled_by if r.labelled_by in sources else "unstamped"
            sources[key] += 1
        by = ", ".join(f"{k} {v}" for k, v in sources.items())
        return (
            f"GoldSet {self.name}: {len(self.rows)} rows "
            f"({len(labelled)} labelled, {len(self.rows) - len(labelled)} pending); {by}"
        )

    def _repr_html_(self) -> str:
        rows = [
            (r.id, r.text, r.labels if r.labels else "pending", r.split, r.labelled_by)
            for r in self.rows
        ]
        return _html.line(self._summary()) + _html.table(
            ["id", "text", "labels", "split", "labelled by"], rows
        )

    def __repr__(self) -> str:
        return f"{self._summary()}\n{GOLD_RULE_SHORT}"


class Gold:
    """The gold file. Every property reads the file again, so it never shows stale rows."""

    def __init__(self, path=None):
        self.path = resolve(path, "gold.jsonl")

    def __repr__(self) -> str:
        views = [self.dev, self.test, self.pending]
        sources = GoldSet(self._read())._summary().partition("; ")[2]
        return (
            f"Gold {self.path}: dev {len(views[0])}, test {len(views[1])}, "
            f"pending {len(views[2])}; {sources}\n{GOLD_RULE_SHORT}"
        )

    def _repr_html_(self) -> str:
        rows = []
        for view in (self.dev, self.test, self.pending, self.all):
            labelled = sum(1 for r in view.rows if r.labels)
            rows.append(
                (view.name, len(view.rows), labelled, len(view.rows) - labelled)
            )
        return _html.line(f"Gold: {self.path}") + _html.table(
            ["view", "rows", "labelled", "pending"], rows
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

    @property
    def dev(self) -> GoldSet:
        return GoldSet(
            [r for r in self._read() if r.labels and r.split == "dev"],
            "dev",
            self.path,
        )

    @property
    def test(self) -> GoldSet:
        return GoldSet(
            [r for r in self._read() if r.labels and r.split == "test"],
            "test",
            self.path,
        )

    @property
    def pending(self) -> GoldSet:
        return GoldSet([r for r in self._read() if not r.labels], "pending", self.path)

    @property
    def all(self) -> GoldSet:
        return GoldSet(self._read(), "all", self.path)

    def draw(self, candidates, n: int = 50, split: str = "dev", seed=None) -> GoldSet:
        """Append `n` pending rows (`labels=None`) not already anywhere in the file."""
        if split not in SPLITS:
            raise GoldError(f"split must be 'dev' or 'test', not {split!r}")
        rows = self._read()
        picked = candidates.sample(n, seed, exclude={r.id for r in rows}).rows
        if len(picked) < n:
            raise GoldError(
                f"only {len(picked)} candidates are not already in {self.path}; asked for {n}"
            )
        new = [
            GoldRow(id=str(r["id"]), text=r["text"], labels=None, split=split)
            for r in picked
        ]
        self._write(rows + new)
        return GoldSet(new, "drawn")

    def import_rows(self, rows, split: str) -> GoldSet:
        """Add rows people already labelled (dicts with `id`, `text`, `labels`), stamped `imported`.

        Labels are not checked against a taxonomy here; `evaluate` does that.
        """
        if split not in SPLITS:
            raise GoldError(f"split must be 'dev' or 'test', not {split!r}")
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
                {**r, "split": split, "labelled_by": "imported", "labelled_at": now}
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
        """Move rows to `<gold>.removed.jsonl` (appended) and rewrite the file without them."""
        if isinstance(ids, str):
            raise GoldTypeError("ids must be a list of ids, not a string")
        ids = {str(i) for i in ids}
        rows = self._read()
        unknown = ids - {r.id for r in rows}
        if unknown:
            raise GoldError(f"not in {self.path}: {sorted(unknown)}")
        gone = [r for r in rows if r.id in ids]
        if gone:
            removed = self.path.with_suffix(".removed.jsonl")
            with removed.open("a") as f:
                f.write("".join(json.dumps(r.dump()) + "\n" for r in gone))
            self._write([r for r in rows if r.id not in ids])
        return GoldSet(gone, "removed")
