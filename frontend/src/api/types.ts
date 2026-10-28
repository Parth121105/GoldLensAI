// Mirrors backend/app/api/schemas.py. Prices are decimal strings from the API.

export type DataKind = 'empty' | 'user_uploaded' | 'synthetic'

export interface SourceCitation {
  id: string
  title: string
  issuer: string
  issued_on: string
  location: string
  retrieved_from: string
  retrieved_on: string
  retrieval_notes: string
}

export interface SpecVersion {
  version_id: string
  verification: string
  expiry_from: string
  expiry_to: string
  trading_unit_g: string
  quotation_base_g: string
  price_basis_fineness: number
  tick_size_inr: string
  price_quote_location: string
  price_quote_text: string
  delivery_unit_g: string
  quality_text: string
  price_basis_evidence: string
  last_trading_day_text: string
  sources: SourceCitation[]
  notes: string[]
}

export interface Instrument {
  symbol: string
  name: string
  first_trading_date: string | null
  listing_evidence: string | null
  versions: SpecVersion[]
}

export interface InstrumentsResponse {
  comparison_basis: string
  method_version: string
  instruments: Instrument[]
}

export interface RejectedRow {
  line_number: number
  reasons: string[]
}

export interface ContractCoverage {
  contract_id: string
  symbol: string
  expiry: string
  first_trade_date: string
  last_trade_date: string
  observations: number
  traded_observations: number
  spec_status: string
  spec_version_id: string
}

export interface ImportReport {
  source_file: string
  source_sha256: string
  size_bytes: number
  imported_at: string
  synthetic: boolean
  provenance: string
  layout_id: string
  layout_verified_against_real_file: boolean
  units: Record<string, string>
  date_order: string | null
  rows_read: number
  accepted: number
  exact_duplicates_dropped: number
  rejected_count: number
  rejected: RejectedRow[]
  skipped: Record<string, number>
  row_warnings: Record<string, number>
  trade_date_from: string | null
  trade_date_to: string | null
  trade_dates: number
  coverage: ContractCoverage[]
  warnings: string[]
}

/** One imported table of the MCX gold data package (A1, A2, B1 or B2). */
export interface PackageTable {
  table_id: 'A1' | 'A2' | 'B1' | 'B2'
  kind: 'annual' | 'futures' | 'options'
  title: string
  source_file: string
  source_sha256: string
  size_bytes: number
  imported_at: string
  synthetic: boolean
  provenance: string
  rows_read: number
  accepted: number
  rejected_count: number
  rejected: RejectedRow[]
  exact_duplicates_dropped: number
  cross_file_duplicates: number
  row_warnings: Record<string, number>
  table_warnings: string[]
  missing_values: Record<string, number>
  numeric_ranges: Record<string, [string, string]>
  coverage: Record<string, unknown>
}

export interface UploadResponse {
  stored: boolean
  message: string
  /** Bhavcopy import report; null for annual and options package tables. */
  report: ImportReport | null
  package: PackageTable | null
}

export interface DatasetStatus {
  kind: DataKind
  storage: string
  files: ImportReport[]
  observations: number
  trade_date_from: string | null
  trade_date_to: string | null
  contracts: ContractCoverage[]
  cross_file_conflicts: string[]
  limits: Record<string, number>
  package: PackageTable[]
}

export interface ReadinessCheck {
  id: string
  label: string
  passed: boolean
  detail: string
}

export type ReadinessVerdict = 'INSUFFICIENT_DATA' | 'EXPLORATORY_ONLY' | 'WALK_FORWARD_FEASIBLE'

export interface Readiness {
  verdict: ReadinessVerdict
  model: string
  checks: ReadinessCheck[]
  minimums: { dates_for_baseline: number; dates_for_holdout: number; eligible_dates_per_pair: number }
  summary: Record<string, unknown>
  missing: string[]
  split_plan: { folds: { train: [string, string]; test: [string, string] }[]; development: [string, string]; holdout: [string, string] } | null
}

export interface Normalized {
  inr_per_gram_999: string
  basis: string
  quotation_base_g: string
  price_basis_fineness: number
  spec_version_id: string
  spec_status: string
  formula: string
  warnings: string[]
}

export interface Observation {
  trade_date: string
  contract_id: string
  symbol: string
  expiry: string
  open: string | null
  high: string | null
  low: string | null
  close: string
  previous_close: string | null
  settlement: string | null
  volume: number | null
  open_interest: number | null
  traded: boolean | null
  warnings: string[]
  source_file: string
  source_sha256: string
  line_number: number
  normalized: Normalized | null
  normalization_error: string | null
}

export interface ObservationsResponse {
  kind: DataKind
  price_field: string
  trade_dates: string[]
  observations: Observation[]
}

export const COST_COMPONENTS = [
  'brokerage',
  'exchange_transaction_charges',
  'statutory_taxes_and_levies',
  'slippage',
] as const
export type CostName = (typeof COST_COMPONENTS)[number]

export interface CostInput {
  bps_per_leg_side: number
  source?: string | null
  as_of?: string | null
}

export interface ResearchRequest {
  horizon: number
  costs: Partial<Record<CostName, CostInput>>
}

export interface CostComponent {
  name: string
  known: boolean
  bps_per_leg_side: number | null
  source: string | null
  as_of: string | null
  label: string
}

export interface Leg {
  contract_id: string
  raw_price: string
  per_gram_999: string
  volume: number | null
  spec_version_id: string
  spec_status: string
  source_file: string
  line_number: number
}

export interface PointLeg {
  contract_id: string
  raw_price: string
  per_gram_999: string
  volume: number | null
}

export type PointStatus =
  | 'ineligible'
  | 'insufficient_history'
  | 'degenerate_baseline'
  | 'within_baseline'
  | 'candidate_anomaly'
  | 'statistical_anomaly'
  | 'cost_adjusted_candidate'

export interface Point {
  trade_date: string
  spread_bps: number
  resolution_bps: number
  days_to_nearer_expiry: number
  eligible: boolean
  ineligible_reasons: string[]
  status: PointStatus
  baseline_n: number
  baseline_mean_bps: number | null
  baseline_std_bps: number | null
  deviation_bps: number | null
  z_score: number | null
  round_trip_cost_bps: number | null
  net_edge_bps: number | null
  notes: string[]
  leg_a: PointLeg
  leg_b: PointLeg
}

export interface Series {
  pair_id: string
  symbol_pair: string
  contract_a: string
  contract_b: string
  expiry_a: string
  expiry_b: string
  comparison_type: 'same_expiry' | 'cross_expiry'
  expiry_gap_days: number
  aligned_dates: number
  eligible_dates: number
  dates_missing_a: string[]
  dates_missing_b: string[]
  unusable: string[]
  ineligible_reasons: Record<string, number>
  points: Point[]
}

export interface OutcomeStats {
  n: number
  mean_gross_bps: number | null
  std_gross_bps: number | null
  t_stat_gross: number | null
  hit_rate: number | null
  mean_net_bps: number | null
  t_stat_net: number | null
}

export interface ValidationWindow {
  label: string
  train_from: string
  train_to: string
  test_from: string
  test_to: string
  z_threshold: number | null
  baseline_window: number | null
  train_signals: number
  signals: OutcomeStats
  controls: OutcomeStats
  status: string
}

export interface Finding {
  symbol_pair: string
  pair_id: string
  trade_date: string
  status: PointStatus
  spread_bps: number
  deviation_bps: number
  z_score: number
  resolution_bps: number
  round_trip_cost_bps: number | null
  net_edge_bps: number | null
  notes: string[]
  leg_a: Leg
  leg_b: Leg
}

export type Verdict =
  | 'insufficient_data'
  | 'not_supported'
  | 'supported_before_costs_costs_unknown'
  | 'not_supported_after_costs'
  | 'historically_validated'

export interface PairResult {
  symbol_pair: string
  verdict: Verdict
  reasons: string[]
  eligible_dates: number
  development_from: string | null
  development_to: string | null
  holdout_from: string | null
  holdout_to: string | null
  folds: ValidationWindow[]
  final: ValidationWindow | null
  sensitivity: Record<string, OutcomeStats>
  display_params: { z_threshold: number; baseline_window: number; selected_by: string }
  findings: Finding[]
  series: Series[]
}

export interface ResearchConfig {
  price_field: string
  horizon: number
  z_thresholds: number[]
  baseline_windows: number[]
  holdout_fraction: number
  n_folds: number
  min_events: number
  min_t_stat: number
  max_expiry_gap_days: number
  min_volume: number
  lifecycle_buffer_days: number
  allow_unverified_specs: boolean
}

export interface ResearchResponse {
  generated_at: string
  kind: DataKind
  sources: string[]
  observations: number
  trade_date_from: string | null
  trade_date_to: string | null
  cross_file_conflicts: string[]
  config: ResearchConfig
  costs: { components: CostComponent[]; round_trip_bps: number | null; unknown_components: string[] }
  pairs: PairResult[]
}

// --- Relative value (GET /api/relative-value) --------------------------------------------------

export interface ContractQuote {
  contract_id: string
  symbol: string
  expiry: string
  close: string
  quotation_base_g: string
  price_basis_fineness: number
  price_quote_location: string
  inr_per_gram_999: string | null
  spec_version_id: string | null
  spec_verified: boolean
  volume: number | null
  traded_value_lakh: string | null
  open_interest: number | null
  days_to_expiry: number
  thin: boolean
  thin_reasons: string[]
  error: string | null
}

export interface PairGap {
  symbol_a: string
  symbol_b: string
  contract_a: string
  contract_b: string
  expiry_gap_days: number
  gap_bps: number
  resolution_bps: number
  tradeable: boolean
  not_tradeable_reasons: string[]
  location_basis: string | null
  carry_bps: number | null
  carry_adjusted_gap_bps: number | null
}

export interface RelativeValueDay {
  trade_date: string
  contracts: ContractQuote[]
  pairs: PairGap[]
}

export interface RelativeValueResponse {
  kind: 'empty' | 'user_uploaded' | 'synthetic'
  synthetic: boolean
  basis: string
  price_field: string
  disclaimers: string[]
  liquidity: {
    min_volume_lots: number
    min_traded_value_lakh: string
    min_open_interest_lots: number
    expiry_buffer_days: number
    max_expiry_gap_days: number
    official_tender_period: string
    assumptions_file: string
    assumptions: { key: string; value: string; unit: string; why: string }[]
  }
  days: RelativeValueDay[]
}

// --- Term structure (GET /api/term-structure) ----------------------------------------------------

export interface CurvePoint {
  contract_id: string
  expiry: string
  days_to_expiry: number
  inr_per_gram_999: number
  fitted: number
  residual_bps: number
  thin: boolean
}

export interface Curve {
  symbol: string
  trade_date: string
  slope_bps_per_day: number
  annualised_carry_pct: number
  raw_check_annualised_pct: number | null
  points: CurvePoint[]
}

export interface MoveSplit {
  contract_id: string
  symbol: string
  from_date: string
  to_date: string
  total_bps: number
  gold_move_bps: number
  roll_down_bps: number
  curve_change_bps: number
  residual_bps: number
}

export interface TermStructureResponse {
  kind: 'empty' | 'user_uploaded' | 'synthetic'
  synthetic: boolean
  method: string[]
  curves: Curve[]
  splits: MoveSplit[]
}

// --- Lifecycle (GET /api/lifecycle) ---------------------------------------------------------------

export interface CalendarEntry {
  symbol: string
  contract_id: string | null
  expiry_month: string
  launch_month: string
  listing_date: string
  tender_start: string
  expiry: string
  expiry_source: string
  tender_trading_days: number
  making_charge: string | null
  spec_version_id: string
}

export interface ContractStatus {
  contract_id: string
  trade_date: string
  days_to_expiry: number
  trading_days_to_expiry: number
  phase: 'trading' | 'near_expiry' | 'tender_period'
}

export interface YearlyRow {
  year: number
  symbol: string
  lots_traded: number
  total_value_crore: number
  trading_days: number | null
  partial_year: boolean
}

export interface LifecycleResponse {
  kind: 'empty' | 'user_uploaded' | 'synthetic'
  trade_dates: string[]
  notes: string[]
  expiry_buffer_days: number
  calendar: CalendarEntry[]
  status: ContractStatus[]
  yearly_source: string | null
  yearly_problem: string | null
  yearly: YearlyRow[]
}

// --- Synthetic validation (GET /api/validation/synthetic) ------------------------------------------

export interface SyntheticRun {
  label: string
  injected: boolean
  trade_dates: number
  first_date: string
  last_date: string
  eligible_dates_needed: number
  holdout_from: string | null
  holdout_to: string | null
  pairs: { symbol_pair: string; eligible_dates: number; verdict: string; z_threshold: number | null; baseline_window: number | null }[]
  injections_total: number
  injections_in_holdout: number
  caught: number
  catch_rate: number | null
  clean_points: number
  false_alarms: number
  false_alarm_rate: number | null
  round_trip_cost_bps: number
  cost_labels: string[]
  making_charges_paid: string
  pnl: {
    trades: number
    total_gross_bps: number | null
    total_net_bps: number | null
    mean_gross_bps: number | null
    mean_net_bps: number | null
    hit_rate_net: number | null
    total_gold_move_bps: number | null
    corr_strategy_gold: number | null
  }
  cumulative: { exit: string; cumulative_gross_bps: number; cumulative_net_bps: number; cumulative_gold_move_bps: number }[]
}

export interface SyntheticValidationResponse {
  synthetic: true
  notice: string
  model: string[]
  runs: SyntheticRun[]
}

// --- Real-data verdict (GET /api/verdict) ------------------------------------------------------------

export interface VerdictResponse {
  kind: 'empty' | 'user_uploaded' | 'synthetic'
  trade_dates: number
  needed_per_pair: number
  pairs: { symbol_pair: string; eligible_dates: number; needed: number; verdict: string }[]
  statement: string
}
