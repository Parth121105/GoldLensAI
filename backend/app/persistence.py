"""Saves parsed gold rows to disk so imports survive a restart.

One JSON file per imported file, named by the file's SHA-256, holding only what the
importer kept: the accepted gold observations and the import report. The uploaded
bytes themselves are never written. Files are written to a temporary name and then
renamed, so a crash cannot leave a half-written import behind.

Package tables (A1, A2, B2) and research results are not saved; research is
recomputed from the saved observations.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from app.ingestion.models import (
    ContractCoverage,
    ImportReport,
    ImportResult,
    Observation,
    RejectedRow,
    RowProvenance,
)

FORMAT_VERSION = 1

logger = logging.getLogger("goldlensai")


class ImportArchive:
    def __init__(self, directory: Path) -> None:
        self.directory = directory

    def _path(self, sha256: str) -> Path:
        return self.directory / f"{sha256}.json"

    def save(self, result: ImportResult) -> None:
        """Write one import atomically. Raises OSError if the disk write fails."""
        if result.report.synthetic:
            raise ValueError("Synthetic data is never saved to the real-data store.")
        self.directory.mkdir(parents=True, exist_ok=True)
        target = self._path(result.report.source_sha256)
        tmp = target.with_suffix(".json.tmp")
        payload = {"format_version": FORMAT_VERSION, **_result_to_dict(result)}
        tmp.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
        os.replace(tmp, target)

    def load_all(self) -> list[ImportResult]:
        """Every saved import, oldest first. Unreadable files are skipped and logged, never guessed at."""
        if not self.directory.is_dir():
            return []
        results = []
        for path in sorted(self.directory.glob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                if payload.get("format_version") != FORMAT_VERSION:
                    raise ValueError(f"unsupported format_version {payload.get('format_version')!r}")
                result = _result_from_dict(payload)
                if result.report.synthetic:
                    raise ValueError("synthetic data is never reloaded from disk")
                results.append(result)
            except (OSError, ValueError, KeyError, TypeError) as exc:
                logger.warning("Skipping saved import %s: %s", path.name, exc)
        results.sort(key=lambda r: (r.report.imported_at, r.report.source_sha256))
        return results

    def seed_if_empty(self, seed_dir: Path) -> int:
        """Copy saved imports from ``seed_dir`` when this archive holds none. Returns files copied."""
        if not seed_dir.is_dir() or (self.directory.is_dir() and any(self.directory.glob("*.json"))):
            return 0
        self.directory.mkdir(parents=True, exist_ok=True)
        copied = 0
        for path in sorted(seed_dir.glob("*.json")):
            (self.directory / path.name).write_bytes(path.read_bytes())
            copied += 1
        return copied

    def clear(self) -> None:
        if not self.directory.is_dir():
            return
        for path in [*self.directory.glob("*.json"), *self.directory.glob("*.json.tmp")]:
            path.unlink(missing_ok=True)


# --- (de)serialization ------------------------------------------------------------------------
# Decimals are written as strings so no price passes through a float.


def _dec(v: Decimal | None) -> str | None:
    return None if v is None else str(v)


def _undec(v: str | None) -> Decimal | None:
    return None if v is None else Decimal(v)


def _obs_to_dict(o: Observation) -> dict:
    p = o.provenance
    return {
        "trade_date": o.trade_date.isoformat(),
        "symbol": o.symbol,
        "raw_symbol": o.raw_symbol,
        "expiry": o.expiry.isoformat(),
        "open": _dec(o.open),
        "high": _dec(o.high),
        "low": _dec(o.low),
        "close": str(o.close),
        "previous_close": _dec(o.previous_close),
        "settlement": _dec(o.settlement),
        "volume": o.volume,
        "value": _dec(o.value),
        "open_interest": o.open_interest,
        "traded": o.traded,
        "provenance": [p.source_file, p.source_sha256, p.line_number, p.layout_id],
        "warnings": list(o.warnings),
    }


def _obs_from_dict(d: dict) -> Observation:
    source_file, sha, line, layout = d["provenance"]
    return Observation(
        trade_date=date.fromisoformat(d["trade_date"]),
        symbol=d["symbol"],
        raw_symbol=d["raw_symbol"],
        expiry=date.fromisoformat(d["expiry"]),
        open=_undec(d["open"]),
        high=_undec(d["high"]),
        low=_undec(d["low"]),
        close=Decimal(d["close"]),
        previous_close=_undec(d["previous_close"]),
        settlement=_undec(d["settlement"]),
        volume=d["volume"],
        value=_undec(d["value"]),
        open_interest=d["open_interest"],
        traded=d["traded"],
        provenance=RowProvenance(source_file, sha, line, layout),
        warnings=tuple(d["warnings"]),
    )


def _result_to_dict(result: ImportResult) -> dict:
    r = result.report
    return {
        "report": {
            "source_file": r.source_file,
            "source_sha256": r.source_sha256,
            "size_bytes": r.size_bytes,
            "imported_at": r.imported_at.isoformat(),
            "layout_id": r.layout_id,
            "layout_verified_against_real_file": r.layout_verified_against_real_file,
            "units": r.units,
            "date_order": r.date_order,
            "synthetic": r.synthetic,
            "rows_read": r.rows_read,
            "accepted": r.accepted,
            "exact_duplicates_dropped": r.exact_duplicates_dropped,
            "rejected": [{"line_number": x.line_number, "reasons": list(x.reasons), "raw": x.raw} for x in r.rejected],
            "skipped": r.skipped,
            "trade_dates": [d.isoformat() for d in r.trade_dates],
            "coverage": [
                {
                    "contract_id": c.contract_id,
                    "symbol": c.symbol,
                    "expiry": c.expiry.isoformat(),
                    "first_trade_date": c.first_trade_date.isoformat(),
                    "last_trade_date": c.last_trade_date.isoformat(),
                    "observations": c.observations,
                    "traded_observations": c.traded_observations,
                    "spec_status": c.spec_status,
                    "spec_version_id": c.spec_version_id,
                }
                for c in r.coverage
            ],
            "warnings": r.warnings,
        },
        "observations": [_obs_to_dict(o) for o in result.observations],
    }


def _result_from_dict(d: dict) -> ImportResult:
    r = d["report"]
    report = ImportReport(
        source_file=r["source_file"],
        source_sha256=r["source_sha256"],
        size_bytes=r["size_bytes"],
        imported_at=datetime.fromisoformat(r["imported_at"]),
        layout_id=r["layout_id"],
        layout_verified_against_real_file=r["layout_verified_against_real_file"],
        units=r["units"],
        date_order=r["date_order"],
        synthetic=r["synthetic"],
        rows_read=r["rows_read"],
        accepted=r["accepted"],
        exact_duplicates_dropped=r["exact_duplicates_dropped"],
        rejected=[RejectedRow(x["line_number"], tuple(x["reasons"]), x["raw"]) for x in r["rejected"]],
        skipped=r["skipped"],
        trade_dates=[date.fromisoformat(x) for x in r["trade_dates"]],
        coverage=[
            ContractCoverage(
                contract_id=c["contract_id"],
                symbol=c["symbol"],
                expiry=date.fromisoformat(c["expiry"]),
                first_trade_date=date.fromisoformat(c["first_trade_date"]),
                last_trade_date=date.fromisoformat(c["last_trade_date"]),
                observations=c["observations"],
                traded_observations=c["traded_observations"],
                spec_status=c["spec_status"],
                spec_version_id=c["spec_version_id"],
            )
            for c in r["coverage"]
        ],
        warnings=r["warnings"],
    )
    return ImportResult(observations=[_obs_from_dict(o) for o in d["observations"]], report=report)
