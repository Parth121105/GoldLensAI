import { useState } from 'react'
import type { Curve, MoveSplit, TermStructureResponse } from '../../api/types'
import { bps, day, money } from '../../lib/format'
import { td, tdNum, th, thNum } from '../tableStyles'
import { Empty, ErrorNote, Notice, Placeholder, Table } from '../ui'
import { DiagramCard } from '../ui/ink/kit'
import { useTermStructure } from './useAnalysis'

const SERIES: Record<string, { label: string; color: string }> = {
  GOLDM: { label: 'Mini', color: 'var(--color-gold)' },
  GOLDTEN: { label: 'Ten', color: 'var(--color-series-1)' },
  GOLDGUINEA: { label: 'Guinea', color: 'var(--color-series-2)' },
  GOLDPETAL: { label: 'Petal', color: 'var(--color-series-3)' },
}

export function TermStructureSection() {
  const { data, error } = useTermStructure()
  return <TermStructure ts={data} error={error} />
}

function TermStructure({ ts, error }: { ts: TermStructureResponse | null; error: string | null }) {
  const [picked, setPicked] = useState<string | null>(null)
  if (error) {
    return (
      <DiagramCard className="lg:col-span-12" title="Term structure and carry">
        <ErrorNote>The futures curves could not be loaded: {error}</ErrorNote>
      </DiagramCard>
    )
  }
  if (!ts) {
    return (
      <DiagramCard className="lg:col-span-12" title="Term structure and carry">
        <Placeholder className="h-56 w-full" />
      </DiagramCard>
    )
  }
  if (ts.curves.length === 0) return null

  const dates = [...new Set(ts.curves.map((c) => c.trade_date))].sort()
  const current = picked && dates.includes(picked) ? picked : dates[dates.length - 1]
  const curves = ts.curves.filter((c) => c.trade_date === current)
  const splits = ts.splits.filter((s) => s.to_date === current)

  return (
    <DiagramCard
      className="lg:col-span-12"
      title={ts.synthetic ? 'Term structure and carry (synthetic data)' : 'Term structure and carry on real data'}
      description="Each contract's futures curve: price per gram at 999 against days to expiry, with a fitted carry line. Below, each contract's move since the previous imported date is split into the gold price move, roll-down toward expiry, the curve changing shape, and what is left."
      actions={
        <label className="flex items-center gap-2 text-sm text-ink-2">
          Trade date
          <select
            className="rounded-md border border-rule bg-sunken px-2 py-1 text-sm text-ink"
            value={current}
            onChange={(e) => setPicked(e.target.value)}
          >
            {dates.map((d) => (
              <option key={d} value={d}>
                {day(d)}
              </option>
            ))}
          </select>
        </label>
      }
      details={
        <ul className="list-disc space-y-1.5 pl-5">
          {ts.method.map((m) => (
            <li key={m}>{m}</li>
          ))}
        </ul>
      }
      detailsSummary="How the curve and the split are calculated"
    >
      {ts.synthetic && <Notice>Synthetic data. These curves are invented.</Notice>}
      <CarryLine date={current} curves={curves} />
      <div className="mt-3 grid gap-6 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        <CurveChart curves={curves} />
        <SlopeTable curves={curves} />
      </div>
      <MoveSplitTable splits={splits} firstDate={dates[0] === current} />
    </DiagramCard>
  )
}

function CarryLine({ date, curves }: { date: string; curves: Curve[] }) {
  const fitted = curves.map((c) => c.annualised_carry_pct)
  const raw = curves.map((c) => c.raw_check_annualised_pct).filter((v): v is number => v != null)
  const mean = fitted.reduce((a, b) => a + b, 0) / fitted.length
  const range = (v: number[]) =>
    Math.min(...v) === Math.max(...v) ? `${v[0].toFixed(1)}%` : `${Math.min(...v).toFixed(1)}–${Math.max(...v).toFixed(1)}%`
  return (
    <p className="mt-3 text-[15px] leading-relaxed text-ink">
      On {day(date)}, later-expiring gold futures cost about {mean.toFixed(0)}% a year more than nearer ones ({range(fitted)} across the{' '}
      {curves.length} contracts).
      {raw.length > 0 && (
        <span className="text-ink-2">
          {' '}
          Cross-checked against the raw MCX closing prices of each contract's nearest and farthest expiry, before any conversion or fitting:{' '}
          {range(raw)}.
        </span>
      )}
    </p>
  )
}

function CurveChart({ curves }: { curves: Curve[] }) {
  const W = 640
  const H = 300
  const pad = { l: 64, r: 16, t: 12, b: 36 }
  const pts = curves.flatMap((c) => c.points)
  const maxT = Math.max(...pts.map((p) => p.days_to_expiry), 30)
  const ys = pts.map((p) => p.inr_per_gram_999)
  const lo = Math.min(...ys)
  const hi = Math.max(...ys)
  const span = Math.max(hi - lo, 1)
  const y0 = lo - span * 0.08
  const y1 = hi + span * 0.08
  const x = (t: number) => pad.l + (t / maxT) * (W - pad.l - pad.r)
  const y = (v: number) => pad.t + (1 - (v - y0) / (y1 - y0)) * (H - pad.t - pad.b)
  const yTicks = Array.from({ length: 5 }, (_, i) => y0 + ((y1 - y0) * i) / 4)
  const xTicks = Array.from({ length: Math.floor(maxT / 30) + 1 }, (_, i) => i * 30)

  return (
    <figure className="min-w-0">
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="h-auto w-full"
        role="img"
        aria-label="Futures curves: price per gram against days to expiry"
      >
        {yTicks.map((v) => (
          <g key={v}>
            <line x1={pad.l} x2={W - pad.r} y1={y(v)} y2={y(v)} stroke="var(--color-rule)" />
            <text x={pad.l - 8} y={y(v) + 4} textAnchor="end" className="fill-ink-3 text-[11px]">
              {money(String(v), 0)}
            </text>
          </g>
        ))}
        {xTicks.map((t) => (
          <text key={t} x={x(t)} y={H - 12} textAnchor="middle" className="fill-ink-3 text-[11px]">
            {t}
          </text>
        ))}
        <text x={W - pad.r} y={H - 0} textAnchor="end" className="fill-ink-3 text-[11px]">
          days to expiry
        </text>
        {curves.map((c) => {
          const s = SERIES[c.symbol]
          const first = c.points[0]
          const last = c.points[c.points.length - 1]
          return (
            <g key={c.symbol}>
              <line
                x1={x(first.days_to_expiry)}
                y1={y(first.fitted)}
                x2={x(last.days_to_expiry)}
                y2={y(last.fitted)}
                stroke={s.color}
                strokeWidth={1.5}
                strokeDasharray="4 4"
                opacity={0.7}
              />
              {c.points.map((p) => (
                <circle
                  key={p.contract_id}
                  cx={x(p.days_to_expiry)}
                  cy={y(p.inr_per_gram_999)}
                  r={4}
                  fill={p.thin ? 'var(--color-surface)' : s.color}
                  stroke={s.color}
                  strokeWidth={1.5}
                >
                  <title>
                    {`${s.label} ${day(p.expiry)}: ₹${money(String(p.inr_per_gram_999))}/g, ${p.days_to_expiry} days, ${bps(p.residual_bps)} bps from its curve${p.thin ? ' (thin)' : ''}`}
                  </title>
                </circle>
              ))}
            </g>
          )
        })}
      </svg>
      <figcaption className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-ink-2">
        {curves.map((c) => (
          <span key={c.symbol} className="inline-flex items-center gap-1.5">
            <span className="inline-block size-2.5 rounded-full" style={{ background: SERIES[c.symbol].color }} />
            {SERIES[c.symbol].label}
          </span>
        ))}
        <span className="text-ink-3">dashed: fitted carry line · hollow: thin contract · ₹ per gram at 999</span>
      </figcaption>
    </figure>
  )
}

function SlopeTable({ curves }: { curves: Curve[] }) {
  return (
    <div className="min-w-0 overflow-x-auto">
      <Table caption="Carry by contract">
        <thead>
          <tr>
            <th className={th}>Contract</th>
            <th className={thNum}>Carry (bps/day)</th>
            <th className={thNum}>Annualised</th>
            <th className={thNum}>Largest deviation</th>
          </tr>
        </thead>
        <tbody>
          {curves.map((c) => (
            <tr key={c.symbol}>
              <td className={td}>{SERIES[c.symbol].label}</td>
              <td className={tdNum}>{c.slope_bps_per_day.toFixed(2)}</td>
              <td className={tdNum}>{c.annualised_carry_pct.toFixed(1)}%</td>
              <td className={tdNum}>{bps(Math.max(...c.points.map((p) => Math.abs(p.residual_bps))))} bps</td>
            </tr>
          ))}
        </tbody>
      </Table>
      <p className="mt-2 text-xs leading-relaxed text-ink-3">
        Carry is the extra price per day of time to expiry. Largest deviation is how far any one expiry sits from its contract's fitted
        line.
      </p>
    </div>
  )
}

function MoveSplitTable({ splits, firstDate }: { splits: MoveSplit[]; firstDate: boolean }) {
  if (splits.length === 0) {
    return (
      <div className="mt-6">
        <Empty>
          {firstDate
            ? 'This is the first imported date, so there is no earlier day to compare against. Pick a later date.'
            : 'No contract appears on both this date and the previous one.'}
        </Empty>
      </div>
    )
  }
  const from = splits[0].from_date
  return (
    <div className="mt-6 overflow-x-auto">
      <Table caption={`Move since ${day(from)}, in bps`}>
        <thead>
          <tr>
            <th className={th}>Contract</th>
            <th className={thNum}>Total</th>
            <th className={thNum}>Gold move</th>
            <th className={thNum}>Roll-down</th>
            <th className={thNum}>Curve change</th>
            <th className={thNum}>Residual</th>
          </tr>
        </thead>
        <tbody>
          {splits.map((s) => (
            <tr key={s.contract_id}>
              <td className={`${td} whitespace-nowrap`}>
                {SERIES[s.symbol].label} {day(s.contract_id.slice(s.contract_id.indexOf('-') + 1))}
              </td>
              <td className={`${tdNum} text-ink`}>{bps(s.total_bps)}</td>
              <td className={tdNum}>{bps(s.gold_move_bps)}</td>
              <td className={tdNum}>{bps(s.roll_down_bps)}</td>
              <td className={tdNum}>{bps(s.curve_change_bps)}</td>
              <td className={`${tdNum} ${Math.abs(s.residual_bps) >= 5 ? 'text-ink' : 'text-ink-3'}`}>{bps(s.residual_bps)}</td>
            </tr>
          ))}
        </tbody>
      </Table>
      <p className="mt-2 text-xs leading-relaxed text-ink-3">
        Gold move is shared by all four contracts. Roll-down is the expected drift as expiry gets closer on an unchanged curve. Curve change
        is the contract's curve shifting or tilting relative to gold. Residual is the contract moving against its own curve, which is where
        a real relative mispricing would show. The four add up to the total.
      </p>
    </div>
  )
}
