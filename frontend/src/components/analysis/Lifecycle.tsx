import { useState } from 'react'
import type { CalendarEntry, ContractStatus, LifecycleResponse, YearlyRow } from '../../api/types'
import { count, day } from '../../lib/format'
import { td, tdNum, th, thNum } from '../tableStyles'
import { ErrorNote, Pill, Placeholder, Table } from '../ui'
import { DiagramCard } from '../ui/ink/kit'
import { useLifecycle } from './useAnalysis'

const LABEL: Record<string, string> = { GOLDM: 'Mini', GOLDTEN: 'Ten', GOLDGUINEA: 'Guinea', GOLDPETAL: 'Petal' }
const COLOR: Record<string, string> = {
  GOLDM: 'var(--color-gold)',
  GOLDTEN: 'var(--color-series-1)',
  GOLDGUINEA: 'var(--color-series-2)',
  GOLDPETAL: 'var(--color-series-3)',
}
const DAY_MS = 86_400_000
const t = (iso: string) => Date.parse(`${iso}T00:00:00Z`)
const monthShort = (iso: string) => new Date(t(iso)).toLocaleDateString('en-IN', { month: 'short', year: '2-digit', timeZone: 'UTC' })

export function LifecycleSections() {
  const { data, error } = useLifecycle()
  if (error) {
    return (
      <DiagramCard className="lg:col-span-12" title="Contract lifecycle">
        <ErrorNote>The lifecycle calendar could not be loaded: {error}</ErrorNote>
      </DiagramCard>
    )
  }
  if (!data) {
    return (
      <DiagramCard className="lg:col-span-12" title="Contract lifecycle">
        <Placeholder className="h-64 w-full" />
      </DiagramCard>
    )
  }
  return (
    <>
      <LifecycleCard lc={data} />
      <YearlyCard lc={data} />
    </>
  )
}

function LifecycleCard({ lc }: { lc: LifecycleResponse }) {
  const [picked, setPicked] = useState<string | null>(null)
  const dates = lc.trade_dates
  const current = picked && dates.includes(picked) ? picked : dates[dates.length - 1]
  const statusToday = lc.status.filter((s) => s.trade_date === current)
  const flagged = statusToday.filter((s) => s.phase !== 'trading')

  return (
    <DiagramCard
      className="lg:col-span-12"
      title="Contract lifecycle"
      description="Listing, tender period and expiry for each contract from the verified MCX specifications. Vertical lines mark the imported trade dates."
      actions={
        dates.length > 0 && (
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
        )
      }
      details={
        <div className="space-y-3">
          <ul className="list-disc space-y-1.5 pl-5">
            {lc.notes.map((n) => (
              <li key={n}>{n}</li>
            ))}
          </ul>
          <CalendarTable entries={lc.calendar} />
        </div>
      }
      detailsSummary={`Dates for all ${lc.calendar.length} contracts`}
    >
      {current && <StatusLine date={current} flagged={flagged} total={statusToday.length} buffer={lc.expiry_buffer_days} />}
      <div className="mt-4 overflow-x-auto">
        <Timeline entries={lc.calendar} tradeDates={dates} current={current} />
      </div>
    </DiagramCard>
  )
}

function StatusLine({ date, flagged, total, buffer }: { date: string; flagged: ContractStatus[]; total: number; buffer: number }) {
  if (flagged.length === 0) {
    return (
      <p className="mt-3 text-[13px] text-ink-2">
        On {day(date)}, none of the {count(total)} imported contracts is in or near its tender period.
      </p>
    )
  }
  return (
    <div className="mt-3 text-[13px] leading-relaxed text-ink-2">
      <p>
        On {day(date)}, {count(flagged.length)} of {count(total)} imported contracts are in or near their tender period:
      </p>
      <ul className="mt-1.5 flex flex-wrap gap-2">
        {flagged.map((s) => {
          const [symbol, ...rest] = s.contract_id.split('-')
          return (
            <li key={s.contract_id} className="inline-flex items-center gap-1.5 rounded-md border border-rule px-2 py-1">
              <span className="text-ink">
                {LABEL[symbol]} {day(rest.join('-'))}
              </span>
              {s.phase === 'tender_period' ? (
                <Pill tone="bad">In tender period</Pill>
              ) : (
                <Pill tone="warn">
                  {s.trading_days_to_expiry} trading days to expiry (inside the {buffer}-day buffer)
                </Pill>
              )}
            </li>
          )
        })}
      </ul>
    </div>
  )
}

function Timeline({ entries, tradeDates, current }: { entries: CalendarEntry[]; tradeDates: string[]; current: string | undefined }) {
  if (entries.length === 0) return null
  const W = 900
  const labelW = 120
  const rowH = 16
  const top = 24
  const H = top + entries.length * rowH + 8
  const lo = Math.min(...entries.map((e) => t(e.listing_date)))
  const hi = Math.max(...entries.map((e) => t(e.expiry))) + 10 * DAY_MS
  const x = (iso: string) => labelW + ((t(iso) - lo) / (hi - lo)) * (W - labelW - 8)
  const months: string[] = []
  const d = new Date(lo)
  d.setUTCDate(1)
  while (d.getTime() <= hi) {
    if (d.getTime() >= lo) months.push(d.toISOString().slice(0, 10))
    d.setUTCMonth(d.getUTCMonth() + 2)
  }

  return (
    <figure className="min-w-[640px]">
      <svg viewBox={`0 0 ${W} ${H}`} className="h-auto w-full" role="img" aria-label="Contract lifecycle timeline">
        {months.map((m) => (
          <g key={m}>
            <line x1={x(m)} x2={x(m)} y1={top - 6} y2={H} stroke="var(--color-rule)" />
            <text x={x(m) + 3} y={12} className="fill-ink-3 text-[10px]">
              {monthShort(m)}
            </text>
          </g>
        ))}
        {entries.map((e, i) => {
          const y = top + i * rowH
          const held = e.contract_id !== null
          return (
            <g key={`${e.symbol}-${e.expiry_month}`} opacity={held ? 1 : 0.45}>
              <text x={0} y={y + 10} className="fill-ink-2 text-[10px]">
                {LABEL[e.symbol]} {monthShort(e.expiry)}
              </text>
              <rect
                x={x(e.listing_date)}
                y={y + 3}
                width={Math.max(x(e.tender_start) - x(e.listing_date), 1)}
                height={8}
                rx={2}
                fill={COLOR[e.symbol]}
                opacity={0.55}
              />
              <rect
                x={x(e.tender_start)}
                y={y + 1}
                width={Math.max(x(e.expiry) - x(e.tender_start), 3)}
                height={12}
                rx={2}
                fill="var(--color-bad)"
              />
              <title>{`${LABEL[e.symbol]} ${day(e.expiry)}: listed ${day(e.listing_date)}, tender period from ${day(e.tender_start)} (${e.tender_trading_days} trading days), expiry ${day(e.expiry)} (${e.expiry_source})${held ? '' : ', not in the imported data'}`}</title>
            </g>
          )
        })}
        {tradeDates.map((td) => (
          <line
            key={td}
            x1={x(td)}
            x2={x(td)}
            y1={top - 6}
            y2={H}
            stroke="var(--color-ink)"
            strokeWidth={td === current ? 1.5 : 1}
            strokeDasharray={td === current ? undefined : '2 3'}
          />
        ))}
      </svg>
      <figcaption className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-ink-2">
        <span className="inline-flex items-center gap-1.5">
          <span className="inline-block h-2 w-4 rounded-sm bg-gold/60" /> trading (colour per contract)
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span className="inline-block h-3 w-2 rounded-sm bg-bad" /> tender period, ending at expiry
        </span>
        <span className="text-ink-3">
          faded: not in the imported data · white line: selected trade date · dates nominal where not imported
        </span>
      </figcaption>
    </figure>
  )
}

function CalendarTable({ entries }: { entries: CalendarEntry[] }) {
  return (
    <div className="overflow-x-auto">
      <Table caption="Lifecycle dates">
        <thead>
          <tr>
            <th className={th}>Contract</th>
            <th className={th}>Listed</th>
            <th className={th}>Tender period from</th>
            <th className={th}>Expiry</th>
            <th className={th}>Specification</th>
          </tr>
        </thead>
        <tbody>
          {entries.map((e) => (
            <tr key={`${e.symbol}-${e.expiry_month}`}>
              <td className={`${td} whitespace-nowrap`}>
                {LABEL[e.symbol]} {monthShort(e.expiry)}
              </td>
              <td className={`${td} num whitespace-nowrap`}>{day(e.listing_date)}</td>
              <td className={`${td} num whitespace-nowrap`}>
                {day(e.tender_start)} <span className="text-ink-3">({e.tender_trading_days} days)</span>
              </td>
              <td className={`${td} num whitespace-nowrap`}>
                {day(e.expiry)} <span className="text-ink-3">{e.expiry_source === 'imported data' ? '' : 'nominal'}</span>
              </td>
              <td className={`${td} whitespace-nowrap text-ink-3`}>{e.spec_version_id}</td>
            </tr>
          ))}
        </tbody>
      </Table>
    </div>
  )
}

// --- Yearly volume ------------------------------------------------------------------------

function YearlyCard({ lc }: { lc: LifecycleResponse }) {
  const symbols = ['GOLDM', 'GOLDTEN', 'GOLDGUINEA', 'GOLDPETAL'].filter((s) => lc.yearly.some((r) => r.symbol === s))
  const first = (s: string) => Math.min(...lc.yearly.filter((r) => r.symbol === s).map((r) => r.year))
  return (
    <DiagramCard
      className="lg:col-span-12"
      title="Liquidity by year"
      description="Value traded per year in each contract (₹ crore, log scale), from the MCX package year-wise table."
      details={lc.yearly.length > 0 && <YearlyTable rows={lc.yearly} />}
      detailsSummary="Year-by-year figures"
    >
      {lc.yearly_problem ? (
        <p className="mt-3 text-[13px] text-ink-2">{lc.yearly_problem}</p>
      ) : (
        <>
          <p className="mt-3 text-[13px] leading-relaxed text-ink-2">
            {symbols.map((s) => `${LABEL[s]} since ${first(s)}`).join(' · ')}. Gold Ten only began trading in 2025, so it has under two
            years of history. The latest year is partial and drawn hollow. Source: {lc.yearly_source}.
          </p>
          <YearlyChart rows={lc.yearly} symbols={symbols} />
        </>
      )}
    </DiagramCard>
  )
}

function YearlyChart({ rows, symbols }: { rows: YearlyRow[]; symbols: string[] }) {
  const W = 720
  const H = 260
  const pad = { l: 64, r: 12, t: 12, b: 28 }
  const years = rows.map((r) => r.year)
  const y0 = Math.min(...years)
  const y1 = Math.max(...years)
  const vals = rows.map((r) => Math.max(r.total_value_crore, 1))
  const lo = Math.floor(Math.log10(Math.min(...vals)))
  const hi = Math.ceil(Math.log10(Math.max(...vals)))
  const x = (yr: number) => pad.l + ((yr - y0) / Math.max(y1 - y0, 1)) * (W - pad.l - pad.r)
  const y = (v: number) => pad.t + (1 - (Math.log10(Math.max(v, 1)) - lo) / Math.max(hi - lo, 1)) * (H - pad.t - pad.b)
  const ticks = Array.from({ length: hi - lo + 1 }, (_, i) => 10 ** (lo + i))

  return (
    <figure className="mt-3 min-w-0">
      <svg viewBox={`0 0 ${W} ${H}`} className="h-auto w-full" role="img" aria-label="Yearly traded value per contract, log scale">
        {ticks.map((v) => (
          <g key={v}>
            <line x1={pad.l} x2={W - pad.r} y1={y(v)} y2={y(v)} stroke="var(--color-rule)" />
            <text x={pad.l - 6} y={y(v) + 4} textAnchor="end" className="fill-ink-3 text-[11px]">
              {v >= 1e5 ? `${v / 1e5}L` : count(v)}
            </text>
          </g>
        ))}
        {Array.from({ length: y1 - y0 + 1 }, (_, i) => y0 + i)
          .filter((yr) => (yr - y0) % 3 === 0 || yr === y1)
          .map((yr) => (
            <text key={yr} x={x(yr)} y={H - 8} textAnchor="middle" className="fill-ink-3 text-[11px]">
              {yr}
            </text>
          ))}
        {symbols.map((s) => {
          const pts = rows.filter((r) => r.symbol === s).sort((a, b) => a.year - b.year)
          return (
            <g key={s}>
              <polyline
                points={pts.map((r) => `${x(r.year)},${y(r.total_value_crore)}`).join(' ')}
                fill="none"
                stroke={COLOR[s]}
                strokeWidth={1.75}
              />
              {pts.map((r) => (
                <circle
                  key={r.year}
                  cx={x(r.year)}
                  cy={y(r.total_value_crore)}
                  r={3}
                  fill={r.partial_year ? 'var(--color-surface)' : COLOR[s]}
                  stroke={COLOR[s]}
                >
                  <title>{`${LABEL[s]} ${r.year}${r.partial_year ? ' (to date)' : ''}: ₹${count(Math.round(r.total_value_crore))} crore, ${count(r.lots_traded)} lots`}</title>
                </circle>
              ))}
            </g>
          )
        })}
      </svg>
      <figcaption className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-ink-2">
        {symbols.map((s) => (
          <span key={s} className="inline-flex items-center gap-1.5">
            <span className="inline-block size-2.5 rounded-full" style={{ background: COLOR[s] }} />
            {LABEL[s]}
          </span>
        ))}
        <span className="text-ink-3">₹ crore per year, log scale (L = lakh crore)</span>
      </figcaption>
    </figure>
  )
}

function YearlyTable({ rows }: { rows: YearlyRow[] }) {
  return (
    <div className="overflow-x-auto">
      <Table caption="Value traded per year">
        <thead>
          <tr>
            <th className={th}>Contract</th>
            <th className={thNum}>Year</th>
            <th className={thNum}>Lots</th>
            <th className={thNum}>Value (₹ crore)</th>
            <th className={thNum}>Trading days</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={`${r.symbol}-${r.year}`}>
              <td className={td}>{LABEL[r.symbol]}</td>
              <td className={tdNum}>
                {r.year}
                {r.partial_year && ' (to date)'}
              </td>
              <td className={tdNum}>{count(r.lots_traded)}</td>
              <td className={tdNum}>{count(Math.round(r.total_value_crore))}</td>
              <td className={tdNum}>{count(r.trading_days)}</td>
            </tr>
          ))}
        </tbody>
      </Table>
    </div>
  )
}
