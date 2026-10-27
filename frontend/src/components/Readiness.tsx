import type { Readiness } from '../api/types'
import { count } from '../lib/format'
import { VERDICT_LABEL } from '../lib/labels'
import { ErrorNote, Pill, Placeholder } from './ui'

/** Readiness verdict, its checks, and exactly what data is missing. Every value comes from /api/readiness. */
export function ReadinessPanel({ readiness, error, compact = false }: { readiness: Readiness | null; error: string | null; compact?: boolean }) {
  if (error && !readiness) return <ErrorNote>Readiness could not be assessed: {error}</ErrorNote>
  if (!readiness) return <Placeholder className="h-32 w-full" />
  const v = VERDICT_LABEL[readiness.verdict]
  const checks = compact ? readiness.checks.filter((c) => !c.passed) : readiness.checks

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <Pill tone={v.tone}>{v.label}</Pill>
        <span className="text-[13px] text-ink-2">{v.explain}</span>
      </div>
      <p className="text-[13px] leading-relaxed text-ink-3">{readiness.model}</p>

      <ul className="space-y-2" aria-label="Readiness checks">
        {checks.map((c) => (
          <li key={c.id} className="flex gap-2.5 text-[13px]">
            <span
              aria-hidden="true"
              className={`mt-[5px] size-2 shrink-0 rounded-full ${c.passed ? 'bg-good' : 'border border-warn bg-transparent'}`}
            />
            <span className="min-w-0">
              <span className="text-ink">{c.label}</span>
              <span className="sr-only">{c.passed ? ' (passed)' : ' (not met)'}</span>
              <span className="block text-ink-3">{c.detail}</span>
            </span>
          </li>
        ))}
      </ul>

      {readiness.missing.length > 0 && (
        <div className="rounded bg-sunken px-3.5 py-3">
          <h3 className="text-[13px] font-medium text-ink">Data still needed</h3>
          <ul className="mt-1.5 list-disc space-y-1 pl-5 text-[13px] leading-relaxed text-ink-2">
            {readiness.missing.map((m) => (
              <li key={m}>{m}</li>
            ))}
          </ul>
        </div>
      )}
      {!compact && (
        <p className="num text-xs text-ink-3">
          Minimum eligible dates per contract pair: {count(readiness.minimums.eligible_dates_per_pair)} · per holdout:{' '}
          {count(readiness.minimums.dates_for_holdout)} · for one baseline: {count(readiness.minimums.dates_for_baseline)}
        </p>
      )}
    </div>
  )
}
