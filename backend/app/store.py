"""In-memory session store for imported files and the latest research run.

Nothing is written to disk. Everything held here is lost when the process
stops: a local restart, a Render redeploy, or a free-tier spin-down.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from enum import StrEnum

from app.ingestion.models import ImportResult, RejectedRow
from app.ingestion.package import PackageImport


class DataKind(StrEnum):
    EMPTY = "empty"
    # Uploaded by a user. Official MCX provenance is not verified by the app.
    USER_UPLOADED = "user_uploaded"
    SYNTHETIC = "synthetic"


class StoreError(ValueError):
    """Upload refused; the message is safe to show to the user."""


@dataclass(slots=True)
class SessionStore:
    imports: list[ImportResult] = field(default_factory=list)
    # Package tables (A1, A2, B1, B2) with every column, kept apart from the research
    # observations: annual aggregates and option premiums never enter a price series.
    package: list[PackageImport] = field(default_factory=list)
    research: dict | None = None
    _lock: threading.Lock = field(default_factory=threading.Lock)

    @property
    def kind(self) -> DataKind:
        if not self.imports:
            return DataKind.EMPTY
        return DataKind.SYNTHETIC if self.imports[0].report.synthetic else DataKind.USER_UPLOADED

    @property
    def total_bytes(self) -> int:
        # A B1 file is counted once although it feeds both stores.
        shas = {r.report.source_sha256: r.report.size_bytes for r in self.imports}
        shas.update({p.source_sha256: p.size_bytes for p in self.package})
        return sum(shas.values())

    def _file_count(self) -> int:
        return len({r.report.source_sha256 for r in self.imports} | {p.source_sha256 for p in self.package})

    def _synthetic_flags(self) -> set[bool]:
        return {r.report.synthetic for r in self.imports} | {p.synthetic for p in self.package}

    def add(self, result: ImportResult, *, max_files: int, max_total_bytes: int) -> None:
        with self._lock:
            report = result.report
            if any(r.report.source_sha256 == report.source_sha256 for r in self.imports):
                raise StoreError(f"{report.source_file} has already been imported (identical content).")
            if self._synthetic_flags() - {report.synthetic}:
                raise StoreError(
                    "Synthetic and user-uploaded files cannot be combined. "
                    "Clear the session before switching."
                )
            if self._file_count() >= max_files:
                raise StoreError(f"Session already holds the maximum of {max_files} files.")
            if self.total_bytes + report.size_bytes > max_total_bytes:
                raise StoreError(f"Session size limit of {max_total_bytes} bytes would be exceeded.")
            self.imports.append(result)
            self.research = None  # earlier results no longer match the data

    def add_package(self, table: PackageImport, *, max_files: int, max_total_bytes: int, counted: bool = True) -> None:
        """Store one package table.

        A file is refused if the same content is already stored (re-importing is
        idempotent, never duplicating). A row whose key is already held from another
        file is dropped when identical and rejected with a reason when it differs.
        ``counted=False`` when the same bytes were just stored as research
        observations (a B1 file), so the file is not counted twice.
        """
        with self._lock:
            if any(p.source_sha256 == table.source_sha256 for p in self.package):
                raise StoreError(f"{table.source_file} has already been imported (identical content).")
            if self._synthetic_flags() - {table.synthetic}:
                raise StoreError(
                    "Synthetic and user-uploaded files cannot be combined. Clear the session before switching."
                )
            if counted and self._file_count() >= max_files:
                raise StoreError(f"Session already holds the maximum of {max_files} files.")
            if counted and self.total_bytes + table.size_bytes > max_total_bytes:
                raise StoreError(f"Session size limit of {max_total_bytes} bytes would be exceeded.")

            held = {
                p.key_of(row): (p.source_file, row)
                for p in self.package if p.table.id == table.table.id for row in p.rows
            }
            kept = []
            for row in table.rows:
                previous = held.get(table.key_of(row))
                if previous is None:
                    kept.append(row)
                elif _same(table, previous[1], row):
                    table.cross_file_duplicates += 1
                else:
                    table.rejected.append(RejectedRow(
                        row["line_number"],
                        (f"Conflicts with {previous[0]} line {previous[1]['line_number']} for the same key",),
                        {c.name: str(row[c.name]) for c in table.table.columns},
                    ))
            table.rows = kept
            table.rejected.sort(key=lambda r: r.line_number)
            self.package.append(table)

    def package_snapshot(self) -> list[PackageImport]:
        with self._lock:
            return list(self.package)

    def clear(self) -> None:
        with self._lock:
            self.imports.clear()
            self.package.clear()
            self.research = None

    def save_research(self, research: dict, analysed: list[ImportResult]) -> bool:
        """Keep a research result only if the session still holds exactly the files it analysed.

        The comparison and the write happen under one lock, so an upload or clear that lands
        while research is computing can never leave a result describing the old data.
        """
        with self._lock:
            if [r.report.source_sha256 for r in self.imports] != [r.report.source_sha256 for r in analysed]:
                return False
            self.research = research
            return True

    def snapshot(self) -> list[ImportResult]:
        with self._lock:
            return list(self.imports)


def _same(table: PackageImport, a: dict, b: dict) -> bool:
    return all(a[c.name] == b[c.name] for c in table.table.columns)
