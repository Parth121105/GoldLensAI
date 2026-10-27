"""Read the MCX gold package tables and the data-readiness assessment."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import get_store
from app.api.schemas import PackageRowsOut, ReadinessCheckOut, ReadinessOut
from app.ingestion.package import PACKAGE_TABLES
from app.research.readiness import assess
from app.store import SessionStore

router = APIRouter(tags=["package"])

MAX_ROWS = 5000
_TABLE_IDS = {t.id for t in PACKAGE_TABLES}


@router.get("/package/rows", response_model=PackageRowsOut)
def package_rows(
    table: str = Query(description="A1, A2, B1 or B2"),
    store: SessionStore = Depends(get_store),
) -> PackageRowsOut:
    """Accepted rows of one package table, as imported (numbers as decimal strings)."""
    table_id = table.upper()
    if table_id not in _TABLE_IDS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"Unknown package table {table!r}.")
    imports = [p for p in store.package_snapshot() if p.table.id == table_id]
    if not imports:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"Table {table_id} has not been imported.")
    spec = imports[0].table
    rows = [
        {c.name: _json(row[c.name]) for c in spec.columns} | {"source_file": p.source_file, "line_number": row["line_number"]}
        for p in imports for row in p.rows
    ]
    return PackageRowsOut(
        table_id=table_id,
        kind=spec.kind.value,
        columns=list(spec.header),
        rows=rows[:MAX_ROWS],
        truncated=len(rows) > MAX_ROWS,
    )


@router.get("/readiness", response_model=ReadinessOut)
def readiness(store: SessionStore = Depends(get_store)) -> ReadinessOut:
    """Whether the loaded data can support walk-forward research or a model, and what is missing."""
    r = assess(store.snapshot(), store.package_snapshot())
    return ReadinessOut(
        verdict=r.verdict.value,
        model=r.model,
        checks=[ReadinessCheckOut(id=c.id, label=c.label, passed=c.passed, detail=c.detail) for c in r.checks],
        minimums={
            "dates_for_baseline": r.minimums.dates_for_baseline,
            "dates_for_holdout": r.minimums.dates_for_holdout,
            "eligible_dates_per_pair": r.minimums.eligible_dates_per_pair,
        },
        summary=r.summary,
        missing=r.missing,
        split_plan=r.split_plan,
    )


def _json(value: object) -> object:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, date):
        return value.isoformat()
    return value
