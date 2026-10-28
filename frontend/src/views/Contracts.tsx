import { CalendarX2, Hammer, Hourglass, MapPin, ShieldAlert } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { api } from '../api/client'
import type { ContractCoverage, Instrument, Observation } from '../api/types'
import { TimeChart } from '../components/charts/TimeChart'
import { elbow } from '../components/ui/ink/geometry'
import { DiagramCard, FlowLine, InkGrid, InkHead, InkPage } from '../components/ui/ink/kit'
import { Button, Empty, ErrorNote, Notice, Pill, Placeholder, Table } from '../components/ui'
import { td, tdNum, th, thNum } from '../components/tableStyles'
import { count, day, money, month, monthTick } from '../lib/format'
import { SYMBOL_ORDER } from '../lib/labels'
import { navigate } from '../lib/router'
import { useSession } from '../state/context'

const SERIES_COLORS = ['var(--color-series-1)', 'var(--color-series-2)', 'var(--color-series-3)']
const MAX_SELECTED = 3

export function Contracts() {
  const { instruments, datasets, refreshDatasets } = useSession()
  const list = instruments.data?.instruments
  const contracts = datasets.data?.contracts ?? []
  const basis = instruments.data?.comparison_basis ?? 'INR per gram, 999 fineness equivalent'

  return (
    <InkPage>
      <InkHead
        tag="Contracts"
        title="Four contracts, *one basis*"
        finding={
          <>
            Four MCX gold futures with different sizes, units and fineness, compared on one basis: {basis}.
            {contracts.length > 0 && ` ${count(contracts.length)} contracts are imported.`}
          </>
        }
      />

      <InkGrid>
        <DiagramCard
          className="lg:col-span-7"
          title="Specification hub"
          description="Every contract's quote is converted to INR per gram at 999 fineness from its own specification."
          detailsSummary="Specifications and sources"
          details={list && <SpecDetails instruments={list} contracts={contracts} />}
        >
          {instruments.error ? (
            <ErrorNote>Specifications could not be loaded: {instruments.error}</ErrorNote>
          ) : !list ? (
            <Placeholder className="h-56 w-full" />
          ) : (
            <ContractHub instruments={list} contracts={contracts} />
          )}
        </DiagramCard>

        <DiagramCard
          className="lg:col-span-5"
          title="Coverage"
          description="One cell per imported contract, by symbol and expiry month, shaded by its number of observations."
        >
          {!datasets.data && datasets.error ? (
            <ErrorNote onRetry={() => void refreshDatasets()}>Imported data could not be loaded: {datasets.error}</ErrorNote>
          ) : datasets.loading && !datasets.data ? (
            <Placeholder className="h-40 w-full" />
          ) : contracts.length === 0 ? (
            <Empty action={<Button onClick={() => navigate('/data')}>Import data</Button>}>No contracts imported yet.</Empty>
          ) : (
            <CoverageGrid contracts={contracts} />
          )}
        </DiagramCard>

        <NotAdjusted instruments={list ?? null} error={instruments.error} />

        {!datasets.data && datasets.error ? null : contracts.length > 0 ? (
          <Comparison contracts={contracts} instruments={list ?? []} />
        ) : (
          <DiagramCard className="lg:col-span-12" title="Price comparison" description="Close prices normalized to INR per gram at 999 fineness, one line per contract.">
            {datasets.loading && !datasets.data ? (
              <Placeholder className="h-64 w-full" />
            ) : (
              <Empty action={<Button onClick={() => navigate('/data')}>Import data</Button>}>
                No observations are loaded, so there are no prices to compare.
              </Empty>
            )}
          </DiagramCard>
        )}

        {contracts.length > 0 && <ImportedContracts contracts={contracts} />}
      </InkGrid>
    </InkPage>
  )
}

// --- Specification hub -------------------------------------------------------------------

const HUB = { x: 124, y: 64, w: 112, h: 52 }
const SLOTS = [
  { x: 4, y: 14 },
  { x: 4, y: 126 },
  { x: 248, y: 14 },
  { x: 248, y: 126 },
]
const NODE = { w: 108, h: 40 }

interface HubItem {
  instrument: Instrument
  imported: ContractCoverage[]
}

function monthsCovered(imported: ContractCoverage[]) {
  const months = [...new Set(imported.map((c) => c.expiry.slice(0, 7)))].sort()
  return { n: months.length, from: months[0], to: months.at(-1) }
}

/** The four contracts around the common basis; hovering one lights its path and states its specification. */
function ContractHub({ instruments, contracts }: { instruments: Instrument[]; contracts: ContractCoverage[] }) {
  const items: HubItem[] = [...instruments]
    .sort((a, b) => SYMBOL_ORDER.indexOf(a.symbol) - SYMBOL_ORDER.indexOf(b.symbol))
    .slice(0, SLOTS.length)
    .map((i) => ({ instrument: i, imported: contracts.filter((c) => c.symbol === i.symbol) }))
  const [active, setActive] = useState<string | null>(null)
  const current = items.find((x) => x.instrument.symbol === active)

  return (
    <div className="flex flex-1 flex-col">
      <svg className="ink-diagram mx-auto max-w-[500px]" viewBox="0 0 360 180" role="group" aria-label="Contracts converted to a common basis">
        {items.map((it, k) => {
          const s = SLOTS[k]
          const left = s.x < HUB.x
          const x1 = left ? s.x + NODE.w : s.x
          const x2 = left ? HUB.x : HUB.x + HUB.w
          const y2 = HUB.y + HUB.h / 2 + (s.y < HUB.y ? -8 : 8)
          return <FlowLine key={it.instrument.symbol} d={elbow(x1, s.y + NODE.h / 2, x2, y2, (x1 + x2) / 2)} on={active === it.instrument.symbol} />
        })}
        <g data-on={active ? 'true' : undefined}>
          <rect className="ink-node" x={HUB.x} y={HUB.y} width={HUB.w} height={HUB.h} rx={6} />
          <text x={HUB.x + HUB.w / 2} y={HUB.y + 21} fontSize={8} letterSpacing={1} textAnchor="middle" className="fill-ink-3">COMMON BASIS</text>
          <text x={HUB.x + HUB.w / 2} y={HUB.y + 38} fontSize={11.5} textAnchor="middle" className="num fill-gold">INR / g @999</text>
        </g>
        {items.map((it, k) => {
          const s = SLOTS[k]
          const v = it.instrument.versions[0]
          const sym = it.instrument.symbol
          const on = active === sym
          return (
            <g
              key={sym}
              className="ink-hit ink-lift"
              data-on={on ? 'true' : undefined}
              tabIndex={0}
              role="img"
              aria-label={`${sym}: ${v.trading_unit_g} g lot, ${v.price_basis_fineness} fineness, ${monthsCovered(it.imported).n} expiry months imported`}
              onMouseEnter={() => setActive(sym)}
              onMouseLeave={() => setActive(null)}
              onFocus={() => setActive(sym)}
              onBlur={() => setActive(null)}
            >
              <rect className="ink-node" x={s.x} y={s.y} width={NODE.w} height={NODE.h} rx={4} />
              <text x={s.x + 9} y={s.y + 17} fontSize={10.5} fontWeight={600} className="fill-ink">{sym}</text>
              <text x={s.x + 9} y={s.y + 31} fontSize={8.5} className="num fill-ink-3">
                ₹/{v.quotation_base_g} g · {v.price_basis_fineness}
              </text>
              <text x={s.x + NODE.w - 8} y={s.y + 17} fontSize={9} textAnchor="end" className="num fill-ink-2">{v.trading_unit_g} g</text>
            </g>
          )
        })}
      </svg>

      <div className="mt-3 min-h-[4.5rem]" aria-live="polite">
        {current ? (
          <HubFacts item={current} />
        ) : (
          <p className="pt-2 text-center text-[13px] text-ink-3">Hover or focus a contract for its lot size, fineness and the months imported.</p>
        )}
      </div>
    </div>
  )
}

function HubFacts({ item }: { item: HubItem }) {
  const v = item.instrument.versions[0]
  const m = monthsCovered(item.imported)
  const facts: [string, string][] = [
    ['Lot size', `${v.trading_unit_g} g`],
    ['Fineness', String(v.price_basis_fineness)],
    ['To INR / g @999', `÷ ${v.quotation_base_g}${v.price_basis_fineness === 999 ? '' : ` × 999 / ${v.price_basis_fineness}`}`],
    ['Months covered', m.n === 0 ? 'none imported' : `${count(m.n)} · ${monthTick(`${m.from}-01`)} – ${monthTick(`${m.to}-01`)}`],
  ]
  return (
    <dl className="grid grid-cols-2 gap-x-4 gap-y-2 sm:grid-cols-4">
      {facts.map(([k, val]) => (
        <div key={k} className="ink-chip px-3 py-2">
          <dt className="text-[11px] text-ink-3">{k}</dt>
          <dd className="num text-[13px] font-medium text-ink">{val}</dd>
        </div>
      ))}
    </dl>
  )
}

/** Everything the per-contract specification tiles used to show, kept behind Details. */
function SpecDetails({ instruments, contracts }: { instruments: Instrument[]; contracts: ContractCoverage[] }) {
  return (
    <div className="grid gap-3 sm:grid-cols-2">
      {instruments.map((i) => {
        const v = i.versions[0]
        const imported = contracts.filter((c) => c.symbol === i.symbol)
        const rows: [string, string][] = [
          ['Contract size', `${v.trading_unit_g} g`],
          ['Quoted', `₹ per ${v.quotation_base_g} g at ${v.price_basis_fineness}`],
          ['Normalization', `÷ ${v.quotation_base_g}, ${v.price_basis_fineness === 999 ? '× 1 (already 999)' : `× 999 / ${v.price_basis_fineness}`}`],
          ['Tick size', `₹${v.tick_size_inr} per ${v.quotation_base_g} g`],
          ['Price quote', v.price_quote_location],
          ['Last trading day', v.last_trading_day_text],
          ['Verified for expiries', `${month(v.expiry_from)} – ${month(v.expiry_to)}`],
          [
            'Imported',
            imported.length > 0
              ? `${count(imported.length)} contracts, ${count(imported.reduce((n, c) => n + c.observations, 0))} observations`
              : 'None',
          ],
        ]
        return (
          <article key={i.symbol} className="ink-chip space-y-2 p-3.5">
            <header className="flex items-baseline justify-between gap-2">
              <h3 className="text-[14px] font-semibold text-ink">
                {i.symbol} <span className="font-normal text-ink-3">· {i.name}</span>
              </h3>
              {v.verification === 'verified' ? <Pill tone="good">Verified</Pill> : <Pill tone="warn">Unverified</Pill>}
            </header>
            <dl className="space-y-1">
              {rows.map(([k, val]) => (
                <div key={k} className="grid grid-cols-[8.5rem_minmax(0,1fr)] gap-2">
                  <dt className="text-ink-3">{k}</dt>
                  <dd className="text-ink">{val}</dd>
                </div>
              ))}
            </dl>
            <ul className="space-y-0.5 border-t border-rule pt-2 text-xs">
              {v.sources.map((s) => (
                <li key={s.id}>
                  <span className="font-medium text-ink" title={s.retrieved_from}>{s.id}</span>{' '}
                  · {s.location}
                </li>
              ))}
              {i.versions.length > 1 && <li className="text-ink-3">{count(i.versions.length - 1)} further specification versions</li>}
            </ul>
          </article>
        )
      })}
    </div>
  )
}

// --- What is not adjusted --------------------------------------------------------------

/** The differences GoldLensAI reports but never corrects for, written from the specifications. */
function NotAdjusted({ instruments, error }: { instruments: Instrument[] | null; error: string | null }) {
  const byLocation = new Map<string, string[]>()
  instruments?.forEach((i) => {
    const loc = i.versions[0]?.price_quote_location
    if (loc) byLocation.set(loc, [...(byLocation.get(loc) ?? []), i.symbol])
  })
  const locations = [...byLocation.entries()].sort((a, b) => a[1].length - b[1].length)
  const goldten = instruments?.find((i) => i.symbol === 'GOLDTEN')?.first_trading_date
  const items: [LucideIcon, string, string][] = [
    [
      MapPin,
      'Location basis',
      locations.length > 1
        ? `${locations.map(([loc, syms]) => `${syms.join(', ')} ${syms.length === 1 ? 'is' : 'are'} priced ${loc}`).join('; ')}; the difference is not adjusted.`
        : 'Contracts are priced at different delivery locations; the difference is not adjusted.',
    ],
    [Hammer, 'Making charges', 'The cost of making coins and bars is not adjusted.'],
    [Hourglass, 'Carry', 'The cost of holding gold until expiry is not adjusted.'],
    [CalendarX2, 'Before first trading', `GOLDTEN first traded on ${day(goldten)}; earlier GOLDTEN rows are rejected on import.`],
    [ShieldAlert, 'Unverified specifications', 'Contracts outside a verified specification window are not normalized.'],
  ]
  return (
    <DiagramCard className="lg:col-span-12" title="What is not adjusted" description="Differences between the contracts that GoldLensAI reports but never corrects for.">
      {error && !instruments && <ErrorNote>Specifications could not be loaded: {error}</ErrorNote>}
      <ul className="grid grid-cols-1 gap-2.5 sm:grid-cols-2 lg:grid-cols-5">
        {items.map(([Icon, title, text]) => (
          <li key={title} className="ink-chip flex flex-col gap-2 p-3.5">
            <span className="grid size-8 place-items-center border border-rule-strong bg-ground text-gold">
              <Icon className="size-4" aria-hidden="true" />
            </span>
            <span className="text-[13px] font-medium text-ink">{title}</span>
            <span className="text-xs leading-relaxed text-ink-3">{text}</span>
          </li>
        ))}
      </ul>
    </DiagramCard>
  )
}

// --- Compact coverage grid ------------------------------------------------------------------

function CoverageGrid({ contracts }: { contracts: ContractCoverage[] }) {
  const [active, setActive] = useState<ContractCoverage | null>(null)
  const months = useMemo(() => {
    const keys = contracts.map((c) => c.expiry.slice(0, 7)).sort()
    const out: string[] = []
    let [y, m] = keys[0].split('-').map(Number)
    for (;;) {
      const key = `${y}-${String(m).padStart(2, '0')}`
      out.push(key)
      if (key >= keys.at(-1)!) return out
      m += 1
      if (m > 12) {
        m = 1
        y += 1
      }
    }
  }, [contracts])
  const symbols = SYMBOL_ORDER.filter((s) => contracts.some((c) => c.symbol === s))
  const cell = new Map(contracts.map((c) => [`${c.symbol}|${c.expiry.slice(0, 7)}`, c]))
  const max = Math.max(...contracts.map((c) => c.observations), 1)

  return (
    <div className="flex flex-1 flex-col">
      <div className="overflow-x-auto">
        <table className="w-full table-fixed border-separate border-spacing-[3px]" onMouseLeave={() => setActive(null)}>
          <caption className="sr-only">Imported contracts by symbol and expiry month, shaded by observations</caption>
          <thead>
            <tr>
              <th scope="col" className="w-[5.5rem]"><span className="sr-only">Symbol</span></th>
              {months.map((m) => (
                <th key={m} scope="col" className="p-0">
                  <span className="sr-only">{monthTick(`${m}-01`)}</span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {symbols.map((s) => (
              <tr key={s}>
                <th scope="row" className="pr-2 text-left text-[11px] font-medium whitespace-nowrap text-ink-2">{s}</th>
                {months.map((m) => {
                  const c = cell.get(`${s}|${m}`)
                  if (!c) return <td key={m} className="h-6 border border-dashed border-rule"><span className="sr-only">none</span></td>
                  const verified = c.spec_status === 'verified'
                  return (
                    <td
                      key={m}
                      onMouseEnter={() => setActive(c)}
                      aria-label={`${c.contract_id}: ${count(c.observations)} observations, ${verified ? 'verified' : 'unverified'}`}
                      className="h-6 cursor-default border"
                      style={{
                        borderColor: active?.contract_id === c.contract_id ? 'var(--color-ink)' : verified ? 'color-mix(in oklch, var(--color-gold) 45%, transparent)' : 'var(--color-loss)',
                        background: verified ? `color-mix(in oklch, var(--color-gold) ${Math.round(20 + (c.observations / max) * 70)}%, transparent)` : 'transparent',
                      }}
                    />
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-3 min-h-[2.6em] text-[13px] text-ink-2" aria-live="polite">
        {active
          ? `${active.symbol} exp. ${day(active.expiry)}: ${count(active.observations)} observations (${count(active.traded_observations)} traded), ${day(active.first_trade_date)} – ${day(active.last_trade_date)}, specification ${active.spec_status}.`
          : `${count(contracts.length)} contracts across ${count(months.length)} expiry months, ${monthTick(`${months[0]}-01`)} – ${monthTick(`${months.at(-1)}-01`)}. Hover a cell for its contract.`}
      </p>
      <ul className="mt-auto flex flex-wrap gap-x-4 gap-y-1 text-xs text-ink-3" aria-label="Key">
        <li className="flex items-center gap-1.5"><span aria-hidden="true" className="inline-block size-2.5 bg-gold/70" />Verified, darker = more observations</li>
        <li className="flex items-center gap-1.5"><span aria-hidden="true" className="inline-block size-2.5 border border-loss" />Unverified</li>
        <li className="flex items-center gap-1.5"><span aria-hidden="true" className="inline-block size-2.5 border border-dashed border-rule-strong" />None</li>
      </ul>
    </div>
  )
}

// --- Full contract table, behind "Show all" ----------------------------------------------------

function ImportedContracts({ contracts }: { contracts: ContractCoverage[] }) {
  const [open, setOpen] = useState(false)
  const sorted = [...contracts].sort(bySymbolOrder)
  return (
    <DiagramCard
      className="lg:col-span-12"
      title="Imported contracts"
      description="Each row is one symbol and expiry; expiries are never joined into a continuous series."
      actions={
        <Button variant="quiet" onClick={() => setOpen((o) => !o)}>
          {open ? 'Hide table' : `Show all ${count(sorted.length)} contracts`}
        </Button>
      }
    >
      {open && (
        <Table caption="Imported contracts and their coverage">
          <thead>
            <tr>
              <th className={th}>Contract</th>
              <th className={th}>Expiry</th>
              <th className={th}>First – last trade date</th>
              <th className={thNum}>Observations</th>
              <th className={thNum}>Traded</th>
              <th className={th}>Specification</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((c) => (
              <tr key={c.contract_id}>
                <td className={`${td} font-medium`}>{c.symbol}</td>
                <td className={`${td} num whitespace-nowrap`}>{day(c.expiry)}</td>
                <td className={`${td} num whitespace-nowrap text-ink-2`}>{day(c.first_trade_date)} – {day(c.last_trade_date)}</td>
                <td className={tdNum}>{count(c.observations)}</td>
                <td className={tdNum}>{count(c.traded_observations)}</td>
                <td className={td}>{c.spec_status === 'verified' ? <Pill tone="good">Verified</Pill> : <Pill tone="warn">Unverified</Pill>}</td>
              </tr>
            ))}
          </tbody>
        </Table>
      )}
    </DiagramCard>
  )
}

const bySymbolOrder = (a: ContractCoverage, b: ContractCoverage) =>
  SYMBOL_ORDER.indexOf(a.symbol) - SYMBOL_ORDER.indexOf(b.symbol) || a.expiry.localeCompare(b.expiry)

/** Default to comparable contracts: the expiry month shared by the most symbols, best covered. */
function defaultSelection(contracts: ContractCoverage[]): string[] {
  const months = new Map<string, ContractCoverage[]>()
  contracts.forEach((c) => months.set(c.expiry.slice(0, 7), [...(months.get(c.expiry.slice(0, 7)) ?? []), c]))
  const score = (list: ContractCoverage[]) => new Set(list.map((c) => c.symbol)).size * 1e6 + list.reduce((n, c) => n + c.observations, 0)
  const best = [...months.values()].sort((a, b) => score(b) - score(a))[0] ?? []
  const one = new Map<string, ContractCoverage>()
  best.forEach((c) => one.set(c.symbol, c))
  // Month-end contracts first, so the default compares same-expiry contracts.
  return [...one.values()].sort((a, b) => b.expiry.localeCompare(a.expiry) || bySymbolOrder(a, b)).slice(0, MAX_SELECTED).sort(bySymbolOrder).map((c) => c.contract_id)
}

function Comparison({ contracts, instruments }: { contracts: ContractCoverage[]; instruments: Instrument[] }) {
  // Fixed colour slots: a contract keeps its colour while selected, whatever else changes.
  const [slots, setSlots] = useState<(string | null)[]>(() => {
    const d = defaultSelection(contracts)
    return Array.from({ length: MAX_SELECTED }, (_, i) => d[i] ?? null)
  })
  const selected = slots.filter((x): x is string => x != null)
  const colorOf = (id: string) => SERIES_COLORS[slots.indexOf(id)]
  const [view, setView] = useState<'chart' | 'table'>('chart')
  // Rows are tagged with the selection they were loaded for, so a stale response is never charted.
  const [loaded, setLoaded] = useState<{ key: string; rows: Observation[]; dates: string[] } | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [showAll, setShowAll] = useState(false)

  const chosen = contracts.filter((c) => selected.includes(c.contract_id)).sort(bySymbolOrder)
  const key = [...selected].sort().join(',')

  useEffect(() => {
    if (selected.length === 0) return
    let live = true
    const picked = contracts.filter((c) => selected.includes(c.contract_id))
    api
      .observations([...new Set(picked.map((c) => c.symbol))], [...new Set(picked.map((c) => c.expiry))])
      .then((r) => {
        if (!live) return
        setLoaded({ key, rows: r.observations.filter((o) => selected.includes(o.contract_id)), dates: r.trade_dates })
        setError(null)
      })
      .catch((e: unknown) => live && setError(e instanceof Error ? e.message : 'Could not load observations.'))
    return () => {
      live = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key])

  const toggle = (id: string) =>
    setSlots((s) => {
      if (s.includes(id)) return s.map((x) => (x === id ? null : x))
      const free = s.indexOf(null)
      return free === -1 ? s : s.map((x, i) => (i === free ? id : x))
    })

  const model = useMemo(() => {
    if (!loaded || loaded.key !== key || chosen.length === 0) return null
    const { rows, dates: sessionDates } = loaded
    const first = chosen.map((c) => c.first_trade_date).sort()[0]
    const last = chosen.map((c) => c.last_trade_date).sort().at(-1)!
    const dates = sessionDates.filter((d) => d >= first && d <= last)
    const byContract = new Map(chosen.map((c) => [c.contract_id, new Map<string, Observation>()]))
    rows.forEach((o) => byContract.get(o.contract_id)?.set(o.trade_date, o))
    const series = chosen.map((c) => {
      const obs = byContract.get(c.contract_id)!
      const inLife = dates.filter((d) => d >= c.first_trade_date && d <= c.last_trade_date)
      return {
        contract: c,
        color: colorOf(c.contract_id),
        obs,
        missing: inLife.filter((d) => !obs.has(d)).length,
        unnormalized: [...obs.values()].filter((o) => !o.normalized),
        values: dates.map((d) => {
          const n = obs.get(d)?.normalized
          return n ? Number(n.inr_per_gram_999) : null
        }),
      }
    })
    return { dates, series }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loaded, key])

  const bySymbol = useMemo(() => {
    const m = new Map<string, ContractCoverage[]>()
    ;[...contracts].sort(bySymbolOrder).forEach((c) => m.set(c.symbol, [...(m.get(c.symbol) ?? []), c]))
    return [...m.entries()]
  }, [contracts])

  const specFor = (symbol: string) => instruments.find((i) => i.symbol === symbol)?.versions[0]

  return (
    <DiagramCard
      className="lg:col-span-12"
      title="Price comparison"
      description="Close prices normalized by the backend to INR per gram at 999 fineness, one line per contract; drag across the chart to read values."
      detailsSummary="How to read it"
      details={
        <div className="space-y-2">
          <p>Each line is one contract; a gap means no observation that day.</p>
          <p>
            Raw quotes use different units (per 10 g, 8 g or 1 g; 995 or 999 fineness) and are only shown in the table, never
            plotted on a shared axis. Close is MCX's last-half-hour weighted average, not a synchronized executable quote.
          </p>
        </div>
      }
      actions={
        <div role="group" aria-label="View" className="flex rounded-full border border-rule p-0.5">
          {(['chart', 'table'] as const).map((v) => (
            <button
              key={v}
              type="button"
              aria-pressed={view === v}
              onClick={() => setView(v)}
              className={`rounded-full px-2.5 py-1 font-mono text-[11px] capitalize ${view === v ? 'bg-ink font-medium text-ground' : 'text-ink-3 hover:text-ink'}`}
            >
              {v}
            </button>
          ))}
        </div>
      }
    >
      <fieldset>
        <legend className="mb-2 text-xs text-ink-3">Contracts (choose up to {MAX_SELECTED})</legend>
        <div className="flex flex-wrap gap-x-5 gap-y-2">
          {bySymbol.map(([symbol, list]) => (
            <div key={symbol} className="flex flex-wrap items-center gap-1.5">
              <span className="w-24 text-xs font-medium text-ink">{symbol}</span>
              {list.map((c) => {
                const on = selected.includes(c.contract_id)
                const color = on ? colorOf(c.contract_id) : undefined
                return (
                  <label
                    key={c.contract_id}
                    data-on={on ? 'true' : undefined}
                    className={`ink-chip num flex cursor-pointer items-center gap-1.5 px-1.5 py-0.5 text-xs ${on ? 'text-ink' : 'text-ink-2'} ${!on && selected.length >= MAX_SELECTED ? 'opacity-50' : ''}`}
                  >
                    <input type="checkbox" className="sr-only" checked={on} onChange={() => toggle(c.contract_id)} />
                    <span aria-hidden="true" className="inline-block size-2 rounded-full border border-rule-strong" style={color ? { background: color, borderColor: color } : undefined} />
                    {day(c.expiry)}
                  </label>
                )
              })}
            </div>
          ))}
        </div>
      </fieldset>

      {error ? (
        <ErrorNote>{error}</ErrorNote>
      ) : selected.length === 0 ? (
        <Empty>Select at least one contract.</Empty>
      ) : !model ? (
        <Placeholder className="h-64 w-full" />
      ) : (
        <div className="space-y-3">
          <ul className="flex flex-wrap gap-x-5 gap-y-1 text-xs text-ink-2" aria-label="Legend">
            {model.series.map((s) => (
              <li key={s.contract.contract_id} className="flex items-center gap-1.5">
                <span aria-hidden="true" className="inline-block h-0.5 w-4" style={{ background: s.color }} />
                <span className="font-medium text-ink">{s.contract.symbol}</span> exp. {day(s.contract.expiry)}
                <span className="text-ink-3">· {count(s.obs.size)} obs, {count(s.missing)} missing</span>
              </li>
            ))}
          </ul>

          {view === 'chart' ? (
            <TimeChart
              dates={model.dates}
              unit="INR / g @999"
              formatValue={(v) => money(String(v), 0)}
              description={`Normalized close prices in INR per gram at 999 fineness for ${model.series.map((s) => `${s.contract.symbol} expiring ${day(s.contract.expiry)}`).join(', ')}.`}
              series={model.series.map((s) => ({
                id: s.contract.contract_id,
                label: `${s.contract.symbol} ${s.contract.expiry.slice(0, 7)}`,
                color: s.color,
                values: s.values,
              }))}
            />
          ) : (
            <ObservationTable model={model} specFor={specFor} showAll={showAll} onShowAll={() => setShowAll(true)} />
          )}

          {model.series.some((s) => s.unnormalized.length > 0) && (
            <Notice>
              {model.series
                .filter((s) => s.unnormalized.length > 0)
                .map((s) => `${s.contract.symbol} exp. ${day(s.contract.expiry)}: ${s.unnormalized.length} observations not normalized (${s.unnormalized[0].normalization_error})`)
                .join(' ')}
            </Notice>
          )}
        </div>
      )}
    </DiagramCard>
  )
}

interface Model {
  dates: string[]
  series: { contract: ContractCoverage; obs: Map<string, Observation>; color: string }[]
}

function ObservationTable({
  model,
  specFor,
  showAll,
  onShowAll,
}: {
  model: Model
  specFor: (s: string) => Instrument['versions'][number] | undefined
  showAll: boolean
  onShowAll: () => void
}) {
  const dates = [...model.dates].reverse()
  const visible = showAll ? dates : dates.slice(0, 40)
  return (
    <>
      <Table caption="Raw and normalized close prices by date">
        <thead>
          <tr>
            <th className={th} rowSpan={2}>Trade date</th>
            {model.series.map((s) => (
              <th key={s.contract.contract_id} className={`${th} text-center text-ink`} colSpan={2}>
                {s.contract.symbol} exp. {day(s.contract.expiry)}
              </th>
            ))}
          </tr>
          <tr>
            {model.series.map((s) => {
              const spec = specFor(s.contract.symbol)
              return [
                <th key="raw" className={thNum}>Close, INR / {spec?.quotation_base_g ?? '?'} g @{spec?.price_basis_fineness ?? '?'}</th>,
                <th key="norm" className={thNum}>INR / g @999</th>,
              ]
            })}
          </tr>
        </thead>
        <tbody>
          {visible.map((d) => (
            <tr key={d}>
              <td className={`${td} num whitespace-nowrap`}>{day(d)}</td>
              {model.series.map((s) => {
                const o = s.obs.get(d)
                return [
                  <td key="raw" className={tdNum} title={o ? `${o.source_file}, line ${o.line_number}` : undefined}>
                    {o ? money(o.close, 0) : <span className="text-ink-3">no obs.</span>}
                    {o && o.traded === false && <Pill>no trades</Pill>}
                  </td>,
                  <td key="norm" className={tdNum} title={o?.normalized?.formula}>
                    {o?.normalized ? money(o.normalized.inr_per_gram_999) : <span className="text-ink-3">—</span>}
                  </td>,
                ]
              })}
            </tr>
          ))}
        </tbody>
      </Table>
      {!showAll && dates.length > visible.length && (
        <Button variant="quiet" onClick={onShowAll}>Show all {count(dates.length)} dates</Button>
      )}
      <p className="text-xs text-ink-3">Hover a value to see its source file and line, or the normalization formula.</p>
    </>
  )
}
