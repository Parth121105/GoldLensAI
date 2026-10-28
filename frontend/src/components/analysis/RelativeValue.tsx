import { useState } from 'react'
import type { ContractQuote, PairGap, RelativeValueResponse } from '../../api/types'
import { bps, count, day, money } from '../../lib/format'
import { td, tdNum, th, thNum } from '../tableStyles'
import { ErrorNote, Notice, Pill, Placeholder, Table } from '../ui'
import { DiagramCard } from '../ui/ink/kit'
import { useRelativeValue } from './useAnalysis'

const SHORT: Record<string, string> = {
  GOLDM: 'Mini',
  GOLDTEN: 'Ten',
  GOLDGUINEA: 'Guinea',
  GOLDPETAL: 'Petal',
}

function expiryLabel(contractId: string): string {
  const iso = contractId.slice(contractId.indexOf('-') + 1)
  return day(iso)
}

export function RelativeValue({ rv, error }: { rv: RelativeValueResponse | null; error: string | null }) {
  const [picked, setPicked] = useState<string | null>(null)
  const [pairFilter, setPairFilter] = useState('all')
  if (error) {
    return (
      <DiagramCard className="lg:col-span-12" title="Relative value">
        <ErrorNote>Relative value could not be loaded: {error}</ErrorNote>
      </DiagramCard>
    )
  }
  if (!rv) {
    return (
      <DiagramCard className="lg:col-span-12" title="Relative value">
        <Placeholder className="h-40 w-full" />
      </DiagramCard>
    )
  }
  if (rv.days.length === 0) return null

  const dates = rv.days.map((d) => d.trade_date)
  const current = rv.days.find((d) => d.trade_date === picked) ?? rv.days[rv.days.length - 1]
  const byId = new Map(current.contracts.map((q) => [q.contract_id, q]))
  const thin = current.contracts.filter((q) => q.thin).length
  const pairNames = [...new Set(current.pairs.map((p) => `${p.symbol_a}/${p.symbol_b}`))]
  const shown = current.pairs.filter((p) => pairFilter === 'all' || `${p.symbol_a}/${p.symbol_b}` === pairFilter)
  const selectClass = 'rounded-md border border-rule bg-sunken px-2 py-1 text-sm text-ink'

  return (
    <DiagramCard
      className="lg:col-span-12"
      title={rv.synthetic ? 'Relative value (synthetic data)' : 'Relative value on real data'}
      description={`Each contract converted to ₹ per gram at 999 purity, then paired with the nearest expiry of each other contract (at most ${rv.liquidity.max_expiry_gap_days} days apart). Gap = 10,000 × ln(A ÷ B) in basis points; positive means A is dearer.`}
      actions={
        <>
          <label className="flex items-center gap-2 text-sm text-ink-2">
            Pair
            <select className={selectClass} value={pairFilter} onChange={(e) => setPairFilter(e.target.value)}>
              <option value="all">All pairs</option>
              {pairNames.map((n) => {
                const [a, b] = n.split('/')
                return (
                  <option key={n} value={n}>
                    {SHORT[a]} / {SHORT[b]}
                  </option>
                )
              })}
            </select>
          </label>
          <label className="flex items-center gap-2 text-sm text-ink-2">
            Trade date
            <select className={selectClass} value={current.trade_date} onChange={(e) => setPicked(e.target.value)}>
              {dates.map((d) => (
                <option key={d} value={d}>
                  {day(d)}
                </option>
              ))}
            </select>
          </label>
        </>
      }
      details={<NormalizedPrices contracts={current.contracts} liquidity={rv.liquidity} />}
      detailsSummary={`Normalized prices for all ${current.contracts.length} contracts${thin ? ` (${thin} thin)` : ''}`}
    >
      {rv.synthetic && <Notice>Synthetic data. These gaps are invented and say nothing about the market.</Notice>}
      <ul className="mt-3 space-y-1 text-[13px] leading-relaxed text-ink-2">
        {rv.disclaimers.map((d) => (
          <li key={d}>{d}</li>
        ))}
      </ul>
      <Assumptions liquidity={rv.liquidity} />
      <ul className="mt-4 space-y-2 md:hidden">
        {shown.map((p) => (
          <PairCard key={`${p.contract_a}|${p.contract_b}`} p={p} />
        ))}
      </ul>
      <div className="mt-4 hidden overflow-x-auto md:block">
        <Table caption={`Contract pairs on ${day(current.trade_date)}`}>
          <thead>
            <tr>
              <th className={th}>Pair</th>
              <th className={th}>Expiries</th>
              <th className={thNum}>Gap, raw (bps)</th>
              <th className={thNum} title="Mismatched expiries only: the raw gap minus the carry over the expiry difference">
                Carry-adjusted (bps)
              </th>
              <th className={thNum}>1 tick (bps)</th>
              <th className={thNum}>Volume A / B (lots)</th>
              <th className={thNum}>Open interest A / B</th>
              <th className={th}>Status</th>
            </tr>
          </thead>
          <tbody>
            {shown.map((p) => (
              <PairRow key={`${p.contract_a}|${p.contract_b}`} p={p} a={byId.get(p.contract_a)} b={byId.get(p.contract_b)} />
            ))}
          </tbody>
        </Table>
      </div>
    </DiagramCard>
  )
}

function Assumptions({ liquidity }: { liquidity: RelativeValueResponse['liquidity'] }) {
  const crore = Number(liquidity.min_traded_value_lakh) / 100
  return (
    <div className="mt-3 rounded-lg border border-dashed border-rule-strong px-3 py-2 text-[13px] leading-relaxed text-ink-2">
      <span className="mr-2 inline-block">
        <Pill tone="info">Assumptions</Pill>
      </span>
      A contract counts as liquid only if it traded at least ₹{crore.toLocaleString('en-IN')} crore that day. Pairs within{' '}
      {liquidity.expiry_buffer_days} calendar days of an expiry are not tradeable. The official MCX tender period is shorter:{' '}
      {liquidity.official_tender_period.charAt(0).toLowerCase() + liquidity.official_tender_period.slice(1)}. Both limits are editable in{' '}
      <code className="text-ink">{liquidity.assumptions_file}</code>.
    </div>
  )
}

function PairCard({ p }: { p: PairGap }) {
  return (
    <li className="rounded-lg border border-rule px-3 py-2">
      <div className="flex items-baseline justify-between gap-3">
        <span className="font-medium text-ink">
          {SHORT[p.symbol_a]} / {SHORT[p.symbol_b]}
        </span>
        <span className={`num text-base ${p.gap_bps < 0 ? 'text-loss' : 'text-ink'}`}>{bps(p.gap_bps)} bps</span>
      </div>
      {p.carry_adjusted_gap_bps != null && (
        <div className="num mt-0.5 text-xs text-ink-2">
          carry-adjusted {bps(p.carry_adjusted_gap_bps)} bps (carry {bps(p.carry_bps)} over {p.expiry_gap_days} days)
        </div>
      )}
      <div className="num mt-0.5 text-xs text-ink-3">
        {expiryLabel(p.contract_a)} · {expiryLabel(p.contract_b)}
        {p.location_basis && ' · includes Mumbai–Ahmedabad basis'}
      </div>
      <div className="mt-1.5">
        {p.tradeable ? (
          <Pill tone="good">Both legs liquid</Pill>
        ) : (
          <>
            <Pill tone="warn">Not tradeable</Pill>
            <span className="mt-0.5 block text-xs text-ink-3">{p.not_tradeable_reasons[0]}</span>
          </>
        )}
      </div>
    </li>
  )
}

function PairRow({ p, a, b }: { p: PairGap; a?: ContractQuote; b?: ContractQuote }) {
  return (
    <tr>
      <td className={td}>
        <span className="font-medium whitespace-nowrap text-ink">
          {SHORT[p.symbol_a]} / {SHORT[p.symbol_b]}
        </span>
        {p.location_basis && (
          <span className="mt-0.5 block text-xs text-ink-3" title={p.location_basis}>
            + location basis
          </span>
        )}
      </td>
      <td className={`${td} num whitespace-nowrap text-ink-2`}>
        {expiryLabel(p.contract_a)} · {expiryLabel(p.contract_b)}
        {p.expiry_gap_days > 0 && <span className="block text-xs text-ink-3">{p.expiry_gap_days} days apart</span>}
      </td>
      <td className={`${tdNum} ${p.gap_bps < 0 ? 'text-loss' : 'text-ink'}`}>{bps(p.gap_bps)}</td>
      <td className={tdNum}>
        {p.carry_adjusted_gap_bps == null ? (
          <span className="text-ink-3">{p.expiry_gap_days === 0 ? 'same expiry' : 'no curve'}</span>
        ) : (
          <span
            className={p.carry_adjusted_gap_bps < 0 ? 'text-loss' : 'text-ink'}
            title={`${bps(p.carry_bps)} bps of the raw gap is carry over the ${p.expiry_gap_days}-day expiry difference`}
          >
            {bps(p.carry_adjusted_gap_bps)}
            <span className="block text-xs text-ink-3">carry {bps(p.carry_bps)}</span>
          </span>
        )}
      </td>
      <td className={`${tdNum} text-ink-3`}>{p.resolution_bps.toFixed(2)}</td>
      <td className={tdNum}>
        {count(a?.volume)} / {count(b?.volume)}
      </td>
      <td className={tdNum}>
        {count(a?.open_interest)} / {count(b?.open_interest)}
      </td>
      <td className={td}>
        {p.tradeable ? (
          <Pill tone="good">Both legs liquid</Pill>
        ) : (
          <span title={p.not_tradeable_reasons.join('\n')}>
            <Pill tone="warn">Not tradeable</Pill>
            <span className="mt-0.5 block max-w-56 text-xs text-ink-3">{p.not_tradeable_reasons[0]}</span>
          </span>
        )}
      </td>
    </tr>
  )
}

function NormalizedPrices({ contracts, liquidity }: { contracts: ContractQuote[]; liquidity: RelativeValueResponse['liquidity'] }) {
  return (
    <div className="space-y-2">
      <p>
        A contract is thin when it trades under {liquidity.min_volume_lots} lot, under ₹{money(liquidity.min_traded_value_lakh, 0)} lakh in
        value, or has no open interest. Thin contracts are never shown as tradeable. These limits are assumptions, set in{' '}
        {liquidity.assumptions_file}.
      </p>
      <div className="overflow-x-auto">
        <Table caption="Normalized prices">
          <thead>
            <tr>
              <th className={th}>Contract</th>
              <th className={thNum}>Close (as quoted)</th>
              <th className={th}>Quote basis</th>
              <th className={thNum}>₹/g @999</th>
              <th className={thNum}>Volume</th>
              <th className={thNum}>Value (₹ lakh)</th>
              <th className={thNum}>Open interest</th>
              <th className={th}>Liquidity</th>
            </tr>
          </thead>
          <tbody>
            {contracts.map((q) => (
              <tr key={q.contract_id}>
                <td className={td}>
                  {SHORT[q.symbol]} {day(q.expiry)}
                </td>
                <td className={tdNum}>{money(q.close)}</td>
                <td className={`${td} whitespace-nowrap text-ink-2`}>
                  per {q.quotation_base_g} g · {q.price_basis_fineness} · {q.price_quote_location}
                </td>
                <td className={tdNum}>{q.inr_per_gram_999 ? money(q.inr_per_gram_999) : <span title={q.error ?? ''}>unverified</span>}</td>
                <td className={tdNum}>{count(q.volume)}</td>
                <td className={tdNum}>{money(q.traded_value_lakh)}</td>
                <td className={tdNum}>{count(q.open_interest)}</td>
                <td className={td}>
                  {q.thin ? (
                    <span title={q.thin_reasons.join('; ')}>
                      <Pill tone="warn">Thin</Pill>
                    </span>
                  ) : (
                    <span className="text-ink-3">OK</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </Table>
      </div>
    </div>
  )
}

/** The Research page section: fetches and renders relative value for the session's data. */
export function RelativeValueSection() {
  const { data, error } = useRelativeValue()
  return <RelativeValue rv={data} error={error} />
}
