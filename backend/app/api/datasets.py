"""Dataset session: upload CSVs, load the synthetic demo, inspect, clear.

Uploads are sent as the raw request body (Content-Type text/csv) with the
original file name in the ``filename`` query parameter. Files are parsed in
memory by the existing importer; the uploaded bytes are never written to disk.
Only the parsed gold rows are saved (app/persistence.py), when the store has an archive.
"""

from __future__ import annotations

import csv
import functools
import hashlib
from collections import Counter, defaultdict
from pathlib import PurePosixPath

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from starlette.concurrency import run_in_threadpool

from app.api.deps import get_settings, get_store
from app.api.schemas import (
    ContractCoverageOut,
    DatasetStatus,
    ImportReportOut,
    PackageTableOut,
    RejectedRowOut,
    UploadResponse,
)
from app.demo import DEMO_FILENAME, demo_csv_bytes
from app.ingestion import DateOrder, ImportFailedError, ImportResult, import_bhavcopy_bytes
from app.ingestion.models import Observation
from app.ingestion.package import (
    PackageImport,
    PackageImportError,
    TableKind,
    detect_package_table,
    import_package_table,
)
from app.research.engine import merge_observations
from app.settings import Settings
from app.specs import default_registry
from app.store import AlreadyHeldError, SessionStore, StoreError

router = APIRouter(tags=["datasets"])

STORAGE_NOTE = (
    "In server memory only. Lost when the server restarts, redeploys or (on Render's free "
    "tier) spins down after inactivity. Nothing is written to disk."
)
STORAGE_NOTE_SAVED = (
    "Parsed gold rows are saved on the server's disk and reloaded after a restart; uploaded files "
    "themselves are not kept. Package tables and research results stay in memory. On a host "
    "without a persistent disk (Render's free tier) a redeploy still empties the session."
)
MAX_REJECTED_SHOWN = 200
MAX_FILENAME = 200

_WARNING_KINDS = (
    ("No trades", "no trades (zero OHLC treated as missing)"),
    ("Open interest not reported", "open interest not reported"),
    ("Volume not reported", "volume not reported"),
    ("outside the low-high range", "close outside low-high range"),
    ("weekend", "weekend trade date"),
    ("last-trading-day rule", "expiry differs from documented rule"),
)


@router.get("/datasets", response_model=DatasetStatus)
def dataset_status(
    store: SessionStore = Depends(get_store), settings: Settings = Depends(get_settings)
) -> DatasetStatus:
    return build_status(store, settings)


@router.post("/datasets", response_model=UploadResponse)
async def upload_dataset(
    request: Request,
    filename: str = Query(min_length=1, max_length=255),
    date_order: DateOrder | None = Query(default=None),
    store: SessionStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
) -> UploadResponse:
    name = _safe_filename(filename)
    data = await _read_limited(request, settings.max_upload_bytes)
    if not data.strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=f"{name} is empty.")
    if _is_package_table(data):
        return await run_in_threadpool(_store_package, data, name, store, settings)
    result = await run_in_threadpool(_import, data, name, date_order)
    return _store(result, store, settings)


@router.post("/datasets/demo", response_model=UploadResponse)
async def load_demo(
    store: SessionStore = Depends(get_store), settings: Settings = Depends(get_settings)
) -> UploadResponse:
    result = await run_in_threadpool(_import, demo_csv_bytes(), DEMO_FILENAME, None)
    return _store(result, store, settings)


@router.delete("/datasets", response_model=DatasetStatus)
def clear_datasets(
    store: SessionStore = Depends(get_store), settings: Settings = Depends(get_settings)
) -> DatasetStatus:
    store.clear()
    return build_status(store, settings)


# --- helpers --------------------------------------------------------------------------


def build_status(store: SessionStore, settings: Settings) -> DatasetStatus:
    imports = store.snapshot()
    observations, conflicts = merge_observations(imports)
    dates = sorted({o.trade_date for o in observations})
    return DatasetStatus(
        kind=store.kind.value,
        storage=STORAGE_NOTE_SAVED if store.persistent else STORAGE_NOTE,
        files=[report_out(r, _provenance(r)) for r in imports],
        observations=len(observations),
        trade_date_from=dates[0] if dates else None,
        trade_date_to=dates[-1] if dates else None,
        contracts=_contracts(observations),
        cross_file_conflicts=conflicts,
        limits={
            "max_upload_bytes": settings.max_upload_bytes,
            "max_files": settings.max_files,
            "max_total_bytes": settings.max_total_bytes,
        },
        package=[package_out(p) for p in store.package_snapshot()],
    )


def package_out(p: PackageImport) -> PackageTableOut:
    return PackageTableOut(
        table_id=p.table.id,
        kind=p.table.kind.value,
        title=p.table.title,
        source_file=p.source_file,
        source_sha256=p.source_sha256,
        size_bytes=p.size_bytes,
        imported_at=p.imported_at,
        synthetic=p.synthetic,
        provenance=(
            "File name starts with SYNTHETIC_: treated as synthetic test data, not market data."
            if p.synthetic
            else "Uploaded by a user. GoldLensAI has not verified that this file came from MCX."
        ),
        rows_read=p.rows_read,
        accepted=p.accepted,
        rejected_count=len(p.rejected),
        rejected=[RejectedRowOut(line_number=x.line_number, reasons=list(x.reasons))
                  for x in p.rejected[:MAX_REJECTED_SHOWN]],
        exact_duplicates_dropped=p.exact_duplicates_dropped,
        cross_file_duplicates=p.cross_file_duplicates,
        row_warnings=dict(sorted(p.row_warnings.items())),
        table_warnings=list(p.warnings),
        missing_values=p.missing_values,
        numeric_ranges={k: list(v) for k, v in p.numeric_ranges.items()},
        coverage=p.coverage,
    )


def _is_package_table(data: bytes) -> bool:
    """A package table is recognised by its exact header row, not by its file name."""
    head = data[:4096].decode("utf-8-sig", errors="replace").splitlines()
    return bool(head) and detect_package_table(next(csv.reader([head[0]]), [])) is not None


def _store_package(data: bytes, name: str, store: SessionStore, settings: Settings) -> UploadResponse:
    try:
        table = import_package_table(data, source_name=name)
    except PackageImportError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc

    report = None
    research_rows = 0
    if table.table.kind is TableKind.FUTURES:
        # Futures rows also go through the Bhavcopy importer, which feeds research with its
        # own validation and specification checks (GOLD 1 kg, for example, is out of scope).
        result = _import(data, name, None)
        report = report_out(result, _provenance(result))
        research_rows = result.report.accepted
        if research_rows and table.accepted:
            try:
                store.add(result, max_files=settings.max_files, max_total_bytes=settings.max_total_bytes)
            except AlreadyHeldError:
                research_rows = 0  # its futures rows are already held; the package table is still kept
            except StoreError as exc:
                raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    if table.accepted == 0:
        return UploadResponse(
            stored=False,
            message=f"Table {table.table.id}: no rows were accepted, so nothing was added.",
            report=report,
            package=package_out(table),
        )
    try:
        store.add_package(
            table,
            max_files=settings.max_files,
            max_total_bytes=settings.max_total_bytes,
            counted=not research_rows,
        )
    except StoreError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    message = f"Added table {table.table.id} ({table.table.kind.value}): {table.accepted} rows from {name}."
    if table.table.kind is TableKind.FUTURES:
        message += f" {research_rows} rows of the four researched contracts went to research."
    elif table.table.kind is TableKind.OPTIONS:
        message += " Option premiums are stored separately and never used as futures prices."
    else:
        message += " Year-wise aggregates are reference context only."
    return UploadResponse(stored=True, message=message, report=report, package=package_out(table))


def report_out(result: ImportResult, provenance: str) -> ImportReportOut:
    r = result.report
    kinds: Counter[str] = Counter()
    for obs in result.observations:
        for w in obs.warnings:
            kinds[next((label for key, label in _WARNING_KINDS if key in w), "other")] += 1
    return ImportReportOut(
        source_file=r.source_file,
        source_sha256=r.source_sha256,
        size_bytes=r.size_bytes,
        imported_at=r.imported_at,
        synthetic=r.synthetic,
        provenance=provenance,
        layout_id=r.layout_id,
        layout_verified_against_real_file=r.layout_verified_against_real_file,
        units=r.units,
        date_order=r.date_order,
        rows_read=r.rows_read,
        accepted=r.accepted,
        exact_duplicates_dropped=r.exact_duplicates_dropped,
        rejected_count=len(r.rejected),
        rejected=[RejectedRowOut(line_number=x.line_number, reasons=list(x.reasons))
                  for x in r.rejected[:MAX_REJECTED_SHOWN]],
        skipped=r.skipped,
        row_warnings=dict(kinds),
        trade_date_from=r.trade_dates[0] if r.trade_dates else None,
        trade_date_to=r.trade_dates[-1] if r.trade_dates else None,
        trade_dates=len(r.trade_dates),
        coverage=[ContractCoverageOut(**vars_of(c)) for c in r.coverage],
        warnings=r.warnings,
    )


def vars_of(obj: object) -> dict:
    return {name: getattr(obj, name) for name in obj.__slots__}  # type: ignore[attr-defined]


def _contracts(observations: list[Observation]) -> list[ContractCoverageOut]:
    registry = default_registry()
    groups: dict[str, list[Observation]] = defaultdict(list)
    for o in observations:
        groups[o.contract_id].append(o)
    out = []
    for contract_id, group in sorted(groups.items()):
        first = group[0]
        resolution = registry.resolve(first.symbol, first.expiry)
        out.append(ContractCoverageOut(
            contract_id=contract_id,
            symbol=first.symbol,
            expiry=first.expiry,
            first_trade_date=min(o.trade_date for o in group),
            last_trade_date=max(o.trade_date for o in group),
            observations=len(group),
            traded_observations=sum(1 for o in group if o.traded),
            spec_status=resolution.status.value,
            spec_version_id=resolution.spec.version_id,
        ))
    return out


@functools.cache
def _demo_sha256() -> str:
    return hashlib.sha256(demo_csv_bytes()).hexdigest()


def _provenance(result: ImportResult) -> str:
    # The demo is recognised by its exact bytes, not its name: a user file that happens
    # to be called SYNTHETIC_demo_dataset.csv is labelled by the prefix rule below.
    if result.report.source_file == DEMO_FILENAME and result.report.source_sha256 == _demo_sha256():
        return "Generated synthetic demonstration dataset. Every price is invented; not market data."
    if result.report.synthetic:
        return "File name starts with SYNTHETIC_: treated as synthetic test data, not market data."
    return "Uploaded by a user. GoldLensAI has not verified that this file came from MCX."


def _import(data: bytes, name: str, date_order: DateOrder | None) -> ImportResult:
    try:
        return import_bhavcopy_bytes(data, source_name=name, date_order=date_order)
    except ImportFailedError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc


def _store(result: ImportResult, store: SessionStore, settings: Settings) -> UploadResponse:
    report = report_out(result, _provenance(result))
    if result.report.accepted == 0:
        return UploadResponse(
            stored=False,
            message="No supported gold futures rows were accepted, so nothing was added.",
            report=report,
        )
    try:
        store.add(result, max_files=settings.max_files, max_total_bytes=settings.max_total_bytes)
    except StoreError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return UploadResponse(
        stored=True,
        message=f"Added {result.report.accepted} observations from {result.report.source_file}.",
        report=report,
    )


def _safe_filename(raw: str) -> str:
    """Display name only: no directories, no control characters. Never used as a path."""
    name = PurePosixPath(raw.replace("\\", "/")).name
    name = "".join(ch for ch in name if ch.isprintable()).strip()
    if not name:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="A file name is required.")
    return name[:MAX_FILENAME]


async def _read_limited(request: Request, limit: int) -> bytes:
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > limit:
        raise HTTPException(
            status.HTTP_413_CONTENT_TOO_LARGE, detail=f"File exceeds the {limit}-byte upload limit."
        )
    chunks, size = [], 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > limit:
            raise HTTPException(
                status.HTTP_413_CONTENT_TOO_LARGE, detail=f"File exceeds the {limit}-byte upload limit."
            )
        chunks.append(chunk)
    return b"".join(chunks)
