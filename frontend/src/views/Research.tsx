import { useState } from 'react'
import type { FormEvent, ReactNode } from 'react'
import { api } from '../api/client'
import { COST_COMPONENTS } from '../api/types'
import type { CostInput, CostName, Finding, OutcomeStats, PairResult, Readiness, ResearchResponse, Series } from '../api/types'
import { Figure } from '../components/Bento'
import { RealVerdictSection } from '../components/analysis/RealVerdict'
import { RelativeValueSection } from '../components/analysis/RelativeValue'
import { SyntheticValidationSection } from '../components/analysis/SyntheticValidation'
import { TermStructureSection } from '../components/analysis/TermStructure'
import { ReadinessPanel } from '../components/Readiness'
import { SpreadChart } from '../components/ui/ink/SpreadChart'
import { DiagramCard, Details, InkGrid, InkHead, InkPage } from '../components/ui/ink/kit'
import { VERDICT_SHORT } from '../components/ui/ink/verdicts'
import { Button, Empty, ErrorNote, Notice, Pill, Placeholder, Table } from '../components/ui'
import { td, tdNum, th, thNum } from '../components/tableStyles'
import { bps, count, day, fixed, money, percent, timestamp } from '../lib/format'
import { COST_LABELS, INELIGIBLE, STATUSES, VERDICTS, VERDICT_LABEL } from '../lib/labels'
import { navigate } from '../lib/router'
import { useSession } from '../state/context'

export function Research() {
  const { research, datasets, readiness, refreshDatasets } = useSession()
  const run = research.data
  const hasData = (datasets.data?.observations ?? 0) > 0
  const unavailable = !datasets.data && !!datasets.error
  const form = <RunForm key={run?.generated_at ?? 'none'} />

  return (
    <InkPage>
      <InkHead
        tag="Research"
        title="Spread *evidence*"
        finding={finding(run, hasData, unavailable)}
        aside={
          run ? (
            <span className="flex flex-wrap items-center justify-end gap-2">
              <Pill tone="good">Run complete</Pill>
              <span className="num">
                {timestamp(run.generated_at)} · {count(run.observations)} obs. · {day(run.trade_date_from)} – {day(run.trade_date_to)}
              </span>
            </span>
          ) : (
            !unavailable && <Pill>Not run yet</Pill>
          )
        }
      />

      {research.error && <ErrorNote>{research.error}</ErrorNote>}

      <InkGrid>
        {hasData && <RealVerdictSection />}
        {hasData && <ReadinessMeter readiness={readiness.data} error={readiness.error} />}
        {hasData && <RelativeValueSection />}
        {hasData && <TermStructureSection />}
        <SyntheticValidationSection />

        {unavailable ? (
          <DiagramCard className="lg:col-span-12" title="Run research" description="Research runs on the observations held in this session.">
            <ErrorNote onRetry={() => void refreshDatasets()}>Imported data could not be loaded: {datasets.error}</ErrorNote>
          </DiagramCard>
        ) : research.loading && !run ? (
          <DiagramCard className="lg:col-span-12" title="Verdicts by contract pair">
            <Placeholder className="h-48 w-full" />
          </DiagramCard>
        ) : run ? (
          <Results run={run} form={hasData ? form : null} />
        ) : (
          <>
            <DiagramCard
              className={hasData ? 'lg:col-span-12' : 'lg:col-span-7'}
              title="Verdicts by contract pair"
              description="Out-of-sample results per contract pair appear here after a run."
              details={
                !hasData && (
                  <p>
                    Research compares contracts in fixed pairs, so it needs observations for at least two contracts whose expiries are
                    close together. The synthetic demo on the Data screen is enough to try every step.
                  </p>
                )
              }
            >
              {hasData ? (
                <Empty>Research has not been run on the current data. Set the horizon and any known costs, then run it.</Empty>
              ) : (
                <Empty action={<Button onClick={() => navigate('/data')}>Import data</Button>}>
                  Research needs imported observations. Nothing has been calculated.
                </Empty>
              )}
            </DiagramCard>
            {hasData && form}
            <HowItRuns />
          </>
        )}
      </InkGrid>
    </InkPage>
  )
}

function finding(run: ResearchResponse | null, hasData: boolean, unavailable: boolean): ReactNode {
  if (unavailable) return 'The server could not be reached, so research cannot be run or shown.'
  if (!run) return hasData ? 'Spread anomalies and walk-forward validation, computed by the backend over every comparable contract pair.' : 'Import data first; research runs on the observations in this session.'
  const validated = run.pairs.filter((p) => p.verdict === 'historically_validated').length
  const unknown = run.costs.unknown_components.length
  return `${count(run.pairs.length)} contract pairs tested at a ${run.config.horizon}-observation horizon; ${validated === 0 ? 'none' : count(validated)} historically validated${unknown > 0 ? `, with ${unknown} of 4 cost components unknown` : ''}.`
}

function HowItRuns() {
  return (
    <DiagramCard
      className="lg:col-span-5"
      title="What a run does"
      description="Tests whether unusual spreads between fixed contract pairs revert, out of sample and net of costs."
      details={
        <ul className="list-disc space-y-1.5 pl-5">
          <li>Builds spreads only between fixed contract pairs whose expiries are close; series are never rolled or spliced.</li>
          <li>Flags deviations against a trailing baseline of the same series.</li>
          <li>Chooses thresholds on training windows only, then tests once on a final holdout.</li>
          <li>Treats a blank cost as unknown, never as zero, so nothing can pass the cost rung until all four are supplied.</li>
        </ul>
      }
    />
  )
}

// --- Readiness meter ----------------------------------------------------------------------

/** Eligible dates in the best pair against the minimums; the full readiness report sits behind Details. */
function ReadinessMeter({ readiness, error }: { readiness: Readiness | null; error: string | null }) {
  if (!readiness) {
    return (
      <DiagramCard className="lg:col-span-12" title="Readiness">
        {error ? <ErrorNote>Readiness could not be assessed: {error}</ErrorNote> : <Placeholder className="h-16 w-full" />}
      </DiagramCard>
    )
  }
  const v = VERDICT_LABEL[readiness.verdict]
  const have = typeof readiness.summary.best_pair_eligible_dates === 'number' ? readiness.summary.best_pair_eligible_dates : 0
  const best = typeof readiness.summary.best_pair === 'string' ? readiness.summary.best_pair : null
  const need = readiness.minimums.eligible_dates_per_pair
  const marks = [
    { at: readiness.minimums.dates_for_baseline, label: 'one baseline' },
    { at: readiness.minimums.dates_for_holdout, label: 'one holdout' },
  ].filter((m) => m.at < need)
  const pos = (n: number) => `${Math.min(100, (n / need) * 100)}%`

  return (
    <DiagramCard
      className="lg:col-span-12"
      title="Readiness"
      description={`Eligible dates in the best contract pair against the ${count(need)} a walk-forward verdict needs.`}
      actions={<Pill tone={v.tone}>{v.label}</Pill>}
      detailsSummary="Readiness checks and what is missing"
      details={<ReadinessPanel readiness={readiness} error={error} />}
    >
      <div>
        <div className="mb-2 flex flex-wrap items-baseline justify-between gap-2 text-[13px]">
          <span className="text-ink-2">{best ?? 'No pair yet'}</span>
          <span className="num text-ink">
            {count(have)} <span className="text-ink-3">of {count(need)} eligible dates</span>
          </span>
        </div>
        <div
          className="ink-meter"
          role="meter"
          aria-label="Eligible dates in the best contract pair"
          aria-valuemin={0}
          aria-valuemax={need}
          aria-valuenow={have}
          aria-valuetext={`${count(have)} of ${count(need)}`}
        >
          {have > 0 && <div className="ink-meter-fill" style={{ width: pos(have) }} />}
          {marks.map((m) => (
            <span key={m.label} aria-hidden="true" className="absolute -inset-y-1 w-px bg-ink-3" style={{ left: pos(m.at) }} />
          ))}
        </div>
        <div className="relative mt-1.5 h-4 text-[11px] text-ink-3" aria-hidden="true">
          {marks.map((m) => (
            <span key={m.label} className="num absolute -translate-x-1/2" style={{ left: pos(m.at) }}>{count(m.at)}</span>
          ))}
          <span className="num absolute right-0">{count(need)}</span>
        </div>
        <p className="mt-1 text-xs text-ink-3">
          {marks.map((m) => `${count(m.at)} for ${m.label}`).join(' · ')}{marks.length > 0 ? ' · ' : ''}{count(need)} for a walk-forward verdict
        </p>
      </div>
    </DiagramCard>
  )
}

type CostDraft = Record<CostName, { value: string; source: string; asOf: string }>

function RunForm() {
  const { research, setResearch } = useSession()
  const previous = research.data
  const [horizon, setHorizon] = useState(String(previous?.config.horizon ?? 5))
  const [costs, setCosts] = useState<CostDraft>(() => {
    const draft = {} as CostDraft
    for (const name of COST_COMPONENTS) {
      const c = previous?.costs.components.find((x) => x.name === name)
      draft[name] = {
        value: c?.known ? String(c.bps_per_leg_side) : '',
        source: c?.source ?? '',
        asOf: c?.as_of ?? '',
      }
    }
    return draft
  })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function submit(e: FormEvent) {
    e.preventDefault()
    const h = Number(horizon)
    if (!Number.isInteger(h) || h < 1 || h > 60) {
      setError('Horizon must be a whole number from 1 to 60.')
      return
    }
    const supplied: Partial<Record<CostName, CostInput>> = {}
    for (const name of COST_COMPONENTS) {
      const c = costs[name]
      if (c.value.trim() === '') continue
      const v = Number(c.value)
      if (!Number.isFinite(v) || v < 0) {
        setError(`${COST_LABELS[name]} must be a number of basis points ≥ 0, or blank for unknown.`)
        return
      }
      supplied[name] = { bps_per_leg_side: v, source: c.source.trim() || null, as_of: c.asOf || null }
    }
    setBusy(true)
    setError(null)
    try {
      setResearch(await api.runResearch({ horizon: h, costs: supplied }))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Research failed.')
    } finally {
      setBusy(false)
    }
  }

  const input = 'h-8 rounded-lg border border-rule-strong bg-surface px-2 text-[13px] text-ink'

  return (
    <DiagramCard
      className="lg:col-span-7"
      title="Run research"
      description="Spread anomalies and walk-forward validation, computed by the backend over every comparable contract pair."
    >
      <form onSubmit={(e) => void submit(e)} className="space-y-5">
        <label className="block text-[13px] font-medium text-ink">
          Outcome horizon
          <span className="block font-normal text-ink-3">Eligible observations after a signal, 1 to 60.</span>
          <input type="number" min={1} max={60} value={horizon} onChange={(e) => setHorizon(e.target.value)} className={`${input} num mt-1.5 block w-24`} />
        </label>

        <fieldset>
          <legend className="text-[13px] font-medium text-ink">Transaction costs</legend>
          <p className="text-[13px] text-ink-3">Basis points per leg-side. Leave blank for unknown; unknown is never treated as zero.</p>
          <div className="mt-3 grid gap-2.5">
            {COST_COMPONENTS.map((name) => (
              <div key={name} className="grid grid-cols-[minmax(0,1fr)] gap-2 sm:grid-cols-[11rem_5.5rem_minmax(0,1fr)_9.5rem] sm:items-center">
                <span className="text-[13px] text-ink">{COST_LABELS[name]}</span>
                <input
                  aria-label={`${COST_LABELS[name]} in basis points per leg-side`}
                  inputMode="decimal"
                  placeholder="unknown"
                  value={costs[name].value}
                  onChange={(e) => setCosts((c) => ({ ...c, [name]: { ...c[name], value: e.target.value } }))}
                  className={`${input} num placeholder:text-ink-3`}
                />
                <input
                  aria-label={`${COST_LABELS[name]} source`}
                  placeholder="Source, e.g. broker tariff"
                  value={costs[name].source}
                  maxLength={300}
                  onChange={(e) => setCosts((c) => ({ ...c, [name]: { ...c[name], source: e.target.value } }))}
                  className={`${input} placeholder:text-ink-3`}
                />
                <input
                  aria-label={`${COST_LABELS[name]} as-of date`}
                  type="date"
                  value={costs[name].asOf}
                  onChange={(e) => setCosts((c) => ({ ...c, [name]: { ...c[name], asOf: e.target.value } }))}
                  className={input}
                />
              </div>
            ))}
          </div>
        </fieldset>

        <div className="flex flex-wrap items-center gap-3">
          <Button type="submit" variant="primary" disabled={busy}>
            {busy ? 'Running…' : previous ? 'Run again' : 'Run research'}
          </Button>
          {error && <span role="alert" className="text-[13px] text-bad">{error}</span>}
        </div>
      </form>
    </DiagramCard>
  )
}

// --- Results -------------------------------------------------------------------------------

function Results({ run, form }: { run: ResearchResponse; form: ReactNode }) {
  const [selected, setSelected] = useState(run.pairs[0]?.symbol_pair ?? null)
  const pair = run.pairs.find((p) => p.symbol_pair === selected) ?? run.pairs[0]
  const c = run.config
  const validated = run.pairs.filter((p) => p.verdict === 'historically_validated').length
  const supported = run.pairs.filter((p) => p.verdict === 'supported_before_costs_costs_unknown').length

  return (
    <>
      <DiagramCard
        className="lg:col-span-12"
        title="Verdicts by contract pair"
        description="Out-of-sample results from the final holdout; select a pair for its evidence."
        detailsSummary="Full verdict table"
        details={
          run.pairs.length > 0 && (
            <div className="space-y-2">
              <Table caption="Walk-forward verdict per contract pair">
                <thead>
                  <tr>
                    <th className={th}>Pair</th>
                    <th className={th}>Verdict</th>
                    <th className={thNum}>Eligible dates</th>
                    <th className={th}>Holdout</th>
                    <th className={thNum}>Signals</th>
                    <th className={thNum}>Mean reversion, bps</th>
                    <th className={thNum}>t</th>
                    <th className={thNum}>Controls, bps</th>
                    <th className={thNum}>Net of costs, bps</th>
                  </tr>
                </thead>
                <tbody>
                  {run.pairs.map((p) => {
                    const s = p.final?.signals
                    return (
                      <tr key={p.symbol_pair}>
                        <td className={`${td} font-medium whitespace-nowrap text-ink`}>{p.symbol_pair}</td>
                        <td className={td}>
                          <Pill tone={VERDICTS[p.verdict].tone}>{VERDICTS[p.verdict].label}</Pill>
                          <span className="mt-0.5 block text-xs text-ink-3">{VERDICT_SHORT[p.verdict]}</span>
                        </td>
                        <td className={tdNum}>{count(p.eligible_dates)}</td>
                        <td className={`${td} num whitespace-nowrap text-ink-2`}>{p.holdout_from ? `${day(p.holdout_from)} – ${day(p.holdout_to)}` : '—'}</td>
                        <td className={tdNum}>{count(s?.n)}</td>
                        <td className={tdNum}>{reported(p, s, (x) => bps(x.mean_gross_bps))}</td>
                        <td className={tdNum}>{reported(p, s, (x) => fixed(x.t_stat_gross))}</td>
                        <td className={tdNum}>{reported(p, p.final?.controls, (x) => bps(x.mean_gross_bps))}</td>
                        <td className={tdNum}>{reported(p, s, (x) => bps(x.mean_net_bps))}</td>
                      </tr>
                    )
                  })}
                </tbody>
              </Table>
              <p className="text-xs text-ink-3">
                Statistics are shown only when the holdout reached the minimum number of signals. "Mean reversion" is how far the
                spread moved back toward its baseline after a signal; it is not a trading return.
              </p>
            </div>
          )
        }
      >
        <dl className="grid grid-cols-2 gap-x-8 gap-y-4 sm:grid-cols-4">
          <Figure size="lg" label="Pairs historically validated" value={<>{count(validated)} <span className="text-ink-3">of {count(run.pairs.length)}</span></>} />
          <Figure label="Supported before costs" value={count(supported)} note={run.costs.round_trip_bps == null ? 'cannot be validated while costs are unknown' : 'not applicable: all costs supplied'} />
          <Figure
            label="Round trip cost"
            value={run.costs.round_trip_bps == null ? <span className="font-sans text-[15px] font-normal text-ink-2">Not computed</span> : fixed(run.costs.round_trip_bps)}
            unit={run.costs.round_trip_bps == null ? undefined : 'bps'}
            note={run.costs.round_trip_bps == null ? `${run.costs.unknown_components.length} of 4 components unknown` : '4 leg-sides'}
          />
          <Figure label="Holdout" value={percent(c.holdout_fraction)} note={`of eligible dates, after ${c.n_folds} folds`} />
        </dl>

        {run.pairs.length === 0 ? (
          <Empty>No two imported contracts have expiries within {c.max_expiry_gap_days} days of each other, so nothing could be compared.</Empty>
        ) : (
          <ul className="grid grid-cols-1 gap-2.5 sm:grid-cols-2 lg:grid-cols-3" aria-label="Pairs">
            {run.pairs.map((p) => (
              <li key={p.symbol_pair}>
                <VerdictTile pair={p} minEvents={c.min_events} on={p.symbol_pair === pair?.symbol_pair} onSelect={() => setSelected(p.symbol_pair)} />
              </li>
            ))}
          </ul>
        )}
      </DiagramCard>

      {form}

      <DiagramCard
        className={form ? 'lg:col-span-5' : 'lg:col-span-12'}
        title="Assumptions used"
        description="Everything on this screen was computed with exactly these settings."
        detailsSummary="Parameters"
        details={
          <ul className="space-y-1.5">
            <li>Price: {c.price_field}; horizon {c.horizon} eligible observations</li>
            <li>Parameter grid: z ∈ {'{'}{c.z_thresholds.join(', ')}{'}'}, baseline window ∈ {'{'}{c.baseline_windows.join(', ')}{'}'}, chosen on training data only</li>
            <li>Final holdout: last {percent(c.holdout_fraction)} of eligible dates; {c.n_folds} expanding folds before it</li>
            <li>Verdict needs ≥ {c.min_events} non-overlapping holdout signals and t ≥ {c.min_t_stat}</li>
            <li>Pairs: expiries ≤ {c.max_expiry_gap_days} days apart; both legs volume ≥ {c.min_volume}; dates within {c.lifecycle_buffer_days} days of expiry excluded</li>
          </ul>
        }
      >
        <div className="space-y-3 text-[13px]">
          <ul className="space-y-1.5 text-ink-2">
            {run.costs.components.map((x) => (
              <li key={x.name} className="flex flex-wrap items-baseline gap-2">
                {x.known ? <Pill tone="neutral">{x.bps_per_leg_side} bps</Pill> : <Pill tone="warn">Unknown</Pill>}
                <span className="text-ink">{COST_LABELS[x.name] ?? x.name}</span>
                {x.known && <span className="text-xs text-ink-3">{x.source ?? 'user assumption, no source'}{x.as_of ? `, as of ${day(x.as_of)}` : ''}</span>}
              </li>
            ))}
            <li className="pt-1">
              Round trip (4 leg-sides):{' '}
              {run.costs.round_trip_bps == null ? <strong className="font-medium">not computed — costs unknown</strong> : <strong className="num font-medium">{fixed(run.costs.round_trip_bps)} bps</strong>}
            </li>
          </ul>
          {run.cross_file_conflicts.length > 0 && <Notice>{run.cross_file_conflicts.length} conflicting observations were dropped before research.</Notice>}
        </div>
      </DiagramCard>

      {pair && <PairDetail key={pair.symbol_pair} pair={pair} run={run} />}
    </>
  )
}

/** One pair at a glance: verdict, holdout signals against the minimum, and its headline statistics. */
function VerdictTile({ pair: p, minEvents, on, onSelect }: { pair: PairResult; minEvents: number; on: boolean; onSelect: () => void }) {
  const v = VERDICTS[p.verdict]
  const s = p.final?.signals
  const n = s?.n ?? 0
  return (
    <button type="button" aria-pressed={on} onClick={onSelect} className="ink-chip flex w-full flex-col gap-2.5 p-3.5 text-left">
      <span className="flex items-start justify-between gap-2">
        <span className="text-[13px] font-semibold text-ink">{p.symbol_pair}</span>
        <Pill tone={v.tone}>{v.label}</Pill>
      </span>
      <span className="text-xs leading-snug text-ink-2">{VERDICT_SHORT[p.verdict]}</span>
      <span className="block">
        <span className="flex justify-between text-xs text-ink-3">
          <span>Holdout signals</span>
          <span className="num text-ink">{count(n)}<span className="text-ink-3">/{count(minEvents)}</span></span>
        </span>
        <span className="ink-meter mt-1 block h-1.5">
          {n > 0 && <span className="ink-meter-fill" style={{ width: `${Math.min(100, (n / minEvents) * 100)}%` }} />}
        </span>
      </span>
      <span className="grid grid-cols-3 gap-2 text-xs">
        <span><span className="block text-ink-3">Eligible</span><span className="num text-ink">{count(p.eligible_dates)}</span></span>
        <span><span className="block text-ink-3">Mean rev.</span><span className="num text-ink">{reported(p, s, (x) => bps(x.mean_gross_bps))}</span></span>
        <span><span className="block text-ink-3">t</span><span className="num text-ink">{reported(p, s, (x) => fixed(x.t_stat_gross))}</span></span>
      </span>
    </button>
  )
}

/** Hide statistics below the evidence threshold rather than show numbers from a handful of events. */
function reported(p: PairResult, s: OutcomeStats | undefined, f: (s: OutcomeStats) => string) {
  if (!s || p.verdict === 'insufficient_data') return <span className="text-ink-3">—</span>
  return f(s)
}

function PairDetail({ pair, run }: { pair: PairResult; run: ResearchResponse }) {
  const v = VERDICTS[pair.verdict]
  // Open on the series where the final holdout begins, so the HOLDOUT divider is in view.
  const [seriesId, setSeriesId] = useState(() => {
    const from = pair.holdout_from
    const hit = from ? pair.series.find((x) => x.points.some((pt) => pt.trade_date >= from) && x.points[0]?.trade_date <= from) : undefined
    return (hit ?? pair.series[0])?.pair_id ?? null
  })
  const series = pair.series.find((s) => s.pair_id === seriesId) ?? pair.series[0]

  return (
    <>
      <DiagramCard
        className="lg:col-span-12"
        title={<>{pair.symbol_pair} <span className="font-normal text-ink-3">· walk-forward evidence</span></>}
        description={`Point labels use z ≥ ${pair.display_params.z_threshold} and a ${pair.display_params.baseline_window}-observation baseline.`}
        actions={<Pill tone={v.tone}>{v.label}</Pill>}
        detailsSummary="Why this verdict"
        details={
          <div className="space-y-2">
            <p>{v.explain}</p>
            {pair.reasons.length > 0 && (
              <ul className="list-disc space-y-0.5 pl-5">
                {pair.reasons.map((r) => <li key={r}>{r}</li>)}
              </ul>
            )}
            <p>{pair.display_params.selected_by}.</p>
            <p className="text-ink-3">
              Windows are chronological and parameters are chosen on each training window only. Grey rows have fewer than{' '}
              {run.config.min_events} test signals: their numbers are computed but are not evidence.
            </p>
          </div>
        }
      >
        <p className="text-[13px] text-ink-2">
          <span className="font-medium text-ink">{v.label}:</span> {VERDICT_SHORT[pair.verdict]}
        </p>
        {pair.folds.length === 0 && !pair.final ? (
          <Empty>Not enough eligible dates to form validation windows ({count(pair.eligible_dates)} available).</Empty>
        ) : (
          <Table caption="Walk-forward validation windows">
            <thead>
              <tr>
                <th className={th}>Window</th>
                <th className={th}>Train</th>
                <th className={th}>Test</th>
                <th className={th}>Chosen z / window</th>
                <th className={thNum}>Train signals</th>
                <th className={thNum}>Test signals</th>
                <th className={thNum}>Mean reversion, bps</th>
                <th className={thNum}>Hit rate</th>
                <th className={thNum}>Controls, bps</th>
                <th className={th}>Status</th>
              </tr>
            </thead>
            <tbody>
              {[...pair.folds, ...(pair.final ? [pair.final] : [])].map((w) => (
                <tr key={w.label} className={w.signals.n < run.config.min_events ? 'text-ink-3' : undefined}>
                  <td className={`${td} whitespace-nowrap ${w.label === 'final holdout' ? 'font-medium' : ''}`}>{w.label}</td>
                  <td className={`${td} num whitespace-nowrap text-ink-2`}>{day(w.train_from)} – {day(w.train_to)}</td>
                  <td className={`${td} num whitespace-nowrap text-ink-2`}>{day(w.test_from)} – {day(w.test_to)}</td>
                  <td className={`${td} num`}>{w.z_threshold != null ? `${w.z_threshold} / ${w.baseline_window}` : '—'}</td>
                  <td className={tdNum}>{count(w.train_signals)}</td>
                  <td className={tdNum}>{count(w.signals.n)}</td>
                  <td className={tdNum}>{bps(w.signals.mean_gross_bps)}</td>
                  <td className={tdNum}>{percent(w.signals.hit_rate)}</td>
                  <td className={tdNum}>{bps(w.controls.mean_gross_bps)}</td>
                  <td className={`${td} text-xs text-ink-2`}>{w.status}</td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
        {Object.keys(pair.sensitivity).length > 0 && pair.verdict !== 'insufficient_data' && (
          <Details summary="Sensitivity on the holdout (information only, not used for selection)">
            <Table caption="Holdout results for every parameter set">
              <thead>
                <tr>
                  <th className={th}>Parameters</th>
                  <th className={thNum}>Signals</th>
                  <th className={thNum}>Mean reversion, bps</th>
                  <th className={thNum}>t</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(pair.sensitivity).map(([k, s]) => (
                  <tr key={k}>
                    <td className={`${td} num`}>{k}</td>
                    <td className={tdNum}>{count(s.n)}</td>
                    <td className={tdNum}>{bps(s.mean_gross_bps)}</td>
                    <td className={tdNum}>{fixed(s.t_stat_gross)}</td>
                  </tr>
                ))}
              </tbody>
            </Table>
          </Details>
        )}
      </DiagramCard>

      {series && (
        <SpreadView
          series={series}
          holdoutFrom={pair.holdout_from}
          findings={pair.findings.filter((f) => f.pair_id === series.pair_id)}
          unknownCosts={run.costs.round_trip_bps == null}
          picker={
            <select
              aria-label="Contract pair series"
              value={series.pair_id}
              onChange={(e) => setSeriesId(e.target.value)}
              className="h-8 max-w-full rounded-lg border border-rule-strong bg-surface px-2 text-[13px]"
            >
              {pair.series.map((s) => (
                <option key={s.pair_id} value={s.pair_id}>
                  {s.contract_a} vs {s.contract_b} ({s.comparison_type === 'same_expiry' ? 'same expiry' : `expiries ${s.expiry_gap_days} d apart`})
                </option>
              ))}
            </select>
          }
        />
      )}
    </>
  )
}

function SpreadView({
  series,
  holdoutFrom,
  findings,
  unknownCosts,
  picker,
}: {
  series: Series
  holdoutFrom: string | null
  findings: Finding[]
  unknownCosts: boolean
  picker: ReactNode
}) {
  const reasons = Object.entries(series.ineligible_reasons)
  const [showAll, setShowAll] = useState(false)
  const shown = showAll ? findings : findings.slice(0, 12)
  const first = series.points[0]?.trade_date
  const last = series.points.at(-1)?.trade_date
  const holdoutNote =
    !holdoutFrom || !first || !last
      ? 'This pair has no holdout window.'
      : holdoutFrom > last
        ? `The pair's holdout starts ${day(holdoutFrom)}, after this series ends.`
        : holdoutFrom <= first
          ? 'This whole series lies in the pair’s final holdout.'
          : `Dates from ${day(holdoutFrom)} are in the pair's final holdout.`

  return (
    <>
      <DiagramCard
        className="lg:col-span-12"
        title="Spread series"
        description={`Spread of ${series.contract_a} over ${series.contract_b} in basis points; drag across the chart or use the arrow keys to read each date.`}
        actions={picker}
        detailsSummary="How the spread is computed"
        details={
          <p>
            Spread = 10,000 × ln(A ÷ B) on INR per gram at 999 fineness. Positive means {series.contract_a} is rich relative to{' '}
            {series.contract_b}. The baseline is the trailing mean of the same series. {holdoutNote}
          </p>
        }
      >
        <dl className="flex flex-wrap gap-x-6 gap-y-1 text-[13px] text-ink-2">
          <div><dt className="inline text-ink-3">Aligned dates </dt><dd className="num inline text-ink">{count(series.aligned_dates)}</dd></div>
          <div><dt className="inline text-ink-3">Eligible </dt><dd className="num inline text-ink">{count(series.eligible_dates)}</dd></div>
          <div><dt className="inline text-ink-3">Missing {series.contract_a} </dt><dd className="num inline text-ink">{count(series.dates_missing_a.length)}</dd></div>
          <div><dt className="inline text-ink-3">Missing {series.contract_b} </dt><dd className="num inline text-ink">{count(series.dates_missing_b.length)}</dd></div>
          {reasons.map(([code, n]) => (
            <div key={code}><dt className="inline text-ink-3">{INELIGIBLE[code] ?? code} </dt><dd className="num inline text-ink">{count(n)}</dd></div>
          ))}
        </dl>

        {series.points.length === 0 ? (
          <Empty>These two contracts never have an observation on the same date.</Empty>
        ) : (
          <>
            <ul className="flex flex-wrap gap-x-5 gap-y-1 text-xs text-ink-2" aria-label="Legend">
              <li className="flex items-center gap-1.5"><span aria-hidden="true" className="inline-block h-0.5 w-4 bg-gold" />Spread, eligible dates</li>
              <li className="flex items-center gap-1.5"><span aria-hidden="true" className="inline-block w-4 border-t border-dashed border-ink-3" />Trailing baseline mean</li>
              <li className="flex items-center gap-1.5"><span aria-hidden="true" className="inline-block size-2.5 rounded-full border-[1.75px] border-ink bg-surface" />Statistical anomaly or higher</li>
              <li className="flex items-center gap-1.5"><span aria-hidden="true" className="inline-block size-1.5 rounded-full bg-rule-strong" />Ineligible date</li>
              <li className="flex items-center gap-1.5"><span aria-hidden="true" className="inline-block h-2.5 w-4 border-l border-dashed border-gold bg-gold/10" />Final holdout</li>
            </ul>
            <SpreadChart series={series} holdoutFrom={holdoutFrom} />
          </>
        )}
      </DiagramCard>

      <DiagramCard
        className="lg:col-span-12"
        title={`Flagged observations in this series (${count(findings.length)})`}
        description="Each flag with the inputs it was computed from, back to the source file and line."
        details={
          findings.length > 0 && (
            <p>
              A flag is a single-day observation against the trailing baseline. It is not a validated finding and not a trade: the
              pair's walk-forward verdict above decides whether flags like these have historically meant anything.
            </p>
          )
        }
      >
        {findings.length === 0 ? (
          <Empty>No observation in this series reached the candidate threshold.</Empty>
        ) : (
          <div>
            <Table caption="Flagged observations with their inputs">
              <thead>
                <tr>
                  <th className={th}>Date</th>
                  <th className={th}>Level</th>
                  <th className={thNum}>Raw A</th>
                  <th className={thNum}>Raw B</th>
                  <th className={thNum}>A, INR/g @999</th>
                  <th className={thNum}>B, INR/g @999</th>
                  <th className={thNum}>Deviation, bps</th>
                  <th className={thNum}>z</th>
                  <th className={thNum}>Tick floor, bps</th>
                  <th className={thNum}>Net of costs, bps</th>
                  <th className={th}>Source</th>
                </tr>
              </thead>
              <tbody>
                {shown.map((f) => (
                  <tr key={`${f.trade_date}`}>
                    <td className={`${td} num whitespace-nowrap`}>{day(f.trade_date)}</td>
                    <td className={td}><Pill tone={STATUSES[f.status].tone}>{STATUSES[f.status].label}</Pill></td>
                    <td className={tdNum}>{money(f.leg_a.raw_price, 0)}</td>
                    <td className={tdNum}>{money(f.leg_b.raw_price, 0)}</td>
                    <td className={tdNum}>{money(f.leg_a.per_gram_999)}</td>
                    <td className={tdNum}>{money(f.leg_b.per_gram_999)}</td>
                    <td className={tdNum}>{bps(f.deviation_bps)}</td>
                    <td className={tdNum}>{fixed(f.z_score)}</td>
                    <td className={tdNum}>{fixed(f.resolution_bps)}</td>
                    <td className={tdNum}>{unknownCosts ? <span className="text-ink-3">costs unknown</span> : bps(f.net_edge_bps)}</td>
                    <td className={`${td} text-xs whitespace-nowrap text-ink-3`}>
                      {f.leg_a.source_file === f.leg_b.source_file
                        ? `${f.leg_a.source_file}: lines ${f.leg_a.line_number}, ${f.leg_b.line_number}`
                        : `${f.leg_a.source_file}:${f.leg_a.line_number}; ${f.leg_b.source_file}:${f.leg_b.line_number}`}
                    </td>
                  </tr>
                ))}
              </tbody>
            </Table>
            {!showAll && findings.length > shown.length && (
              <div className="mt-3">
                <Button variant="quiet" onClick={() => setShowAll(true)}>Show all {count(findings.length)}</Button>
              </div>
            )}
          </div>
        )}
      </DiagramCard>
    </>
  )
}
