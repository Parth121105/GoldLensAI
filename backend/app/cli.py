"""Command-line tools.

    python -m app.cli specs
    python -m app.cli import <file.csv> [--date-order DMY|MDY] [--json]
    python -m app.cli research <file.csv> [<file.csv> ...] [--costs costs.json] [--horizon N]
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from pathlib import Path

from app.ingestion import DateOrder, ImportFailedError, import_bhavcopy
from app.research import CostModel, MixedDataError, ResearchConfig, run_research
from app.specs import default_registry


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("specs", help="List contract specification versions and sources")

    p_import = sub.add_parser("import", help="Validate a Bhavcopy CSV and print a report")
    p_import.add_argument("file", type=Path)
    p_import.add_argument("--date-order", choices=[o.value for o in DateOrder])
    p_import.add_argument("--json", action="store_true", help="Print the full report as JSON")

    p_research = sub.add_parser("research", help="Run spread research and walk-forward validation")
    p_research.add_argument("files", type=Path, nargs="+")
    p_research.add_argument("--date-order", choices=[o.value for o in DateOrder])
    p_research.add_argument("--costs", type=Path, help="JSON file of cost components (see docs)")
    p_research.add_argument("--horizon", type=int, default=ResearchConfig().horizon)

    args = parser.parse_args(argv)
    if args.command == "specs":
        return _print_specs()
    if args.command == "research":
        return _research(args.files, args.date_order and DateOrder(args.date_order), args.costs,
                         args.horizon)
    return _import(args.file, args.date_order and DateOrder(args.date_order), args.json)


def _print_specs() -> int:
    registry = default_registry()
    for spec in registry.all_versions():
        lo, hi = spec.expiry_from, spec.expiry_to
        print(f"{spec.version_id}  [{spec.verification}]")
        print(f"  expiries      {lo[0]}-{lo[1]:02d} to {hi[0]}-{hi[1]:02d}")
        print(f"  trading unit  {spec.trading_unit_g} g, quoted per {spec.quotation_base_g} g")
        print(f"  price basis   {spec.price_basis_fineness} fineness, {spec.price_quote_location}")
        print(f"  last trading  {spec.last_trading_day_text}")
        for c in spec.sources:
            print(f"  source        {c.source.id} ({c.source.issued_on}), {c.location}")
        print()
    return 0


def _import(path: Path, order: DateOrder | None, as_json: bool) -> int:
    try:
        result = import_bhavcopy(path, date_order=order)
    except (ImportFailedError, OSError) as exc:
        print(f"Import failed: {exc}", file=sys.stderr)
        return 1

    report = result.report
    if as_json:
        print(json.dumps(dataclasses.asdict(report), default=_json_default, indent=2))
        return 0

    if report.synthetic:
        print("*** SYNTHETIC FILE: not real market data ***")
    print(f"File       {report.source_file}  sha256={report.source_sha256[:16]}...")
    print(f"Layout     {report.layout_id}  (verified against real MCX file: "
          f"{report.layout_verified_against_real_file})")
    print(f"Rows       read={report.rows_read} accepted={report.accepted} "
          f"rejected={len(report.rejected)} duplicates_dropped={report.exact_duplicates_dropped}")
    for reason, count in report.skipped.items():
        print(f"Skipped    {count} x {reason}")
    if report.trade_dates:
        print(f"Dates      {report.trade_dates[0]} to {report.trade_dates[-1]} "
              f"({len(report.trade_dates)} trade dates)")
    for c in report.coverage:
        print(f"Contract   {c.contract_id}: {c.observations} obs "
              f"({c.traded_observations} traded), spec {c.spec_status}")
    for r in report.rejected:
        print(f"Rejected   line {r.line_number}: {'; '.join(r.reasons)}")
    for o in result.observations:
        for w in o.warnings:
            print(f"Row note   line {o.provenance.line_number} {o.contract_id}: {w}")
    for w in report.warnings:
        print(f"Warning    {w}")
    return 0


def _research(files: list[Path], order: DateOrder | None, costs_file: Path | None, horizon: int) -> int:
    try:
        imports = [import_bhavcopy(f, date_order=order) for f in files]
        costs = CostModel.from_dict(json.loads(costs_file.read_text())) if costs_file else CostModel()
        report = run_research(imports, ResearchConfig(horizon=horizon, costs=costs))
    except (ImportFailedError, MixedDataError, OSError, ValueError) as exc:
        print(f"Research failed: {exc}", file=sys.stderr)
        return 1

    if report.synthetic:
        print("*** SYNTHETIC DATA: results are pipeline checks, not market findings ***")
    span = report.trade_date_range
    print(f"Files        {len(report.sources)}; observations {report.observations}; "
          f"dates {f'{span[0]} to {span[1]}' if span else 'none'}")
    for c in report.config.costs.components:
        print(f"Cost         {c.label}")
    for conflict in report.cross_file_conflicts:
        print(f"Conflict     {conflict}")
    for cov in report.coverage:
        print(f"Series       {cov.pair_id} ({cov.comparison_type}, gap {cov.expiry_gap_days}d): "
              f"{cov.eligible_dates}/{cov.aligned_dates} eligible; ineligible {cov.ineligible_reasons}")
    if not report.validations:
        print("Validation   no comparable contract pairs in the data")
    for v in report.validations:
        print(f"Validation   {v.symbol_pair}: {v.verdict.value}")
        for reason in v.reasons:
            print(f"               {reason}")
    return 0


def _json_default(value: object) -> object:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    raise TypeError(f"Cannot serialise {type(value).__name__}")


if __name__ == "__main__":
    raise SystemExit(main())
