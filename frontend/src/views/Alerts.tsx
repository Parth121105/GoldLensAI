import { useAlerts } from '../components/analysis/useAnalysis'
import { td, tdNum, th, thNum } from '../components/tableStyles'
import { Button, Empty, ErrorNote, Pill, Placeholder, Table } from '../components/ui'
import { DiagramCard, InkGrid, InkHead, InkPage } from '../components/ui/ink/kit'
import { bps, count, day } from '../lib/format'
import { navigate } from '../lib/router'
import { useSession } from '../state/context'

const SHORT: Record<string, string> = { GOLDM: 'Mini', GOLDTEN: 'Ten', GOLDGUINEA: 'Guinea', GOLDPETAL: 'Petal' }
const contract = (id: string) => {
  const [s, ...rest] = id.split('-')
  return `${SHORT[s] ?? s} ${day(rest.join('-'))}`
}

export function Alerts() {
  const { datasets } = useSession()
  const { data, error } = useAlerts()
  const hasData = (datasets.data?.observations ?? 0) > 0

  return (
    <InkPage>
      <InkHead
        tag="Alerts"
        title="Relative-value *alerts*"
        finding="Quiet unless a liquid contract pair moves unusually far from its own normal gap, by more than it would cost to trade."
        aside={data && <Pill tone={data.quiet ? 'neutral' : 'warn'}>{data.quiet ? 'Quiet' : `${data.alerts.length} alert(s)`}</Pill>}
      />
      <InkGrid>
        {error ? (
          <DiagramCard className="lg:col-span-12" title="Alerts">
            <ErrorNote>Alerts could not be loaded: {error}</ErrorNote>
          </DiagramCard>
        ) : !data ? (
          <DiagramCard className="lg:col-span-12" title="Alerts">
            <Placeholder className="h-32 w-full" />
          </DiagramCard>
        ) : !hasData ? (
          <DiagramCard className="lg:col-span-12" title="No meaningful signal">
            <Empty action={<Button onClick={() => navigate('/data')}>Import data</Button>}>
              No data is imported, so there is nothing to check.
            </Empty>
          </DiagramCard>
        ) : (
          <>
            <DiagramCard
              className="lg:col-span-12"
              title={data.kind === 'synthetic' ? `${data.headline} (synthetic data)` : data.headline}
              description={data.trade_date ? `Checked on ${day(data.trade_date)}, the latest imported trade date.` : undefined}
            >
              <p className="mt-3 text-[15px] leading-relaxed text-ink">{data.reason}</p>
              {data.alerts.length > 0 && (
                <div className="mt-4 overflow-x-auto">
                  <Table caption="Alerts">
                    <thead>
                      <tr>
                        <th className={th}>Pair</th>
                        <th className={thNum}>Gap (bps)</th>
                        <th className={thNum}>Normal gap</th>
                        <th className={thNum}>Move</th>
                        <th className={thNum}>z</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.alerts.map((a) => (
                        <tr key={`${a.contract_a}|${a.contract_b}`}>
                          <td className={`${td} whitespace-nowrap`}>
                            {contract(a.contract_a)} / {contract(a.contract_b)}
                          </td>
                          <td className={tdNum}>{bps(a.gap_bps)}</td>
                          <td className={tdNum}>{bps(a.normal_gap_bps)}</td>
                          <td className={tdNum}>{bps(a.move_bps)}</td>
                          <td className={tdNum}>{a.z.toFixed(1)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </Table>
                </div>
              )}
            </DiagramCard>
            <DiagramCard
              className="lg:col-span-12"
              title="What has to happen for an alert"
              description="Every test must pass. The thresholds are assumptions, editable in backend/config/assumptions.json."
            >
              <ol className="mt-3 list-decimal space-y-2 pl-5 text-[13px] leading-relaxed text-ink-2">
                <li>
                  Both contracts are liquid and more than the pre-expiry buffer away from expiry ({count(data.pairs_tradeable)} of{' '}
                  {count(data.pairs_checked)} pairs pass on this date).
                </li>
                <li>
                  The pair has at least {data.baseline_dates} earlier dates, so its normal gap is known ({count(data.pairs_with_baseline)}{' '}
                  pass).
                </li>
                <li>The gap, carry-adjusted where expiries differ, is at least {data.z_threshold} standard deviations from that normal gap.</li>
                <li>
                  The move from normal is larger than the {data.round_trip_cost_bps.toFixed(1)} bps round-trip cost of trading both legs
                  {data.extra_margin_bps > 0 ? ` plus a ${data.extra_margin_bps} bps margin` : ''}.
                </li>
              </ol>
              <p className="mt-3 text-xs text-ink-3">
                A gap that is always there, such as GOLDPETAL priced in Mumbai against the Ahmedabad contracts, is part of the normal gap and
                never alerts. Closing prices are not fill prices.
              </p>
            </DiagramCard>
          </>
        )}
      </InkGrid>
    </InkPage>
  )
}
