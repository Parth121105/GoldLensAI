"""Command-line tools.

    python -m app.cli specs
    python -m app.cli import <file.csv> [--date-order DMY|MDY] [--json]
    python -m app.cli import-dir <folder> [--store-dir DIR]
    python -m app.cli research <file.csv> [<file.csv> ...] [--costs costs.json] [--horizon N]
    python -m app.cli package-extract <package.pdf> <output-dir>
    python -m app.cli package-audit <table.csv> [<table.csv> ...] [--out audit.json]
    python -m app.cli readiness <bhavcopy file> [...]
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import sys
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from pathlib import Path

from app.ingestion import DateOrder, ImportFailedError, import_bhavcopy
from app.ingestion.package import PackageImportError, audit_dict, import_package_table
from app.ingestion.package_pdf import PackageExtractError, extract_blocks, pdf_to_text
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

    p_dir = sub.add_parser(
        "import-dir", help="Import every Bhavcopy file in a folder and save the gold rows to the store"
    )
    p_dir.add_argument("folder", type=Path)
    p_dir.add_argument("--store-dir", type=Path, help="Defaults to GOLDLENS_STORE_DIR or backend/data/store")

    p_research = sub.add_parser("research", help="Run spread research and walk-forward validation")
    p_research.add_argument("files", type=Path, nargs="+")
    p_research.add_argument("--date-order", choices=[o.value for o in DateOrder])
    p_research.add_argument("--costs", type=Path, help="JSON file of cost components (see docs)")
    p_research.add_argument("--horizon", type=int, default=ResearchConfig().horizon)

    p_extract = sub.add_parser("package-extract", help="Recover the package CSV tables from its PDF")
    p_extract.add_argument("pdf", type=Path)
    p_extract.add_argument("out_dir", type=Path)

    p_audit = sub.add_parser("package-audit", help="Validate package tables and write an audit report")
    p_audit.add_argument("files", type=Path, nargs="+")
    p_audit.add_argument("--out", type=Path, help="Write the audit JSON here as well as printing a summary")

    p_ready = sub.add_parser("readiness", help="Assess whether Bhavcopy files can support research or a model")
    p_ready.add_argument("files", type=Path, nargs="+")

    args = parser.parse_args(argv)
    if args.command == "specs":
        return _print_specs()
    if args.command == "package-extract":
        return _package_extract(args.pdf, args.out_dir)
    if args.command == "package-audit":
        return _package_audit(args.files, args.out)
    if args.command == "readiness":
        return _readiness(args.files)
    if args.command == "import-dir":
        return _import_dir(args.folder, args.store_dir)
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
        if spec.tender_period:
            print(f"  tender period {spec.tender_period.text}")
        if spec.making_charge:
            print(f"  making charge {spec.making_charge.text}")
        for c in spec.sources:
            print(f"  source        {c.source.id} ({c.source.issued_on}), {c.location}")
        print()
    for symbol, gap in sorted(registry.uncovered.items()):
        print(f"No specification PDF covers {symbol} expiries {gap}.")
    return 0


def _import_dir(folder: Path, store_dir: Path | None) -> int:
    """Import each file in date order of name, saving accepted gold rows; already-held days are skipped."""
    from collections import Counter

    from app.persistence import ImportArchive
    from app.settings import Settings
    from app.store import AlreadyHeldError, SessionStore, StoreError

    settings = Settings.from_env()
    target = store_dir or settings.store_dir
    if target is None:
        print("error: GOLDLENS_STORE_DIR is off; pass --store-dir", file=sys.stderr)
        return 1
    store = SessionStore.open(ImportArchive(target))
    files = sorted(p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in {".csv", ".xls", ".htm", ".html", ".txt"})
    if not files:
        print(f"No Bhavcopy files in {folder}", file=sys.stderr)
        return 1
    failed = 0
    for path in files:
        try:
            result = import_bhavcopy(path)
            store.add(result, max_files=settings.max_files, max_total_bytes=settings.max_total_bytes)
        except AlreadyHeldError:
            print(f"{path.name}: skipped, every gold row is already held")
            continue
        except (ImportFailedError, StoreError, OSError) as exc:
            print(f"{path.name}: not imported: {exc}", file=sys.stderr)
            failed += 1
            continue
        report = result.report
        for w in report.warnings:
            print(f"{path.name}: warning: {w}")
        per_day = Counter((o.trade_date, o.symbol) for o in result.observations)
        for (day, symbol), n in sorted(per_day.items()):
            expiries = sorted({o.expiry for o in result.observations if o.trade_date == day and o.symbol == symbol})
            print(f"{path.name}: {day} {symbol:<10} {n} contracts ({', '.join(f'{e:%d%b%Y}'.upper() for e in expiries)})")
    print(f"Store {target}: {len(store.imports)} files, "
          f"{sum(len(r.observations) for r in store.imports)} gold rows. Restart the server to load them.")
    return 1 if failed else 0


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


def _package_extract(pdf: Path, out_dir: Path) -> int:
    """Write each CSV block of the package PDF to out_dir, with a manifest of hashes.

    The PDF is only read. An existing output file with different content is never
    overwritten.
    """
    try:
        text, tool = pdf_to_text(pdf)
        tables = extract_blocks(text)
    except PackageExtractError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    out_dir.mkdir(parents=True, exist_ok=True)
    for t in tables:
        target = out_dir / t.file_name
        if target.exists() and target.read_text(encoding="utf-8") != t.csv_text:
            print(f"error: {target} exists with different content; not overwritten", file=sys.stderr)
            return 1
    for t in tables:
        (out_dir / t.file_name).write_text(t.csv_text, encoding="utf-8", newline="\n")
        print(f"{t.file_name}: {t.rows} rows, sha256 {t.sha256}")
    manifest = {
        "source_pdf": pdf.name,
        "source_pdf_sha256": hashlib.sha256(pdf.read_bytes()).hexdigest(),
        "extracted_with": tool,
        "extracted_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "method": "CSV blocks between ===BEGIN and ===END; page footers removed; every row checked for the header's column count",
        "files": {t.file_name: {"rows": t.rows, "sha256": t.sha256} for t in tables},
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return 0


def _package_audit(files: list[Path], out: Path | None) -> int:
    audits = []
    for path in files:
        try:
            result = import_package_table(path.read_bytes(), source_name=path.name)
        except PackageImportError as exc:
            print(f"{path.name}: not imported: {exc}", file=sys.stderr)
            return 1
        audit = audit_dict(result)
        audits.append(audit)
        print(
            f"{audit['table_id']} {path.name}: read {audit['rows_read']}, accepted {audit['accepted']}, "
            f"rejected {audit['rejected']}, duplicates {audit['exact_duplicates_dropped']}, "
            f"warnings {sum(audit['row_warnings'].values()) + len(audit['table_warnings'])}"
        )
    if out:
        out.write_text(json.dumps({"tables": audits}, indent=2, default=_json_default) + "\n", encoding="utf-8")
        print(f"audit written to {out}")
    return 0


def _readiness(files: list[Path]) -> int:
    from app.research.readiness import assess

    imports = []
    for path in files:
        try:
            imports.append(import_bhavcopy(path))
        except ImportFailedError as exc:
            print(f"{path.name}: not imported: {exc}", file=sys.stderr)
            return 1
    r = assess(imports)
    print(f"verdict: {r.verdict.value}")
    print(r.model)
    for c in r.checks:
        print(f"  {'PASS' if c.passed else 'FAIL'}  {c.label}: {c.detail}")
    for m in r.missing:
        print(f"  missing: {m}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
