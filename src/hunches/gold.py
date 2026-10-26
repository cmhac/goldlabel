import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationError

from hunches.settings import resolve
from hunches.taxonomy import Taxonomy

SPLITS = ("dev", "test")


class GoldRow(BaseModel):
    """One gold item. `labels` is `None` while pending (`[]` in pre-006 files means the same)."""

    model_config = ConfigDict(extra="allow")  # a hand-edited file keeps its other keys

    id: str
    text: str
    labels: list[str] | None
    split: Literal["dev", "test"]
    labelled_by: str | None = None  # "hunches-ui", "imported" or absent
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

    def __repr__(self) -> str:
        labelled = [r for r in self.rows if r.labels]
        sources = {"hunches-ui": 0, "imported": 0, "unstamped": 0}
        for r in labelled:
            key = r.labelled_by if r.labelled_by in sources else "unstamped"
            sources[key] += 1
        by = ", ".join(f"{k} {v}" for k, v in sources.items())
        return (
            f"GoldSet {self.name}: {len(self.rows)} rows "
            f"({len(labelled)} labelled, {len(self.rows) - len(labelled)} pending); {by}"
        )


class Gold:
    """The gold file. Every property reads the file again, so it never shows stale rows."""

    def __init__(self, path=None):
        self.path = resolve(path, "gold.jsonl")

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
                raise ValueError(f"{self.path}:{n}: not a gold row ({e})") from e
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
            [r for r in self._read() if r.labels and r.split == "dev"], "dev"
        )

    @property
    def test(self) -> GoldSet:
        return GoldSet(
            [r for r in self._read() if r.labels and r.split == "test"], "test"
        )

    @property
    def pending(self) -> GoldSet:
        return GoldSet([r for r in self._read() if not r.labels], "pending")

    @property
    def all(self) -> GoldSet:
        return GoldSet(self._read(), "all")

    def draw(self, candidates, n: int = 50, split: str = "dev", seed=None) -> GoldSet:
        """Append `n` pending rows (`labels=None`) not already anywhere in the file."""
        if split not in SPLITS:
            raise ValueError(f"split must be 'dev' or 'test', not {split!r}")
        rows = self._read()
        picked = candidates.sample(n, seed, exclude={r.id for r in rows}).rows
        if len(picked) < n:
            raise ValueError(
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
            raise ValueError(f"split must be 'dev' or 'test', not {split!r}")
        existing = self._read()
        seen = {r.id for r in existing}
        now = datetime.now(UTC).isoformat()
        new = []
        for r in rows:
            missing = [k for k in ("id", "text", "labels") if k not in r]
            if missing or not r["labels"]:
                raise ValueError(
                    f"imported row {r.get('id')!r} needs id, text and labels"
                )
            row = GoldRow.model_validate(
                {**r, "split": split, "labelled_by": "imported", "labelled_at": now}
            )
            if row.id in seen:
                raise ValueError(f"id {row.id!r} is already in {self.path}")
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
            raise TypeError("ids must be a list of ids, not a string")
        ids = {str(i) for i in ids}
        rows = self._read()
        unknown = ids - {r.id for r in rows}
        if unknown:
            raise ValueError(f"not in {self.path}: {sorted(unknown)}")
        gone = [r for r in rows if r.id in ids]
        if gone:
            removed = self.path.with_suffix(".removed.jsonl")
            with removed.open("a") as f:
                f.write("".join(json.dumps(r.dump()) + "\n" for r in gone))
            self._write([r for r in rows if r.id not in ids])
        return GoldSet(gone, "removed")
