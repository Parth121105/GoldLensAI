"""Response schemas for the dashboard API.

Prices and normalized values are decimal strings so exact exchange quotes are
never rounded by JSON floats. Research statistics are floats (bps).
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field

# --- Instruments -----------------------------------------------------------------


class SourceCitationOut(BaseModel):
    id: str
    title: str
    issuer: str
    issued_on: date
    location: str
    retrieved_from: str
    retrieved_on: date
    retrieval_notes: str


class SpecVersionOut(BaseModel):
    version_id: str
    verification: str
    expiry_from: str = Field(description="First covered expiry month, YYYY-MM")
    expiry_to: str = Field(description="Last covered expiry month, YYYY-MM")
    trading_unit_g: str
    quotation_base_g: str
    price_basis_fineness: int
    tick_size_inr: str
    price_quote_location: str
    price_quote_text: str
    delivery_unit_g: str
    quality_text: str
    price_basis_evidence: str
    last_trading_day_text: str
    sources: list[SourceCitationOut]
    notes: list[str]


class InstrumentOut(BaseModel):
    symbol: str
    name: str
    first_trading_date: date | None
    listing_evidence: str | None
    versions: list[SpecVersionOut]


class InstrumentsResponse(BaseModel):
    comparison_basis: str
    method_version: str
    instruments: list[InstrumentOut]


# --- Datasets ------------------------------------------------------------------------


class RejectedRowOut(BaseModel):
    line_number: int
    reasons: list[str]


class ContractCoverageOut(BaseModel):
    contract_id: str
    symbol: str
    expiry: date
    first_trade_date: date
    last_trade_date: date
    observations: int
    traded_observations: int
    spec_status: str
    spec_version_id: str


class ImportReportOut(BaseModel):
    source_file: str
    source_sha256: str
    size_bytes: int
    imported_at: datetime
    synthetic: bool
    provenance: str = Field(description="How the file reached the app; never 'official' unless verified")
    layout_id: str
    layout_verified_against_real_file: bool
    units: dict[str, str]
    date_order: str | None
    rows_read: int
    accepted: int
    exact_duplicates_dropped: int
    rejected_count: int
    rejected: list[RejectedRowOut] = Field(description="First rejected rows (see rejected_count)")
    skipped: dict[str, int]
    row_warnings: dict[str, int] = Field(description="Accepted-row warnings grouped by kind")
    trade_date_from: date | None
    trade_date_to: date | None
    trade_dates: int
    coverage: list[ContractCoverageOut]
    warnings: list[str]


class PackageTableOut(BaseModel):
    """One imported table of the MCX gold data package (A1, A2, B1 or B2)."""

    table_id: str
    kind: str = Field(description="annual | futures | options")
    title: str
    source_file: str
    source_sha256: str
    size_bytes: int
    imported_at: datetime
    synthetic: bool
    provenance: str
    rows_read: int
    accepted: int
    rejected_count: int
    rejected: list[RejectedRowOut]
    exact_duplicates_dropped: int
    cross_file_duplicates: int
    row_warnings: dict[str, int]
    table_warnings: list[str]
    missing_values: dict[str, int]
    numeric_ranges: dict[str, list[str]]
    coverage: dict[str, Any]


class UploadResponse(BaseModel):
    stored: bool
    message: str
    report: ImportReportOut | None = Field(
        default=None, description="Bhavcopy import report; absent for annual and options package tables"
    )
    package: PackageTableOut | None = Field(default=None, description="Present when the file was a package table")


class DatasetStatus(BaseModel):
    kind: str = Field(description="empty | user_uploaded | synthetic")
    storage: str
    files: list[ImportReportOut]
    observations: int
    trade_date_from: date | None
    trade_date_to: date | None
    contracts: list[ContractCoverageOut]
    cross_file_conflicts: list[str]
    limits: dict[str, int]
    package: list[PackageTableOut] = Field(default_factory=list)


class PackageRowsOut(BaseModel):
    table_id: str
    kind: str
    columns: list[str]
    rows: list[dict[str, Any]]
    truncated: bool


class ReadinessCheckOut(BaseModel):
    id: str
    label: str
    passed: bool
    detail: str


class ReadinessOut(BaseModel):
    verdict: str = Field(description="INSUFFICIENT_DATA | EXPLORATORY_ONLY | WALK_FORWARD_FEASIBLE")
    model: str
    checks: list[ReadinessCheckOut]
    minimums: dict[str, int]
    summary: dict[str, Any]
    missing: list[str]
    split_plan: dict[str, Any] | None


# --- Observations ------------------------------------------------------------------


class NormalizedOut(BaseModel):
    inr_per_gram_999: str
    basis: str
    quotation_base_g: str
    price_basis_fineness: int
    spec_version_id: str
    spec_status: str
    formula: str
    warnings: list[str]


class ObservationOut(BaseModel):
    trade_date: date
    contract_id: str
    symbol: str
    expiry: date
    open: str | None
    high: str | None
    low: str | None
    close: str
    previous_close: str | None
    settlement: str | None
    volume: int | None
    open_interest: int | None
    traded: bool | None
    warnings: list[str]
    source_file: str
    source_sha256: str
    line_number: int
    normalized: NormalizedOut | None
    normalization_error: str | None


class ObservationsResponse(BaseModel):
    kind: str
    price_field: str
    trade_dates: list[date] = Field(description="Every trade date in the session, for gap detection")
    observations: list[ObservationOut]


# --- Research ----------------------------------------------------------------------------


class CostComponentIn(BaseModel):
    bps_per_leg_side: float = Field(ge=0, le=1000)
    source: str | None = Field(default=None, max_length=300)
    as_of: date | None = None


class ResearchRequest(BaseModel):
    horizon: int = Field(default=5, ge=1, le=60)
    costs: dict[str, CostComponentIn] = Field(
        default_factory=dict,
        description="Known cost components; anything omitted stays UNKNOWN (never zero)",
    )


class CostComponentOut(BaseModel):
    name: str
    known: bool
    bps_per_leg_side: float | None
    source: str | None
    as_of: date | None
    label: str


class CostsOut(BaseModel):
    components: list[CostComponentOut]
    round_trip_bps: float | None
    unknown_components: list[str]


class LegOut(BaseModel):
    contract_id: str
    raw_price: str
    per_gram_999: str
    volume: int | None
    spec_version_id: str
    spec_status: str
    source_file: str
    line_number: int


class PointLegOut(BaseModel):
    """Compact leg for chart points; full provenance is on findings (LegOut)."""

    contract_id: str
    raw_price: str
    per_gram_999: str
    volume: int | None


class PointOut(BaseModel):
    trade_date: date
    spread_bps: float
    resolution_bps: float
    days_to_nearer_expiry: int
    eligible: bool
    ineligible_reasons: list[str]
    status: str
    baseline_n: int
    baseline_mean_bps: float | None
    baseline_std_bps: float | None
    deviation_bps: float | None
    z_score: float | None
    round_trip_cost_bps: float | None
    net_edge_bps: float | None
    notes: list[str]
    leg_a: PointLegOut
    leg_b: PointLegOut


class SeriesOut(BaseModel):
    pair_id: str
    symbol_pair: str
    contract_a: str
    contract_b: str
    expiry_a: date
    expiry_b: date
    comparison_type: str
    expiry_gap_days: int
    aligned_dates: int
    eligible_dates: int
    dates_missing_a: list[date]
    dates_missing_b: list[date]
    unusable: list[str]
    ineligible_reasons: dict[str, int]
    points: list[PointOut]


class OutcomeStatsOut(BaseModel):
    n: int
    mean_gross_bps: float | None
    std_gross_bps: float | None
    t_stat_gross: float | None
    hit_rate: float | None
    mean_net_bps: float | None
    t_stat_net: float | None


class WindowOut(BaseModel):
    label: str
    train_from: date
    train_to: date
    test_from: date
    test_to: date
    z_threshold: float | None
    baseline_window: int | None
    train_signals: int
    signals: OutcomeStatsOut
    controls: OutcomeStatsOut
    status: str


class DisplayParams(BaseModel):
    z_threshold: float
    baseline_window: int
    selected_by: str


class FindingOut(BaseModel):
    symbol_pair: str
    pair_id: str
    trade_date: date
    status: str
    spread_bps: float
    deviation_bps: float
    z_score: float
    resolution_bps: float
    round_trip_cost_bps: float | None
    net_edge_bps: float | None
    notes: list[str]
    leg_a: LegOut
    leg_b: LegOut


class PairResultOut(BaseModel):
    symbol_pair: str
    verdict: str
    reasons: list[str]
    eligible_dates: int
    development_from: date | None
    development_to: date | None
    holdout_from: date | None
    holdout_to: date | None
    folds: list[WindowOut]
    final: WindowOut | None
    sensitivity: dict[str, OutcomeStatsOut]
    display_params: DisplayParams
    findings: list[FindingOut]
    series: list[SeriesOut]


class ResearchConfigOut(BaseModel):
    price_field: str
    horizon: int
    z_thresholds: list[float]
    baseline_windows: list[int]
    holdout_fraction: float
    n_folds: int
    min_events: int
    min_t_stat: float
    max_expiry_gap_days: int
    min_volume: int
    lifecycle_buffer_days: int
    allow_unverified_specs: bool


class ResearchResponse(BaseModel):
    generated_at: datetime
    kind: str
    sources: list[str]
    observations: int
    trade_date_from: date | None
    trade_date_to: date | None
    cross_file_conflicts: list[str]
    config: ResearchConfigOut
    costs: CostsOut
    pairs: list[PairResultOut]
