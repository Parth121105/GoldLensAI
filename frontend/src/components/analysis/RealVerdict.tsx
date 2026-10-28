import { count } from '../../lib/format'
import { ErrorNote, Pill, Placeholder } from '../ui'
import { DiagramCard } from '../ui/ink/kit'
import { useVerdict } from './useAnalysis'

const SHORT: Record<string, string> = { GOLDM: 'Mini', GOLDTEN: 'Ten', GOLDGUINEA: 'Guinea', GOLDPETAL: 'Petal' }

/** Real dates per pair against the walk-forward minimum, and the plain verdict. */
export function RealVerdictSection() {
  const { data, error } = useVerdict()
  const title = data?.kind === 'synthetic' ? 'Verdict on the loaded synthetic data' : 'Verdict on real data'
  if (error) {
    return (
      <DiagramCard className="lg:col-span-12" title={title}>
        <ErrorNote>The verdict could not be loaded: {error}</ErrorNote>
      </DiagramCard>
    )
  }
  if (!data) {
    return (
      <DiagramCard className="lg:col-span-12" title={title}>
        <Placeholder className="h-32 w-full" />
      </DiagramCard>
    )
  }
  const insufficient = data.pairs.every((p) => p.verdict === 'insufficient_data')
  return (
    <DiagramCard
      className="lg:col-span-12"
      title={title}
      description={`${count(data.trade_dates)} trade dates imported. The walk-forward test needs ${count(data.needed_per_pair)} eligible dates for each contract pair before it can give any verdict.`}
      actions={<Pill tone={insufficient ? 'neutral' : 'info'}>{insufficient ? 'Insufficient data' : 'Ready to test'}</Pill>}
    >
      <p className="mt-3 text-[15px] leading-relaxed text-ink">{data.statement}</p>
      <ul className="mt-4 grid gap-x-6 gap-y-2.5 sm:grid-cols-2">
        {data.pairs.map((p) => {
          const share = Math.min(1, p.eligible_dates / p.needed)
          return (
            <li key={p.symbol_pair}>
              <div className="flex items-baseline justify-between gap-3 text-[13px]">
                <span className="text-ink">
                  {p.symbol_pair
                    .split('/')
                    .map((s) => SHORT[s] ?? s)
                    .join(' / ')}
                </span>
                <span className="num text-ink-2">
                  {count(p.eligible_dates)} of {count(p.needed)} dates
                </span>
              </div>
              <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-sunken" aria-hidden>
                <div className="h-full rounded-full bg-gold" style={{ width: `${Math.max(share * 100, share > 0 ? 0.6 : 0)}%` }} />
              </div>
            </li>
          )
        })}
      </ul>
    </DiagramCard>
  )
}
