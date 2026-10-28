import { useCallback, useEffect, useMemo, useState } from 'react'
import { api } from '../api/client'
import type { ContractCoverage, Observation } from '../api/types'
import { BentoGrid, BentoTile } from '../components/Bento'
import { GoldBento } from '../components/ui/gold-bento'
import type { ResearchState } from '../components/ui/gold-bento'
import { Button, ErrorNote } from '../components/ui'
import { useRelativeValue, useTermStructure, useVerdict } from '../components/analysis/useAnalysis'
import { composition, instrumentCards, pairViews, priceSeries, recentSignals, sameDayView } from '../lib/bento-data'
import { count, day, monthTick } from '../lib/format'
import { SYMBOL_ORDER } from '../lib/labels'
import { navigate } from '../lib/router'
import { useSession } from '../state/context'

export function Overview() {
  const { datasets, research, instruments, refreshDatasets, refreshResearch } = useSession()
  const status = datasets.data
  const run = research.data
  const hasData = !!status && status.observations > 0
  const [observations, setObservations] = useState<{ key: string; list: Observation[] } | null>(null)
  const [busy, setBusy] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)

  // Observations are refetched whenever the set of imported files changes.
  const key = status ? `${status.observations}|${status.files.map((f) => f.source_sha256).join(',')}` : ''
  useEffect(() => {
    if (!hasData) return
    let live = true
    api
      .observations([], [])
      .then((r) => live && setObservations({ key, list: r.observations }))
      .catch((e: unknown) => live && setActionError(e instanceof Error ? e.message : 'Observations could not be loaded.'))
    return () => {
      live = false
    }
  }, [key, hasData])

  const list = hasData && observations?.key === key ? observations.list : null
  const price = useMemo(() => (list ? priceSeries(list) : null), [list])
  const cards = useMemo(() => instrumentCards(instruments.data?.instruments ?? [], list ?? []), [instruments.data, list])
  const pairs = useMemo(() => (run ? pairViews(run) : []), [run])
  const signals = useMemo(() => (run ? recentSignals(run) : []), [run])
  const relativeValue = useRelativeValue().data
  const termStructure = useTermStructure().data
  const neededDates = useVerdict().data?.needed_per_pair ?? null
  const sameDay = useCallback((pairId: string) => sameDayView(pairId, relativeValue, termStructure), [relativeValue, termStructure])

  const researchState: ResearchState = research.loading && !run ? 'loading' : run ? 'ready' : 'none'
  const loading = (!status && !datasets.error) || (hasData && !list && !actionError)

  async function loadDemo() {
    setBusy(true)
    setActionError(null)
    try {
      await api.loadDemo()
      await Promise.all([refreshDatasets(), refreshResearch()])
    } catch (e) {
      setActionError(e instanceof Error ? e.message : 'The demo could not be loaded.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-3">
      {!status && datasets.error && <ErrorNote onRetry={() => void refreshDatasets()}>{datasets.error}</ErrorNote>}
      {actionError && <ErrorNote>{actionError}</ErrorNote>}
      {research.error && <ErrorNote onRetry={() => void refreshResearch()}>{research.error}</ErrorNote>}

      <GoldBento
        kind={status?.kind}
        loading={loading}
        price={price}
        instruments={cards}
        composition={status ? composition(status) : []}
        research={researchState}
        pairs={pairs}
        signals={signals}
        sameDay={sameDay}
        neededDates={neededDates}
        bundled={status?.bundled}
        busy={busy}
        onLoadDemo={status?.kind === 'user_uploaded' ? undefined : () => void loadDemo()}
        onImport={() => navigate('/data')}
        onRunResearch={() => navigate('/research')}
        onOpenEvidence={() => navigate('/research')}
      />

      {hasData && (
        <BentoGrid>
          <BentoTile
            span={12}
            title="Contract coverage"
            meta="One cell per contract, by symbol and expiry month, showing accepted observations. Expiries are never joined into a continuous series."
            actions={<Button variant="quiet" onClick={() => navigate('/contracts')}>Compare prices</Button>}
          >
            <CoverageCalendar contracts={status.contracts} />
          </BentoTile>
        </BentoGrid>
      )}
    </div>
  )
}

// --- Coverage calendar ------------------------------------------------------------

function months(contracts: ContractCoverage[]): string[] {
  const keys = contracts.map((c) => c.expiry.slice(0, 7)).sort()
  if (keys.length === 0) return []
  const out: string[] = []
  let [y, m] = keys[0].split('-').map(Number)
  const last = keys.at(-1)!
  for (;;) {
    const key = `${y}-${String(m).padStart(2, '0')}`
    out.push(key)
    if (key >= last) return out
    m += 1
    if (m > 12) {
      m = 1
      y += 1
    }
  }
}

function CoverageCalendar({ contracts }: { contracts: ContractCoverage[] }) {
  const cols = months(contracts)
  const cell = new Map<string, ContractCoverage[]>()
  contracts.forEach((c) => {
    const k = `${c.symbol}|${c.expiry.slice(0, 7)}`
    cell.set(k, [...(cell.get(k) ?? []), c])
  })
  const symbols = SYMBOL_ORDER.filter((s) => contracts.some((c) => c.symbol === s))
  const unverified = contracts.filter((c) => c.spec_status !== 'verified').length

  return (
    <div className="space-y-3">
      <div className="relative -mx-5 overflow-x-auto px-5">
        <table className="w-full border-separate border-spacing-[3px] text-[13px]">
          <caption className="sr-only">Accepted observations per contract, by symbol and expiry month</caption>
          <thead>
            <tr>
              <th scope="col" className="sticky left-0 z-10 bg-surface pr-3 text-left text-xs font-normal text-ink-3">Symbol</th>
              {cols.map((m) => (
                <th key={m} scope="col" className="min-w-14 px-1 pb-1 text-center text-xs font-normal whitespace-nowrap text-ink-3">
                  {monthTick(`${m}-01`)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {symbols.map((s) => (
              <tr key={s}>
                <th scope="row" className="sticky left-0 z-10 bg-surface pr-3 text-left font-medium whitespace-nowrap text-ink">{s}</th>
                {cols.map((m) => {
                  const list = cell.get(`${s}|${m}`)
                  if (!list) {
                    return (
                      <td key={m} className="h-11 rounded border border-dashed border-rule text-center">
                        <span className="sr-only">No contract</span>
                      </td>
                    )
                  }
                  const ok = list.every((c) => c.spec_status === 'verified')
                  const obs = list.reduce((n, c) => n + c.observations, 0)
                  return (
                    <td
                      key={m}
                      title={list.map((c) => `${c.contract_id}: ${count(c.observations)} observations (${count(c.traded_observations)} traded), ${day(c.first_trade_date)} – ${day(c.last_trade_date)}, specification ${c.spec_status}`).join('\n')}
                      className={`num h-11 rounded text-center font-medium ${ok ? 'border-t border-gold/35 bg-sunken text-ink' : 'bg-warn-soft text-warn'}`}
                    >
                      {count(obs)}
                      <span className="sr-only"> observations, expiry {list.map((c) => day(c.expiry)).join(', ')}, {ok ? 'verified' : 'unverified'} specification</span>
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <ul className="flex flex-wrap gap-x-5 gap-y-1 text-xs text-ink-2" aria-label="Key">
        <li className="flex items-center gap-1.5"><span aria-hidden="true" className="inline-block size-2.5 rounded-[3px] border-t border-gold/60 bg-sunken" />Verified specification</li>
        <li className="flex items-center gap-1.5"><span aria-hidden="true" className="inline-block size-2.5 rounded-[3px] bg-warn-soft ring-1 ring-warn/50" />Unverified: not normalized{unverified > 0 ? ` (${count(unverified)})` : ''}</li>
        <li className="flex items-center gap-1.5"><span aria-hidden="true" className="inline-block size-2.5 rounded-[3px] border border-dashed border-rule-strong" />No contract imported</li>
      </ul>
    </div>
  )
}

