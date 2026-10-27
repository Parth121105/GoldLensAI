import type { PointStatus, ReadinessVerdict, Verdict } from '../api/types'
import type { Tone } from '../components/ui'

/** Display order for instruments: the contract sizes from largest to smallest. */
export const SYMBOL_ORDER = ['GOLDM', 'GOLDTEN', 'GOLDGUINEA', 'GOLDPETAL']

export const VERDICTS: Record<Verdict, { label: string; tone: Tone; explain: string }> = {
  insufficient_data: {
    label: 'Insufficient data',
    tone: 'neutral',
    explain: 'Too few eligible dates or out-of-sample signals to test the hypothesis. No result is reported.',
  },
  not_supported: {
    label: 'Not supported',
    tone: 'neutral',
    explain: 'Out of sample, flagged deviations did not reliably move back toward the baseline.',
  },
  supported_before_costs_costs_unknown: {
    label: 'Supported before costs · costs unknown',
    tone: 'warn',
    explain:
      'Out of sample, deviations reverted more than ordinary days, but at least one cost component is unknown, so it cannot be validated.',
  },
  not_supported_after_costs: {
    label: 'Not supported after costs',
    tone: 'neutral',
    explain: 'Reversion out of sample was smaller than the supplied round-trip costs.',
  },
  historically_validated: {
    label: 'Historically validated',
    tone: 'good',
    explain:
      'Survived out-of-sample testing net of the supplied costs. A historical result only; it still needs independent checks with executable quotes and depth.',
  },
}

export const STATUSES: Record<PointStatus, { label: string; tone: Tone }> = {
  ineligible: { label: 'Ineligible', tone: 'neutral' },
  insufficient_history: { label: 'Insufficient history', tone: 'neutral' },
  degenerate_baseline: { label: 'Flat baseline', tone: 'neutral' },
  within_baseline: { label: 'Within baseline', tone: 'neutral' },
  candidate_anomaly: { label: 'Candidate anomaly', tone: 'neutral' },
  statistical_anomaly: { label: 'Statistical anomaly', tone: 'info' },
  cost_adjusted_candidate: { label: 'Cost-adjusted candidate', tone: 'gold' },
}

export const INELIGIBLE: Record<string, string> = {
  unverified_spec: 'Unverified specification',
  volume_unknown: 'Volume not reported',
  volume_below_min: 'No trades / volume below minimum',
  lifecycle_buffer: 'Inside delivery/tender buffer',
}

export const COST_LABELS: Record<string, string> = {
  brokerage: 'Brokerage',
  exchange_transaction_charges: 'Exchange transaction charges',
  statutory_taxes_and_levies: 'Statutory taxes and levies',
  slippage: 'Slippage',
}

export const VERDICT_LABEL: Record<ReadinessVerdict, { label: string; tone: Tone; explain: string }> = {
  INSUFFICIENT_DATA: {
    label: 'Insufficient data',
    tone: 'warn',
    explain: 'The loaded data cannot support research or a model yet. Nothing is trained or validated.',
  },
  EXPLORATORY_ONLY: {
    label: 'Exploratory only',
    tone: 'info',
    explain: 'Flags can be computed, but there is too little history for a walk-forward verdict.',
  },
  WALK_FORWARD_FEASIBLE: {
    label: 'Walk-forward feasible',
    tone: 'good',
    explain: 'The minimum history exists. Whether any verdict is reached still depends on the signals found.',
  },
}
