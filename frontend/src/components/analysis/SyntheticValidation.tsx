import { useEffect, useState } from 'react'
import { api } from '../../api/client'
import type { SyntheticRun, SyntheticValidationResponse, Verdict } from '../../api/types'
import { bps, count, day } from '../../lib/format'
import { VERDICTS } from '../../lib/labels'
import { td, tdNum, th, thNum } from '../tableStyles'
import { ErrorNote, Notice, Pill, Placeholder, Table } from '../ui'
import { DiagramCard } from '../ui/ink/kit'

const pct = (v: number | null, digits = 1) => (v == null ? '—' : `${(v * 100).toFixed(digits)}%`)
const SHORT: Record<string, string> = { GOLDM: 'Mini', GOLDTEN: 'Ten', GOLDGUINEA: 'Guinea', GOLDPETAL: 'Petal' }
const pairLabel = (p: string) =>
  p
    .split('/')
    .map((s) => SHORT[s] ?? s)
    .join(' / ')

/** The engine scored on controlled synthetic data. Independent of the session's imported data. */
export function SyntheticValidationSection() {
  const [state, setState] = useState<{ data: SyntheticValidationResponse | null; error: string | null }>({ data: null, error: null })
  useEffect(() => {
    let live = true
    api
      .syntheticValidation()
      .then((data) => live && setState({ data, error: null }))
      .catch((e: Error) => live && setState({ data: null, error: e.message }))
    return () => {
      live = false
    }
  }, [])
  const title = 'Engine check on synthetic data'
  if (state.error) {
    return (
      <DiagramCard className="lg:col-span-12" title={title}>
        <ErrorNote>The synthetic validation could not be loaded: {state.error}</ErrorNote>
      </DiagramCard>
    )
  }
  const v = state.data
  if (!v) {
    return (
      <DiagramCard className="lg:col-span-12" title={title} description="Generating the synthetic history and running the walk-forward…">
        <Placeholder className="h-56 w-full" />
      </DiagramCard>
    )
  }
  const [injected, control] = v.runs
  return (
    <DiagramCard
      className="lg:col-span-12"
      title={title}
      description="Does the signal engine find mispricings when they exist, and stay quiet when they don't? Known mispricings were planted in a synthetic market and the unchanged walk-forward was run on it, then on the same market with nothing planted."
      details={
        <div className="space-y-3">
          <ul className="list-disc space-y-1.5 pl-5">
            {v.model.map((m) => (
              <li key={m}>{m}</li>
            ))}
          </ul>
          <p>
            Costs (assumptions, from backend/config/assumptions.json), per leg-side: {injected.cost_labels.join('; ')}. Round trip on two
            legs: {injected.round_trip_cost_bps.toFixed(1)} bps. Delivery making charges: {injected.making_charges_paid}
          </p>
          <PairTable runs={v.runs} />
        </div>
      }
      detailsSummary="How the synthetic market works, costs, and verdicts per pair"
    >
      <Notice>{v.notice}</Notice>
      <div className="mt-4 grid gap-4 md:grid-cols-2">
        <RunPanel run={injected} />
        <RunPanel run={control} />
      </div>
      <CumulativeChart run={injected} />
    </DiagramCard>
  )
}

function Stat({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div>
      <div className="text-xs text-ink-3">{label}</div>
      <div className="num text-lg text-ink">{value}</div>
      {hint && <div className="text-xs text-ink-3">{hint}</div>}
    </div>
  )
}

function RunPanel({ run }: { run: SyntheticRun }) {
  const validated = run.pairs.filter((p) => p.verdict === 'historically_validated').length
  return (
    <div className="rounded-lg border border-rule p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-sm font-medium text-ink">{run.label}</h3>
        <Pill tone={validated ? 'good' : 'neutral'}>
          {validated} of {run.pairs.length} pairs validated
        </Pill>
      </div>
      <p className="mt-1 text-xs text-ink-3">
        {count(run.trade_dates)} trading days ({count(Math.min(...run.pairs.map((p) => p.eligible_dates)))} eligible per pair,{' '}
        {run.eligible_dates_needed} needed). Scored on the unseen holdout{' '}
        {run.holdout_from && run.holdout_to ? `${day(run.holdout_from)} – ${day(run.holdout_to)}` : ''}.
      </p>
      <div className="mt-3 grid grid-cols-2 gap-x-4 gap-y-3 sm:grid-cols-3">
        {run.injected && (
          <Stat
            label="Mispricings caught"
            value={pct(run.catch_rate, 0)}
            hint={`${run.caught} of ${run.injections_in_holdout} in the holdout`}
          />
        )}
        <Stat
          label="False alarms on clean days"
          value={pct(run.false_alarm_rate, 2)}
          hint={`${run.false_alarms} of ${count(run.clean_points)} clean points`}
        />
        <Stat label="Trades" value={count(run.pnl.trades)} />
        <Stat label="Mean per trade, before costs" value={`${bps(run.pnl.mean_gross_bps)} bps`} />
        <Stat
          label="Mean per trade, after costs"
          value={`${bps(run.pnl.mean_net_bps)} bps`}
          hint={`win rate ${pct(run.pnl.hit_rate_net, 0)}`}
        />
        <Stat
          label="Total after costs vs gold move"
          value={`${bps(run.pnl.total_net_bps, 0)} / ${bps(run.pnl.total_gold_move_bps, 0)}`}
          hint={`bps; correlation with gold ${run.pnl.corr_strategy_gold == null ? '—' : (Math.abs(run.pnl.corr_strategy_gold) < 0.005 ? 0 : run.pnl.corr_strategy_gold).toFixed(2)}`}
        />
      </div>
    </div>
  )
}

function CumulativeChart({ run }: { run: SyntheticRun }) {
  const pts = run.cumulative
  if (pts.length < 2) return null
  const W = 720
  const H = 220
  const pad = { l: 56, r: 12, t: 12, b: 28 }
  const vals = pts.flatMap((p) => [p.cumulative_gross_bps, p.cumulative_net_bps, p.cumulative_gold_move_bps])
  const lo = Math.min(0, ...vals)
  const hi = Math.max(0, ...vals)
  const t0 = Date.parse(pts[0].exit)
  const t1 = Date.parse(pts[pts.length - 1].exit)
  const x = (iso: string) => pad.l + ((Date.parse(iso) - t0) / Math.max(t1 - t0, 1)) * (W - pad.l - pad.r)
  const y = (v: number) => pad.t + (1 - (v - lo) / Math.max(hi - lo, 1)) * (H - pad.t - pad.b)
  const line = (key: 'cumulative_gross_bps' | 'cumulative_net_bps' | 'cumulative_gold_move_bps') =>
    pts.map((p) => `${x(p.exit)},${y(p[key])}`).join(' ')
  const ticks = [lo, 0, hi].filter((v, i, a) => a.indexOf(v) === i)
  const series = [
    { key: 'cumulative_net_bps' as const, label: 'Strategy after costs', color: 'var(--color-gold)', width: 2 },
    { key: 'cumulative_gross_bps' as const, label: 'Strategy before costs', color: 'var(--color-ink-3)', width: 1.25 },
    {
      key: 'cumulative_gold_move_bps' as const,
      label: 'Gold price move over the same trades',
      color: 'var(--color-series-1)',
      width: 1.25,
    },
  ]
  return (
    <figure className="mt-5">
      <figcaption className="mb-2 text-sm text-ink-2">
        Cumulative holdout P&L with injected mispricings, in bps of notional per trade, summed. Each trade is short the dear contract and
        long the cheap one in equal grams, priced only from those two contracts, so the gold price move cancels out of it.
      </figcaption>
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="h-auto w-full"
        role="img"
        aria-label="Cumulative synthetic strategy P&L against the gold move"
      >
        {ticks.map((v) => (
          <g key={v}>
            <line x1={pad.l} x2={W - pad.r} y1={y(v)} y2={y(v)} stroke="var(--color-rule)" strokeDasharray={v === 0 ? undefined : '3 3'} />
            <text x={pad.l - 6} y={y(v) + 4} textAnchor="end" className="fill-ink-3 text-[11px]">
              {Math.round(v)}
            </text>
          </g>
        ))}
        <text x={pad.l} y={H - 8} className="fill-ink-3 text-[11px]">
          {day(pts[0].exit)}
        </text>
        <text x={W - pad.r} y={H - 8} textAnchor="end" className="fill-ink-3 text-[11px]">
          {day(pts[pts.length - 1].exit)}
        </text>
        {series.map((s) => (
          <polyline key={s.key} points={line(s.key)} fill="none" stroke={s.color} strokeWidth={s.width} />
        ))}
      </svg>
      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-ink-2">
        {series.map((s) => (
          <span key={s.key} className="inline-flex items-center gap-1.5">
            <span className="inline-block h-0.5 w-4" style={{ background: s.color }} />
            {s.label}
          </span>
        ))}
      </div>
    </figure>
  )
}

function PairTable({ runs }: { runs: SyntheticRun[] }) {
  const pairs = runs[0].pairs.map((p) => p.symbol_pair)
  return (
    <div className="overflow-x-auto">
      <Table caption="Walk-forward verdict per pair">
        <thead>
          <tr>
            <th className={th}>Pair</th>
            {runs.map((r) => (
              <th key={r.label} className={th}>
                {r.injected ? 'With injections' : 'Control'}
              </th>
            ))}
            <th className={thNum}>Chosen z / window</th>
          </tr>
        </thead>
        <tbody>
          {pairs.map((p) => (
            <tr key={p}>
              <td className={`${td} whitespace-nowrap`}>{pairLabel(p)}</td>
              {runs.map((r) => {
                const row = r.pairs.find((x) => x.symbol_pair === p)
                return (
                  <td key={r.label} className={`${td} whitespace-nowrap`}>
                    {row ? (VERDICTS[row.verdict as Verdict]?.label ?? row.verdict) : '—'}
                  </td>
                )
              })}
              <td className={tdNum}>
                {(() => {
                  const row = runs[0].pairs.find((x) => x.symbol_pair === p)
                  return row?.z_threshold != null ? `${row.z_threshold} / ${row.baseline_window}` : '—'
                })()}
              </td>
            </tr>
          ))}
        </tbody>
      </Table>
    </div>
  )
}
