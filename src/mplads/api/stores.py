"""On-disk stores for the two things that do not fit in a small container's memory.

The API holds its artifacts in memory because 210k rows is nothing — but two of them are
not nothing:

* **case files** — 37,705 nested records, 83 MB as JSON and roughly 400 MB as Python
  dictionaries, of which a request reads exactly one;
* **near-duplicate pairs** — 223,407 rows, 248 MB in pandas, of which the screen shows
  fifty and the rest of the product never looks at.

Together they were most of a 900 MB process, which is why the site could only run on a
host with a gigabyte to spare. Both are now read from disk per request: SQLite for the
case files (a primary-key lookup, sub-millisecond) and parquet for the pairs (a filtered
scan, tens of milliseconds). Everything else — the worklist, the stats, the plan — stays
in memory, because those are read in full on every page.

The trade is deliberate and small: a case file costs one indexed row read instead of a
dictionary lookup, and the Possible Duplicates page reads a page of parquet instead of
slicing a frame it already held.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterator

import pandas as pd

LOGGER = logging.getLogger(__name__)

#: Recently-opened case files, so a reader paging through one work's tabs does not pay for
#: the same row twice. Small on purpose: the point of this module is to not hold 37,705.
CASE_CACHE = 512


class CaseStore:
    """The case files, keyed by work reference, read from SQLite on demand.

    Presents the mapping interface the rest of the code already used (`.get`, `in`, `len`),
    so call sites did not have to change. `bands()` answers from the indexed column rather
    than deserialising every record, which is what the calibration screen needs.
    """

    def __init__(self, artifacts: Path):
        self._json = artifacts / "case_files.json"
        self._db = artifacts / "case_files.sqlite"
        self._conn: sqlite3.Connection | None = None
        self._count: int | None = None

    # ------------------------------------------------------------------ building
    def _fresh(self) -> bool:
        """True when the database exists and is not older than the JSON it came from."""
        if not self._db.exists():
            return False
        if not self._json.exists():
            return True
        return self._db.stat().st_mtime >= self._json.stat().st_mtime

    def _build(self) -> None:
        """Convert case_files.json into SQLite, one record at a time.

        Streamed with `raw_decode` rather than `json.load` because the point is to avoid
        ever holding all 37,705 records at once — on a 512 MB host, doing that during
        start-up is exactly the failure this module exists to prevent.
        """
        if not self._json.exists():
            LOGGER.warning("no case_files.json at %s — case lookups will return nothing",
                           self._json)
            return
        LOGGER.info("building the case store from %s", self._json.name)
        self._db.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._db.with_suffix(".building")
        tmp.unlink(missing_ok=True)
        conn = sqlite3.connect(tmp)
        conn.execute("CREATE TABLE case_file (work_ref TEXT PRIMARY KEY, band TEXT, "
                     "payload TEXT NOT NULL)")
        decoder = json.JSONDecoder()
        text = self._json.read_text(encoding="utf-8")
        index = text.index("[") + 1
        rows, total = [], 0
        while True:
            while index < len(text) and text[index] in " \t\r\n,":
                index += 1
            if index >= len(text) or text[index] == "]":
                break
            case, index = decoder.raw_decode(text, index)
            rows.append((case["work_ref"], case.get("confidence_band"),
                         json.dumps(case, separators=(",", ":"))))
            if len(rows) >= 2000:
                conn.executemany("INSERT OR REPLACE INTO case_file VALUES (?,?,?)", rows)
                total += len(rows)
                rows.clear()
        if rows:
            conn.executemany("INSERT OR REPLACE INTO case_file VALUES (?,?,?)", rows)
            total += len(rows)
        conn.commit()
        conn.close()
        tmp.replace(self._db)
        LOGGER.info("case store built: %s records", f"{total:,}")

    def _connection(self) -> sqlite3.Connection:
        if self._conn is None:
            if not self._fresh():
                self._build()
            # check_same_thread=False: uvicorn serves from a thread pool and this connection
            # is only ever read from, so SQLite's own locking is enough.
            self._conn = sqlite3.connect(self._db, check_same_thread=False)
        return self._conn

    # ------------------------------------------------------------------ reading
    @lru_cache(maxsize=CASE_CACHE)
    def _fetch(self, work_ref: str) -> str | None:
        row = self._connection().execute(
            "SELECT payload FROM case_file WHERE work_ref = ?", (work_ref,)).fetchone()
        return row[0] if row else None

    def get(self, work_ref: str, default: Any = None) -> Any:
        payload = self._fetch(work_ref)
        return json.loads(payload) if payload else default

    def __getitem__(self, work_ref: str) -> dict:
        found = self.get(work_ref)
        if found is None:
            raise KeyError(work_ref)
        return found

    def __contains__(self, work_ref: object) -> bool:
        return isinstance(work_ref, str) and self._fetch(work_ref) is not None

    def __len__(self) -> int:
        if self._count is None:
            self._count = int(self._connection().execute(
                "SELECT COUNT(*) FROM case_file").fetchone()[0])
        return self._count

    def bands(self) -> dict[str, str]:
        """work_ref -> confidence band, without deserialising a single case file."""
        return {ref: band for ref, band in self._connection().execute(
            "SELECT work_ref, band FROM case_file")}

    def values(self) -> Iterator[dict]:
        """Every case file, one at a time. Nothing holds them all."""
        for (payload,) in self._connection().execute("SELECT payload FROM case_file"):
            yield json.loads(payload)


class DuplicateStore:
    """Near-duplicate pairs, read from parquet per question instead of held in a frame.

    Three questions are ever asked of it: which pairs are administratively concerning (the
    screen's default), a page of pairs with optional filters, and which pairs sit inside
    one agency (the dossier). Each is a filtered read; none needs all 223,407 rows in
    memory, and the concerning subset — the only one asked for repeatedly — is cached with
    just the columns the screen shows.
    """

    #: What the Possible Duplicates screen and the dossier actually display.
    COLUMNS = ["work_ref_a", "work_ref_b", "similarity", "classification", "state_name",
               "description_a", "description_b", "amount_a", "amount_b",
               "same_implementing_agency", "implementing_agency"]

    def __init__(self, path: Path):
        self._path = path
        self._concerning: pd.DataFrame | None = None
        self._rows: int | None = None

    def _columns(self) -> list[str]:
        import pyarrow.parquet as pq

        available = set(pq.ParquetFile(self._path).schema.names)
        return [c for c in self.COLUMNS if c in available] or list(available)

    @property
    def empty(self) -> bool:
        return not self._path.exists() or self.rows == 0

    @property
    def rows(self) -> int:
        if self._rows is None:
            if not self._path.exists():
                self._rows = 0
            else:
                import pyarrow.parquet as pq
                self._rows = int(pq.ParquetFile(self._path).metadata.num_rows)
        return self._rows

    def __len__(self) -> int:
        return self.rows

    def concerning(self) -> pd.DataFrame:
        """The pairs worth a human's attention, cached. Around a fifth of the file.

        Read in batches with the two cheap conditions pushed into the scan, because the
        obvious version — load all 223,407 rows and filter in pandas — costs 250 MB at the
        moment it runs, and that peak is what a 512 MB host dies on. The amount test is a
        ratio, so it is applied per batch afterwards, on rows the scan has already thinned.
        """
        if self._concerning is None:
            if self.empty:
                self._concerning = pd.DataFrame()
                return self._concerning
            import pyarrow.compute as pc
            import pyarrow.dataset as ds

            from mplads.intelligence import duplicates as dup_mod

            dataset = ds.dataset(self._path, format="parquet")
            scanner = dataset.scanner(
                columns=self._columns(),
                filter=(pc.field("similarity") >= dup_mod.NEAR_EXACT)
                & (pc.field("same_implementing_agency") == True),  # noqa: E712 - arrow
                batch_size=10_000,
                # Arrow reads ahead on several threads by default, which is the right trade
                # on a machine with memory to spare and the wrong one here: the read-ahead
                # buffers alone were 150 MB. One batch at a time costs about a second more
                # and is the difference between fitting on a small host and not.
                use_threads=False,
                batch_readahead=1,
                fragment_readahead=1,
            )
            kept = [dup_mod.concerning(batch.to_pandas()) for batch in scanner.to_batches()]
            kept = [frame for frame in kept if not frame.empty]
            self._concerning = (pd.concat(kept, ignore_index=True) if kept
                                else pd.DataFrame(columns=self._columns()))
        return self._concerning

    def page(self, offset: int, limit: int, state: str | None = None,
             classification: str | None = None) -> tuple[int, pd.DataFrame]:
        """A slice of *all* pairs, filtered, without materialising the rest."""
        if self.empty:
            return 0, pd.DataFrame()
        import pyarrow.compute as pc
        import pyarrow.dataset as ds

        dataset = ds.dataset(self._path, format="parquet")
        condition = None
        if state:
            condition = pc.field("state_name") == state
        if classification:
            clause = pc.field("classification") == classification
            condition = clause if condition is None else condition & clause
        scanner = dataset.scanner(columns=self._columns(), filter=condition,
                                  use_threads=False, batch_readahead=1, fragment_readahead=1)
        table = scanner.head(offset + limit)
        total = dataset.count_rows(filter=condition)
        return total, table.slice(offset, limit).to_pandas()

    def for_refs(self, refs: set[str]) -> pd.DataFrame:
        """Pairs where both works belong to the given set — the dossier's question."""
        if self.empty or not refs:
            return pd.DataFrame()
        import pyarrow.compute as pc
        import pyarrow.dataset as ds

        wanted = pa_array(refs)
        dataset = ds.dataset(self._path, format="parquet")
        condition = (pc.is_in(pc.field("work_ref_a"), value_set=wanted)
                     & pc.is_in(pc.field("work_ref_b"), value_set=wanted))
        return dataset.scanner(columns=self._columns(), filter=condition, use_threads=False,
                               batch_readahead=1, fragment_readahead=1).to_table().to_pandas()


def pa_array(values: set[str]):
    import pyarrow as pa

    return pa.array(sorted(values), type=pa.string())
