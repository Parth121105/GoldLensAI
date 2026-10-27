import { useState } from 'react'
import type { Instrument, PairResult, PointStatus, ResearchResponse, Verdict } from '../api/types'
import { DiagramCard, InkGrid, InkHead, InkPage } from '../components/ui/ink/kit'
import { VERDICT_SHORT } from '../components/ui/ink/verdicts'
import { Pill, Table } from '../components/ui'
import { td, th } from '../components/tableStyles'
import { count, day, monthTick } from '../lib/format'
import { SYMBOL_ORDER, VERDICTS } from '../lib/labels'
import { useSession } from '../state/context'

export function Methodology() {
  const { instruments, research } = useSession()
  const list = [...(instruments.data?.instruments ?? [])].sort((a, b) => SYMBOL_ORDER.indexOf(a.symbol) - SYMBOL_ORDER.indexOf(b.symbol))
  const sources = new Map(list.flatMap((i) => i.versions.flatMap((v) => v.sources.map((s) => [s.id, s] as const))))
  const run = research.data
  const config = run?.config

  return (
    <InkPage>
      <InkHead
        tag="Methodology"
        title="How a *verdict* is made"
        finding="How GoldLensAI turns end-of-day quotes into a verdict, and where it deliberately stops."
        aside={instruments.data && <>Method version {instruments.data.method_version}</>}
      />

      <InkGrid>
        <DiagramCard
          className="lg:col-span-8"
          title="Specification-aware normalization"
          description="Every quote is converted to one basis, INR per gram at 999 fineness, using its own contract's specification."
          detailsSummary="Formula, factors and what is not adjusted"
          details={
            <div className="space-y-3">
              <pre className="overflow-x-auto bg-ground px-3 py-2.5 font-mono text-[12px] leading-relaxed text-ink">
{`per gram   = close ÷ quotation base (g)
per g @999 = per gram × 999 ÷ price-basis fineness`}
              </pre>
              {list.length > 0 && (
                <Table caption="Normalization inputs per instrument">
                  <thead>
                    <tr>
                      <th className={th}>Instrument</th>
                      <th className={th}>Quoted per</th>
                      <th className={th}>Fineness</th>
                      <th className={th}>Factor to INR/g @999</th>
                    </tr>
                  </thead>
                  <tbody>
                    {list.map((i) => {
                      const v = i.versions[0]
                      return (
                        <tr key={i.symbol}>
                          <td className={`${td} font-medium text-ink`}>{i.symbol}</td>
                          <td className={`${td} num`}>{v.quotation_base_g} g</td>
                          <td className={`${td} num`}>{v.price_basis_fineness}</td>
                          <td className={`${td} num`}>
                            ÷ {v.quotation_base_g}
                            {v.price_basis_fineness !== 999 && ` × 999 / ${v.price_basis_fineness}`}
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </Table>
              )}
              <p>
                The 999/995 step is MCX's own convention (Due Date Rate and 999 delivery premium). Contracts outside a verified
                specification window are not normalized. Location basis (GOLDPETAL is Ex-Mumbai), making charges and carry are
                not adjusted.
              </p>
            </div>
          }
        >
          {list.length === 0 ? (
            <p className="text-[13px] text-ink-3">{instruments.error ? `Specifications could not be loaded: ${instruments.error}` : 'Loading specifications…'}</p>
          ) : (
            <NormalizationFlow instruments={list} />
          )}
        </DiagramCard>

        <DiagramCard
          className="lg:col-span-4"
          title="Anomaly levels"
          description={run ? 'Each level requires the one before it; lit levels were reached in the latest run.' : 'Each level requires the one before it; levels light up once research has run.'}
          detailsSummary="Rules for each level"
          details={
            <div className="space-y-2">
              <ol className="list-decimal space-y-1.5 pl-5">
                {LEVELS.map(([name, rule]) => (
                  <li key={name}>
                    <strong className="font-medium text-ink">{name}</strong>: {rule}
                  </li>
                ))}
              </ol>
              <p>An unknown cost is never treated as zero, so the cost-adjusted level stays empty until all four cost components are supplied.</p>
            </div>
          }
        >
          <Ladder run={run} />
        </DiagramCard>

        <DiagramCard
          className="lg:col-span-8"
          title="Walk-forward validation"
          description="Time only moves forward: thresholds are chosen on each training window and tested on the window after it."
          detailsSummary="Rules"
          details={
            <ul className="list-disc space-y-1.5 pl-5">
              <li>Eligible dates are split chronologically: expanding training/test folds, then a final holdout used once.</li>
              <li>The z threshold and baseline window are chosen on training data only.</li>
              <li>An event counts in a window only if its outcome date is in the same window. Signals never overlap within a pair, across all of its contract series, so one market move counts once.</li>
              <li>A fold votes on consistency only if it has as many test signals as the holdout needs.</li>
              <li>Signals are compared with ordinary (control) observations, and with costs when they are known.</li>
            </ul>
          }
        >
          <Folds run={run} folds={config?.n_folds ?? 3} holdout={config?.holdout_fraction ?? 0.3} />
        </DiagramCard>

        <DiagramCard
          className="lg:col-span-4"
          title="Contract lifecycle"
          description="Each comparison is one fixed pair of contracts; series are never rolled or spliced."
          details={
            <ul className="list-disc space-y-1.5 pl-5">
              <li>Each comparison is one fixed pair of contracts (symbol + expiry); series are never rolled or spliced.</li>
              <li>Pairs need expiries at most 10 days apart. GOLDM expires on the 5th, the others at month-end, so GOLDM pairs are always cross-expiry.</li>
              <li>Dates within 7 calendar days of the nearer expiry are excluded (delivery tender period).</li>
              <li>Dates missing either contract are skipped and counted, never filled in.</li>
            </ul>
          }
        >
          <dl className="grid grid-cols-3 gap-2">
            {[
              [`≤ ${config?.max_expiry_gap_days ?? 10} d`, 'max expiry gap'],
              [`${config?.lifecycle_buffer_days ?? 7} d`, 'expiry buffer'],
              ['0', 'dates filled in'],
            ].map(([v, k]) => (
              <div key={k} className="ink-chip px-3 py-2.5">
                <dd className="num text-[17px] font-medium text-ink">{v}</dd>
                <dt className="text-[11px] text-ink-3">{k}</dt>
              </div>
            ))}
          </dl>
        </DiagramCard>

        <DiagramCard
          className="lg:col-span-12"
          title="Verdicts"
          description={run ? 'The only conclusions GoldLensAI states about a contract pair, with how many pairs received each in the latest run.' : 'The only conclusions GoldLensAI states about a contract pair.'}
          detailsSummary="What each verdict means"
          details={
            <Table caption="Verdict definitions">
              <thead>
                <tr>
                  <th className={th}>Verdict</th>
                  <th className={th}>Meaning</th>
                </tr>
              </thead>
              <tbody>
                {Object.values(VERDICTS).map((v) => (
                  <tr key={v.label}>
                    <td className={`${td} font-medium whitespace-nowrap`}>{v.label}</td>
                    <td className={`${td} text-ink-2`}>{v.explain}</td>
                  </tr>
                ))}
              </tbody>
            </Table>
          }
        >
          <ul className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-5">
            {(Object.entries(VERDICTS) as [Verdict, (typeof VERDICTS)[Verdict]][]).map(([key, v]) => {
              const n = run?.pairs.filter((p) => p.verdict === key).length
              return (
                <li key={key} className="ink-chip flex flex-col gap-2 p-3" data-on={n ? 'true' : undefined}>
                  <span className="self-start">
                    <Pill tone={v.tone}>{v.label}</Pill>
                  </span>
                  <span className="num text-[20px] font-medium text-ink">{n == null ? '—' : count(n)}</span>
                  <span className="text-[11px] text-ink-3">{n == null ? 'no run yet' : n === 1 ? 'pair' : 'pairs'}</span>
                  <span className="text-xs leading-snug text-ink-2">{VERDICT_SHORT[key]}</span>
                </li>
              )
            })}
          </ul>
        </DiagramCard>

        <DiagramCard className="lg:col-span-6" title="Sources" description="Specifications are taken from MCX circulars, by version.">
          {sources.size === 0 ? (
            <p className="text-[13px] text-ink-3">{instruments.error ? `Sources could not be loaded: ${instruments.error}` : 'Loading sources…'}</p>
          ) : (
            <ul className="space-y-2 text-[13px] leading-relaxed text-ink-2">
              {[...sources.values()].map((s) => (
                <li key={s.id}>
                  <a href={s.retrieved_from} target="_blank" rel="noreferrer" className="font-medium text-ink underline underline-offset-2">{s.id}</a>{' '}
                  ({s.issued_on}) {s.title}. <span className="text-ink-3">{s.retrieval_notes}</span>
                </li>
              ))}
            </ul>
          )}
        </DiagramCard>

        <DiagramCard
          className="lg:col-span-6"
          title="Limits"
          description="End-of-day data held in memory: what the results cannot tell you."
          details={
            <ul className="list-disc space-y-1.5 pl-5">
              <li>Imported data lives in server memory only and is lost on restart, redeploy or free-tier spin-down.</li>
              <li>Uploaded files are labelled user-uploaded; GoldLensAI does not verify that they came from MCX.</li>
              <li>Bhavcopy close is an end-of-day value, not a synchronized executable quote. Volume is not order-book depth.</li>
              <li>Only one real MCX trading day (23 Oct 2026) has been checked; the UDiFF layout has not been checked against a real file.</li>
            </ul>
          }
        />

        <DiagramCard
          className="lg:col-span-12"
          title="Implemented today, and what is not"
          description="So nothing on screen is mistaken for a capability this build does not have."
          detailsSummary="Both lists"
          details={
            <div className="grid gap-x-10 gap-y-5 md:grid-cols-2">
              <div>
                <h3 className="mb-2 font-medium text-ink">In this build</h3>
                <ul className="list-disc space-y-1.5 pl-5">
                  {IN_BUILD.map((x) => <li key={x}>{x}</li>)}
                </ul>
              </div>
              <div>
                <h3 className="mb-2 font-medium text-ink">Not in this build</h3>
                <ul className="list-disc space-y-1.5 pl-5">
                  {NOT_IN_BUILD.map((x) => <li key={x}>{x}</li>)}
                </ul>
              </div>
            </div>
          }
        >
          <dl className="grid grid-cols-2 gap-2 sm:max-w-md">
            <div className="ink-chip px-3 py-2.5">
              <dd className="num text-[20px] font-medium text-gold">{IN_BUILD.length}</dd>
              <dt className="text-[11px] text-ink-3">capabilities in this build</dt>
            </div>
            <div className="ink-chip px-3 py-2.5">
              <dd className="num text-[20px] font-medium text-ink">{NOT_IN_BUILD.length}</dd>
              <dt className="text-[11px] text-ink-3">deliberately not in this build</dt>
            </div>
          </dl>
        </DiagramCard>
      </InkGrid>
    </InkPage>
  )
}

const IN_BUILD = [
  'CSV import of the legacy and UDiFF Bhavcopy layouts, validated row by row, with every rejection and its reason reported.',
  'Versioned specifications for GOLDM, GOLDTEN, GOLDGUINEA and GOLDPETAL from MCX circulars, each with its verified expiry window.',
  'Normalization of every quote to INR per gram at 999 fineness.',
  'Fixed-pair spreads, trailing-baseline flags, and the tick and cost rungs of the evidence ladder.',
  'Walk-forward folds and a final holdout used once; non-overlapping signals; controls.',
  'A synthetic demo dataset, labelled as invented data on every screen.',
]

const NOT_IN_BUILD = [
  'Live, intraday or executable quotes, and order-book depth.',
  'Automatic downloads from MCX: files are downloaded by a person in a browser and uploaded.',
  'Location-basis, making-charge and carry adjustments.',
  'Years of real daily history: one MCX trading day has been imported, far short of what walk-forward testing needs.',
  'A trained machine-learning model: research is rule-based, and the readiness check reports what a model would need.',
  'Storage that survives a restart, and user accounts.',
  'Trading, alerts or recommendations, which are out of scope by design.',
]

const LEVELS: [string, string][] = [
  ['Candidate anomaly', '|z| against the trailing baseline of the same series reaches the threshold.'],
  ['Statistical anomaly', 'and the deviation exceeds the tick-size resolution of both contracts.'],
  ['Cost-adjusted candidate', 'and it exceeds known round-trip costs. Impossible while any cost is unknown.'],
  ['Historically validated', 'a pair-level walk-forward verdict, not a point label.'],
  ['Potentially actionable', 'never assigned by GoldLensAI; needs live executable quotes and depth.'],
]

// --- Normalization flow ----------------------------------------------------------------------

/** One row per contract: its quote → per gram → to 999 → the common basis. Hover a row to trace it. */
function NormalizationFlow({ instruments }: { instruments: Instrument[] }) {
  const [active, setActive] = useState<string | null>(null)
  return (
    <ol className="space-y-2.5" aria-label="Normalization steps per contract">
      {instruments.map((i) => {
        const v = i.versions[0]
        const on = active === i.symbol
        const steps = [
          { k: 'Quoted', v: `₹ / ${v.quotation_base_g} g @${v.price_basis_fineness}` },
          { k: 'Per gram', v: `÷ ${v.quotation_base_g}` },
          { k: 'To 999', v: v.price_basis_fineness === 999 ? '× 1' : `× 999 / ${v.price_basis_fineness}` },
        ]
        return (
          <li
            key={i.symbol}
            tabIndex={0}
            aria-label={`${i.symbol}: quoted in rupees per ${v.quotation_base_g} grams at ${v.price_basis_fineness}, divided by ${v.quotation_base_g}${v.price_basis_fineness === 999 ? '' : `, times 999 over ${v.price_basis_fineness}`}, gives INR per gram at 999`}
            onMouseEnter={() => setActive(i.symbol)}
            onMouseLeave={() => setActive(null)}
            onFocus={() => setActive(i.symbol)}
            onBlur={() => setActive(null)}
            className="flex flex-col gap-1.5 outline-none sm:flex-row sm:items-center sm:gap-0"
          >
            <span className="w-28 shrink-0 text-[13px] font-semibold text-ink">{i.symbol}</span>
            <span className="grid grid-cols-2 gap-1.5 sm:flex sm:items-center sm:gap-0">
            {steps.map((s, k) => (
              <span key={s.k} className="flex items-center">
                {k > 0 && <Wire on={on} />}
                <span className="ink-chip flex-1 px-2.5 py-1.5 sm:flex-none" data-on={on ? 'true' : undefined}>
                  <span className="block text-[10px] text-ink-3">{s.k}</span>
                  <span className="num block text-[12.5px] text-ink">{s.v}</span>
                </span>
              </span>
            ))}
            <span className="flex items-center">
              <Wire on={on} />
              <span className="ink-chip flex-1 px-2.5 py-1.5 sm:flex-none" data-on={on ? 'true' : undefined}>
                <span className="block text-[10px] text-ink-3">Basis</span>
                <span className="num block text-[12.5px] text-gold">INR / g @999</span>
              </span>
            </span>
            </span>
          </li>
        )
      })}
    </ol>
  )
}

function Wire({ on }: { on: boolean }) {
  return (
    <span aria-hidden="true" className="relative mx-1 hidden h-px w-7 sm:block" style={{ background: on ? 'var(--color-gold)' : 'var(--color-rule-strong)', transition: 'background-color 0.3s' }}>
      <span className="absolute -top-[3px] right-0 size-[7px] rotate-45 border-t border-r" style={{ borderColor: on ? 'var(--color-gold)' : 'var(--color-rule-strong)' }} />
    </span>
  )
}

// --- Anomaly ladder ---------------------------------------------------------------------------

const RANK: Partial<Record<PointStatus, number>> = { candidate_anomaly: 1, statistical_anomaly: 2, cost_adjusted_candidate: 3 }

/** Counts per level from the latest run: points at or above each point level, then validated pairs. */
function ladderCounts(run: ResearchResponse) {
  const points = run.pairs.flatMap((p) => p.series.flatMap((s) => s.points))
  const atLeast = (r: number) => points.filter((pt) => (RANK[pt.status] ?? 0) >= r).length
  return [atLeast(1), atLeast(2), atLeast(3), run.pairs.filter((p) => p.verdict === 'historically_validated').length, 0]
}

function Ladder({ run }: { run: ResearchResponse | null }) {
  const counts = run ? ladderCounts(run) : null
  const reached = counts ? counts.reduce((hi, n, k) => (n > 0 ? k : hi), -1) : -1
  const [active, setActive] = useState<number | null>(null)
  const units = ['flags', 'flags', 'flags', 'pairs', '']

  return (
    <div className="flex flex-1 flex-col">
      <ol className="relative space-y-1.5" aria-label="Anomaly levels">
        {LEVELS.map(([name], k) => {
          const lit = k <= reached
          return (
            <li
              key={name}
              tabIndex={0}
              onMouseEnter={() => setActive(k)}
              onMouseLeave={() => setActive(null)}
              onFocus={() => setActive(k)}
              onBlur={() => setActive(null)}
              data-on={active === k ? 'true' : undefined}
              className="ink-chip flex items-center gap-3 px-3 py-2 outline-none"
              style={{ marginLeft: `${k * 6}px` }}
            >
              <span
                aria-hidden="true"
                className="grid size-5 shrink-0 place-items-center border text-[10px] font-semibold"
                style={lit ? { background: 'var(--color-gold)', borderColor: 'var(--color-gold)', color: 'var(--color-gold-ink)' } : { borderColor: 'var(--color-rule-strong)', color: 'var(--color-ink-3)' }}
              >
                {k + 1}
              </span>
              <span className={`min-w-0 flex-1 text-[13px] ${lit ? 'font-medium text-ink' : 'text-ink-2'}`}>{name}</span>
              <span className="num shrink-0 text-xs text-ink-3">
                {k === 4 ? 'never' : counts ? `${count(counts[k])} ${units[k]}` : '—'}
              </span>
              <span className="sr-only">{lit ? ', reached' : ', not reached'}</span>
            </li>
          )
        })}
      </ol>
      <p className="mt-3 min-h-[3.2em] text-[12.5px] leading-relaxed text-ink-2" aria-live="polite">
        {active != null
          ? `${LEVELS[active][0]}: ${LEVELS[active][1]}`
          : !run
            ? 'No research run yet, so no level has been reached.'
            : reached < 0
              ? 'No date reached even the candidate level in the latest run.'
              : `Highest level reached: ${LEVELS[reached][0].toLowerCase()}. Hover a level for its rule.`}
      </p>
    </div>
  )
}

// --- Walk-forward folds -------------------------------------------------------------------------

/** The pair whose windows are drawn: the one with the most eligible dates that has windows. */
function featured(run: ResearchResponse | null): PairResult | null {
  return run?.pairs.filter((p) => p.folds.length > 0 || p.final).sort((a, b) => b.eligible_dates - a.eligible_dates)[0] ?? null
}

interface Row {
  label: string
  train: [number, number]
  test: [number, number]
  holdout: boolean
  note: string
}

function Folds({ run, folds, holdout }: { run: ResearchResponse | null; folds: number; holdout: number }) {
  const pair = featured(run)
  const [active, setActive] = useState<number | null>(null)

  let rows: Row[]
  let axis: [string, string] | null = null
  if (pair) {
    const windows = [...pair.folds, ...(pair.final ? [pair.final] : [])]
    const t = (d: string) => new Date(`${d}T00:00:00Z`).getTime()
    const lo = Math.min(...windows.map((w) => t(w.train_from)))
    const hi = Math.max(...windows.map((w) => t(w.test_to)))
    const f = (d: string) => (t(d) - lo) / (hi - lo || 1)
    rows = windows.map((w) => ({
      label: w.label,
      train: [f(w.train_from), f(w.train_to)],
      test: [f(w.test_from), f(w.test_to)],
      holdout: w.label === 'final holdout',
      note: `${w.label}: trained ${day(w.train_from)} – ${day(w.train_to)} (${count(w.train_signals)} signals), tested ${day(w.test_from)} – ${day(w.test_to)} (${count(w.signals.n)} signals). ${w.status}.`,
    }))
    axis = [windows[0].train_from, windows.at(-1)!.test_to]
  } else {
    const dev = 1 - holdout
    const block = dev / (folds + 1)
    rows = [
      ...Array.from({ length: folds }, (_, k) => ({
        label: `fold ${k + 1}`,
        train: [0, block * (k + 1)] as [number, number],
        test: [block * (k + 1), block * (k + 2)] as [number, number],
        holdout: false,
        note: `Fold ${k + 1}: train on everything before its test window, then test on the next block.`,
      })),
      { label: 'final holdout', train: [0, dev], test: [dev, 1], holdout: true, note: `The final ${Math.round(holdout * 100)}% of eligible dates, used once.` },
    ]
  }
  const pct = (x: number) => `${x * 100}%`

  return (
    <div className="flex flex-1 flex-col">
      <ol className="space-y-2" aria-label="Walk-forward windows" onMouseLeave={() => setActive(null)}>
        {rows.map((r, k) => {
          const dim = active != null && active !== k
          return (
            <li
              key={r.label}
              tabIndex={0}
              onMouseEnter={() => setActive(k)}
              onFocus={() => setActive(k)}
              onBlur={() => setActive(null)}
              aria-label={r.note}
              className="grid grid-cols-[6.5rem_minmax(0,1fr)] items-center gap-3 outline-none"
            >
              <span className={`text-xs ${r.holdout ? 'font-medium text-gold' : 'text-ink-2'}`}>{r.label}</span>
              <span className="relative block h-4 border border-rule bg-ground" data-on={active === k ? 'true' : undefined}>
                <span
                  className="ink-block absolute inset-y-0 bg-ink-3/45"
                  style={{ left: pct(r.train[0]), width: pct(r.train[1] - r.train[0]), opacity: dim ? 0.35 : 1 }}
                />
                <span
                  className="ink-block absolute inset-y-0"
                  style={{
                    left: pct(r.test[0]),
                    width: pct(Math.max(0.004, r.test[1] - r.test[0])),
                    background: r.holdout ? 'var(--color-gold)' : 'var(--color-ink)',
                    opacity: dim ? 0.35 : 1,
                    transform: active === k ? 'scaleY(1.35)' : undefined,
                  }}
                />
              </span>
            </li>
          )
        })}
      </ol>
      {axis && (
        <div className="mt-1 grid grid-cols-[6.5rem_minmax(0,1fr)] gap-3 text-[11px] text-ink-3" aria-hidden="true">
          <span />
          <span className="flex justify-between">
            <span>{monthTick(axis[0])}</span>
            <span>{monthTick(axis[1])}</span>
          </span>
        </div>
      )}
      <ul className="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-xs text-ink-2" aria-label="Key">
        <li className="flex items-center gap-1.5"><span aria-hidden="true" className="inline-block h-2.5 w-3 bg-ink-3/45" />Training</li>
        <li className="flex items-center gap-1.5"><span aria-hidden="true" className="inline-block h-2.5 w-3 bg-ink" />Test fold</li>
        <li className="flex items-center gap-1.5"><span aria-hidden="true" className="inline-block h-2.5 w-3 bg-gold" />Final holdout, used once</li>
      </ul>
      <p className="mt-2 min-h-[2.6em] text-[12.5px] text-ink-2" aria-live="polite">
        {active != null
          ? rows[active].note
          : pair
            ? `Windows of ${pair.symbol_pair} in the latest run, drawn to scale. Hover a window for its dates and signals.`
            : `Schematic with ${folds} folds and a ${Math.round(holdout * 100)}% holdout; a run draws its own windows to scale.`}
      </p>
    </div>
  )
}
