// Shapes the Overview bento's inputs from what the API already returns. Nothing here is a
// model output or a new calculation: prices are the backend's normalized INR per gram (999)
// scaled to 10 g for display, and every spread, baseline, z-score and verdict is copied
// from the research run as computed by the backend.

import type {
  DatasetStatus,
  Instrument,
  Observation,
  OutcomeStats,
  PairResult,
  PointStatus,
  ResearchResponse,
  Series,
  Verdict,
} from '../api/types'
import { monthTick } from './format'
import { SYMBOL_ORDER } from './labels'

export interface PricePoint {
  date: string
  /** INR per 10 g at 999 fineness. */
  price: number
}

export interface PriceSeries {
  contractId: string
  symbol: string
  expiry: string
  points: PricePoint[]
}

export interface SpreadPoint {
  date: string
  spread: number
  baseline: number | null
  std: number | null
  z: number | null
  deviation: number | null
}

export interface PairView {
  id: string
  label: string
  /** The fixed contracts of the series shown, e.g. "GOLDM Jul 26 · GOLDGUINEA Jun 26". */
  legs: string
  verdict: Verdict
  points: SpreadPoint[]
  zThreshold: number
  zOptions: number[]
  baselineWindow: number
  horizon: number
  minEvents: number
  holdout: OutcomeStats | null
  holdoutFrom: string | null
  holdoutTo: string | null
  /** Out-of-sample signal count per walk-forward window, folds then the holdout. */
  windows: { label: string; n: number }[]
  eligibleDates: number
  excludedDates: number
  missingLegDates: number
  unknownCosts: number
  roundTripBps: number | null
}

export interface SignalView {
  id: string
  pair: string
  legs: string
  date: string
  status: PointStatus
  z: number
  deviation: number
  netEdge: number | null
}

export interface InstrumentCard {
  symbol: string
  name: string
  tradingUnitG: string
  quoteBaseG: string
  fineness: number
  verified: boolean
  latest: PricePoint | null
}

export interface Composition {
  symbol: string
  value: number
}

const per10g = (o: Observation): number | null => (o.normalized ? Number(o.normalized.inr_per_gram_999) * 10 : null)

export const contractLabel = (symbol: string, expiry: string) => `${symbol} ${monthTick(expiry)}`

/**
 * One fixed contract's closes (never spliced across expiries): among the contracts trading on the
 * latest date, the one with the longest history in the session. Last `sessions` + 1 points.
 */
export function priceSeries(observations: Observation[], sessions = 30): PriceSeries | null {
  const priced = observations.filter((o) => per10g(o) != null)
  if (priced.length === 0) return null
  const last = priced.reduce((m, o) => (o.trade_date > m ? o.trade_date : m), '')
  const byContract = new Map<string, Observation[]>()
  priced.forEach((o) => byContract.set(o.contract_id, [...(byContract.get(o.contract_id) ?? []), o]))
  const live = [...byContract.values()].filter((list) => list.some((o) => o.trade_date === last))
  const pick = live.reduce((a, b) => (b.length > a.length ? b : a))
  const sorted = [...pick].sort((a, b) => a.trade_date.localeCompare(b.trade_date)).slice(-(sessions + 1))
  return {
    contractId: pick[0].contract_id,
    symbol: pick[0].symbol,
    expiry: pick[0].expiry,
    points: sorted.map((o) => ({ date: o.trade_date, price: per10g(o)! })),
  }
}

export function instrumentCards(instruments: Instrument[], observations: Observation[]): InstrumentCard[] {
  const order = (s: string) => {
    const i = SYMBOL_ORDER.indexOf(s)
    return i === -1 ? SYMBOL_ORDER.length : i
  }
  return [...instruments]
    .sort((a, b) => order(a.symbol) - order(b.symbol))
    .filter((i) => i.versions.length > 0)
    .map((i) => {
      const v = i.versions[i.versions.length - 1]
      const series = priceSeries(observations.filter((o) => o.symbol === i.symbol), 0)
      return {
        symbol: i.symbol,
        name: i.name,
        tradingUnitG: v.trading_unit_g,
        quoteBaseG: v.quotation_base_g,
        fineness: v.price_basis_fineness,
        verified: v.verification === 'verified',
        latest: series?.points.at(-1) ?? null,
      }
    })
}

export function composition(status: DatasetStatus): Composition[] {
  const totals = new Map<string, number>()
  status.contracts.forEach((c) => totals.set(c.symbol, (totals.get(c.symbol) ?? 0) + c.observations))
  return [...totals.entries()]
    .map(([symbol, value]) => ({ symbol, value }))
    .sort((a, b) => b.value - a.value)
}

const VERDICT_RANK: Record<Verdict, number> = {
  historically_validated: 4,
  supported_before_costs_costs_unknown: 3,
  not_supported_after_costs: 2,
  not_supported: 1,
  insufficient_data: 0,
}

/** The series whose last observation is most recent. */
function latestSeries(p: PairResult): Series | null {
  const end = (s: Series) => s.points.at(-1)?.trade_date ?? ''
  return p.series.reduce<Series | null>((best, s) => (!best || end(s) > end(best) ? s : best), null)
}

function pairView(p: PairResult, run: ResearchResponse): PairView {
  const s = latestSeries(p)
  const sum = (r: Record<string, number>) => Object.values(r).reduce((a, b) => a + b, 0)
  return {
    id: p.symbol_pair,
    label: p.symbol_pair,
    legs: s ? `${contractLabel(s.contract_a.split('-')[0], s.expiry_a)} · ${contractLabel(s.contract_b.split('-')[0], s.expiry_b)}` : '',
    verdict: p.verdict,
    points: (s?.points ?? [])
      .filter((pt) => pt.eligible)
      .map((pt) => ({
        date: pt.trade_date,
        spread: pt.spread_bps,
        baseline: pt.baseline_mean_bps,
        std: pt.baseline_std_bps,
        z: pt.z_score,
        deviation: pt.deviation_bps,
      })),
    zThreshold: p.display_params.z_threshold,
    zOptions: run.config.z_thresholds,
    baselineWindow: p.display_params.baseline_window,
    horizon: run.config.horizon,
    minEvents: run.config.min_events,
    holdout: p.final?.signals ?? null,
    holdoutFrom: p.holdout_from,
    holdoutTo: p.holdout_to,
    windows: [...p.folds, ...(p.final ? [p.final] : [])].map((w) => ({ label: w.label, n: w.signals.n })),
    eligibleDates: p.eligible_dates,
    excludedDates: p.series.reduce((n, x) => n + sum(x.ineligible_reasons), 0),
    missingLegDates: p.series.reduce((n, x) => n + x.dates_missing_a.length + x.dates_missing_b.length, 0),
    unknownCosts: run.costs.unknown_components.length,
    roundTripBps: run.costs.round_trip_bps,
  }
}

/** Every tested pair, strongest evidence first: verdict, then holdout signals, then history. */
export function pairViews(run: ResearchResponse): PairView[] {
  return [...run.pairs]
    .sort(
      (a, b) =>
        VERDICT_RANK[b.verdict] - VERDICT_RANK[a.verdict] ||
        (b.final?.signals.n ?? 0) - (a.final?.signals.n ?? 0) ||
        b.eligible_dates - a.eligible_dates,
    )
    .map((p) => pairView(p, run))
}

/** The most recent flagged dates across all pairs. */
export function recentSignals(run: ResearchResponse, limit = 4): SignalView[] {
  return run.pairs
    .flatMap((p) => p.findings)
    .sort((a, b) => b.trade_date.localeCompare(a.trade_date) || Math.abs(b.z_score) - Math.abs(a.z_score))
    .slice(0, limit)
    .map((f) => ({
      id: `${f.pair_id}|${f.trade_date}`,
      pair: f.symbol_pair,
      legs: f.pair_id
        .split('|')
        .map((c) => {
          const [symbol, ...date] = c.split('-')
          return contractLabel(symbol, date.join('-'))
        })
        .join(' · '),
      date: f.trade_date,
      status: f.status,
      z: f.z_score,
      deviation: f.deviation_bps,
      netEdge: f.net_edge_bps,
    }))
}
