import { ArrowRight, FileCode, FileSpreadsheet, Table2, Upload } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { useId, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { api } from '../api/client'
import type { DatasetStatus, ImportReport, PackageTable } from '../api/types'
import { ReadinessPanel } from '../components/Readiness'
import { clip, curve, elbow } from '../components/ui/ink/geometry'
import { DiagramCard, FlowLine, InkGrid, InkHead, InkPage } from '../components/ui/ink/kit'
import { Button, Disclosure, Empty, ErrorNote, KindBadge, Notice, Pill, Placeholder, Table } from '../components/ui'
import { td, tdNum, th, thNum } from '../components/tableStyles'
import { bytes, count, day, timestamp } from '../lib/format'
import { navigate } from '../lib/router'
import { useSession } from '../state/context'

interface UploadOutcome {
  file: string
  ok: boolean
  message: string
}

export function DataImport() {
  const { datasets, readiness, refreshDatasets, refreshResearch } = useSession()
  const status = datasets.data
  const inputRef = useRef<HTMLInputElement>(null)
  const limitsId = useId()
  const [dateOrder, setDateOrder] = useState<'' | 'DMY' | 'MDY'>('')
  const [busy, setBusy] = useState(false)
  const [progress, setProgress] = useState<string | null>(null)
  const [outcomes, setOutcomes] = useState<UploadOutcome[]>([])
  const [confirmClear, setConfirmClear] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)
  const [dragging, setDragging] = useState(false)
  const [chosen, setChosen] = useState<string[]>([])

  async function afterChange() {
    await Promise.all([refreshDatasets(), refreshResearch()])
  }

  async function onUpload(e: FormEvent) {
    e.preventDefault()
    const files = Array.from(inputRef.current?.files ?? [])
    if (files.length === 0) {
      setOutcomes([{ file: '—', ok: false, message: 'Choose at least one CSV file.' }])
      return
    }
    setBusy(true)
    setOutcomes([])
    const results: UploadOutcome[] = []
    for (const [i, file] of files.entries()) {
      setProgress(`Uploading ${i + 1} of ${files.length}: ${file.name}`)
      try {
        const r = await api.upload(file, dateOrder)
        results.push({ file: file.name, ok: r.stored, message: r.message })
      } catch (err) {
        results.push({ file: file.name, ok: false, message: err instanceof Error ? err.message : 'Upload failed.' })
      }
      setOutcomes([...results])
    }
    setProgress(null)
    setBusy(false)
    if (inputRef.current) inputRef.current.value = ''
    setChosen([])
    await afterChange()
  }

  async function run(action: () => Promise<unknown>) {
    setBusy(true)
    setActionError(null)
    try {
      await action()
      await afterChange()
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Request failed.')
    } finally {
      setBusy(false)
      setConfirmClear(false)
    }
  }

  const limits = status?.limits

  return (
    <InkPage>
      <InkHead
        tag="Data"
        title="Import and *validate*"
        finding={
          !status && datasets.error
            ? 'The server could not be reached, so the session’s files cannot be shown.'
            : !status
              ? 'Checking the session…'
              : status.files.length === 0 && status.package.length === 0
                ? 'No files are imported in this session. Every file is validated row by row before anything is stored.'
                : `${count(status.observations)} futures observations for research from ${count(status.files.length)} ${status.files.length === 1 ? 'file' : 'files'}` +
                  (status.package.length > 0 ? `; ${count(status.package.length)} package ${status.package.length === 1 ? 'table' : 'tables'} held separately.` : '.')
        }
      />

      <InkGrid>
        <DiagramCard
          className="lg:col-span-12"
          title="Import pipeline"
          description="Each file is read and validated, its quotes are normalized against the contract specification, and every row is kept or set aside with a reason."
        >
          {datasets.error && !status ? (
            <ErrorNote onRetry={() => void refreshDatasets()}>{datasets.error}</ErrorNote>
          ) : !status ? (
            <Placeholder className="h-48 w-full" />
          ) : (
            <Pipeline status={status} />
          )}
        </DiagramCard>

        <DiagramCard
          className="lg:col-span-7"
          title="Import market data files"
          description="Every file is validated row by row by the backend; rejected rows are listed with their reasons."
          detailsSummary="Limits and where to download"
          details={
            limits && (
              <p id={limitsId}>
                Up to {bytes(limits.max_upload_bytes)} per file, {count(limits.max_files)} files and{' '}
                {bytes(limits.max_total_bytes)} per session. Download daily files from{' '}
                <a className="underline underline-offset-2" href="https://www.mcxindia.com/market-data/bhavcopy" target="_blank" rel="noreferrer">
                  MCX Bhavcopy
                </a>{' '}
                in a browser.
              </p>
            )
          }
        >
          <form onSubmit={(e) => void onUpload(e)} className="space-y-4">
            <div
              onDragOver={(e) => {
                e.preventDefault()
                if (!busy) setDragging(true)
              }}
              onDragLeave={() => setDragging(false)}
              onDrop={(e) => {
                e.preventDefault()
                setDragging(false)
                if (busy || !inputRef.current || e.dataTransfer.files.length === 0) return
                // Dropped files go into the same input, so upload and validation are unchanged.
                inputRef.current.files = e.dataTransfer.files
                setChosen(Array.from(e.dataTransfer.files, (f) => f.name))
              }}
              data-on={dragging ? 'true' : undefined}
              className="ink-chip border-dashed px-5 py-6"
            >
              <label className="block text-[13px] font-medium text-ink">
                <span className="flex items-center gap-2 text-[15px]">
                  <Upload className="size-4 shrink-0 text-gold" aria-hidden="true" />
                  Drop Bhavcopy files or package tables here, or choose them
                </span>
                <input
                  ref={inputRef}
                  type="file"
                  accept=".csv,.xls,.htm,.html,text/csv,text/html,application/vnd.ms-excel"
                  multiple
                  disabled={busy}
                  onChange={(e) => setChosen(Array.from(e.target.files ?? [], (f) => f.name))}
                  aria-describedby={limits ? limitsId : undefined}
                  className="mt-3 block w-full text-[13px] font-normal text-ink-2 file:mr-3 file:h-8 file:cursor-pointer file:rounded-full file:border file:border-rule-strong file:bg-transparent file:px-3.5 file:text-[13px] file:font-medium file:text-ink hover:file:bg-sunken"
                />
              </label>
              {chosen.length > 0 && (
                <ul className="mt-3 flex flex-wrap gap-1.5" aria-label="Chosen files">
                  {chosen.map((name) => (
                    <li key={name} className="rounded-full bg-sunken px-2.5 py-0.5 text-xs break-all text-ink-2">{name}</li>
                  ))}
                </ul>
              )}
            </div>
            <div className="flex flex-wrap items-end gap-3">
              <label className="text-[13px] font-medium text-ink">
                Numeric date order
                <select
                  value={dateOrder}
                  onChange={(e) => setDateOrder(e.target.value as '' | 'DMY' | 'MDY')}
                  disabled={busy}
                  className="mt-1.5 block h-8 rounded-lg border border-rule-strong bg-surface px-2 text-[13px] font-normal text-ink"
                >
                  <option value="">Detect from file</option>
                  <option value="DMY">Day first (DD/MM/YYYY)</option>
                  <option value="MDY">Month first (MM/DD/YYYY)</option>
                </select>
              </label>
              <Button type="submit" variant="primary" disabled={busy}>
                Upload and validate
              </Button>
            </div>
            {progress && <p role="status" className="text-[13px] text-ink-2">{progress}</p>}
            {outcomes.length > 0 && (
              <ul className="space-y-1.5 text-[13px]" aria-live="polite">
                {outcomes.map((o, i) => (
                  <li key={i} className="flex gap-2">
                    <Pill tone={o.ok ? 'good' : 'bad'}>{o.ok ? 'Added' : 'Not added'}</Pill>
                    <span className="min-w-0 break-words">
                      <span className="font-medium">{o.file}</span> <span className="text-ink-2">— {o.message}</span>
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </form>
        </DiagramCard>

        <DiagramCard
          className="lg:col-span-5"
          title="Session"
          description="Files held in this session and how much of its allowance they use."
          actions={status && <KindBadge kind={status.kind} />}
          detailsSummary="Where the data is kept"
          details={status && <p>{status.storage}</p>}
        >
          <Session
            status={status}
            unavailable={!status && !!datasets.error}
            busy={busy}
            confirmClear={confirmClear}
            onAskClear={() => setConfirmClear(true)}
            onCancelClear={() => setConfirmClear(false)}
            onClear={() => void run(api.clearDatasets)}
          />
        </DiagramCard>

        <DiagramCard
          className="lg:col-span-8"
          title="Accepted formats"
          description="Files are recognised by their header row, never by the file name."
          detailsSummary="Required columns and scope"
          details={
            <div className="space-y-3">
              <dl className="grid gap-x-6 gap-y-3 sm:grid-cols-2">
                <div>
                  <dt className="font-medium text-ink">Legacy MCX Bhavcopy</dt>
                  <dd className="mt-0.5">
                    Required: <Code>Date</Code> <Code>Symbol</Code> <Code>Expiry Date</Code> <Code>Close</Code>. Optional: Open,
                    High, Low, Previous Close, Volume (Lots), Value (Lacs), Open Interest (Lots), Instrument Name, Option Type,
                    Strike Price.
                  </dd>
                </div>
                <div>
                  <dt className="font-medium text-ink">UDiFF Bhavcopy</dt>
                  <dd className="mt-0.5">
                    Required: <Code>TradDt</Code> <Code>TckrSymb</Code> <Code>XpryDt</Code> <Code>ClsPric</Code>. Optional:
                    OpnPric, HghPric, LwPric, PrvsClsgPric, SttlmPric, TtlTradgVol, TtlTrfVal, OpnIntrst.
                  </dd>
                </div>
                <div>
                  <dt className="font-medium text-ink">MCX date-wise download (.xls)</dt>
                  <dd className="mt-0.5">
                    Not an Excel workbook: an HTML table with the legacy columns. Read as a table; nothing in it is run. A
                    full-market day is about 17 MB.
                  </dd>
                </div>
                <div>
                  <dt className="font-medium text-ink">GoldLensAI package tables</dt>
                  <dd className="mt-0.5">
                    <Code>A1</Code> <Code>A2</Code> year-wise totals (reference only), <Code>B1</Code> daily futures (feeds
                    research), <Code>B2</Code> daily options (stored separately, never used as futures prices).
                  </dd>
                </div>
              </dl>
              <p>Header names ignore case, spaces and punctuation.</p>
              <p>
                Only GOLDM, GOLDTEN, GOLDGUINEA and GOLDPETAL futures rows reach research; options, GOLD (1 kg) and other
                commodities are skipped and counted. The legacy layout was checked against one real MCX download (23 Oct 2026);
                the UDiFF layout has not been checked against a real file.
              </p>
            </div>
          }
        >
          <ul className="grid grid-cols-1 gap-2 sm:grid-cols-2" aria-label="Formats">
            {FORMATS.map(([Icon, name, note]) => (
              <li key={name} className="ink-chip flex items-center gap-3 px-3 py-2.5">
                <Icon className="size-4 shrink-0 text-gold" aria-hidden="true" />
                <span className="min-w-0">
                  <span className="block text-[13px] font-medium text-ink">{name}</span>
                  <span className="block text-xs text-ink-3">{note}</span>
                </span>
              </li>
            ))}
          </ul>
        </DiagramCard>

        <DiagramCard
          className="lg:col-span-4"
          title="Synthetic demonstration"
          description="Loads a generated CSV with invented prices for all four contracts through the same importer."
          details={
            <p>
              Covers Jul 2025 – Jun 2026, so the whole pipeline can be tried without MCX files. It is labelled synthetic
              everywhere and cannot be mixed with uploaded files.
            </p>
          }
        >
          <div className="mt-auto space-y-2">
            <Button onClick={() => void run(api.loadDemo)} disabled={busy || status?.kind === 'user_uploaded'}>
              Load synthetic demo
            </Button>
            {status?.kind === 'user_uploaded' && <p className="text-xs text-ink-3">Unavailable while uploaded files are in the session.</p>}
          </div>
        </DiagramCard>

        <p className="lg:col-span-12">
          <a
            href="/contracts"
            onClick={(e) => {
              if (e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return
              e.preventDefault()
              navigate('/contracts')
            }}
            className="inline-flex items-center gap-1.5 text-[13px] font-medium text-ink-2 underline-offset-4 hover:text-ink hover:underline"
          >
            What is not adjusted <ArrowRight className="size-3.5 text-gold" aria-hidden="true" /> Contracts
          </a>
        </p>

        <DiagramCard className="lg:col-span-12" title="Import reports" description="One report per file, exactly as the importer produced it.">
          {actionError && <ErrorNote>{actionError}</ErrorNote>}
          {datasets.error ? (
            <ErrorNote onRetry={() => void refreshDatasets()}>{datasets.error}</ErrorNote>
          ) : !status ? (
            <Placeholder className="h-24 w-full" />
          ) : status.files.length === 0 ? (
            <Empty>{status.package.length > 0 ? 'No Bhavcopy files imported; package tables are listed below.' : 'No files imported in this session.'}</Empty>
          ) : (
            <div className="space-y-4">
              {status.cross_file_conflicts.length > 0 && (
                <Notice>
                  {status.cross_file_conflicts.length} observations disagreed between files and were dropped:{' '}
                  {status.cross_file_conflicts.slice(0, 3).join('; ')}
                  {status.cross_file_conflicts.length > 3 ? '…' : ''}
                </Notice>
              )}
              {status.files.map((f) => (
                <Report key={f.source_sha256} report={f} />
              ))}
            </div>
          )}
        </DiagramCard>

        {status && status.package.length > 0 && (
          <DiagramCard
            className="lg:col-span-12"
            title="Package tables"
            description="Tables A1, A2, B1 and B2, each audited on import."
            details={<p>Annual totals and option premiums never enter a futures price series.</p>}
          >
            <div className="space-y-4">
              {status.package.map((t) => (
                <PackageReport key={t.source_sha256} table={t} />
              ))}
            </div>
          </DiagramCard>
        )}

        <DiagramCard
          className="lg:col-span-12"
          title="Research and model readiness"
          description="Whether the loaded data can support walk-forward research, and what is missing; nothing is trained here."
        >
          <ReadinessPanel readiness={readiness.data} error={readiness.error} />
        </DiagramCard>
      </InkGrid>
    </InkPage>
  )
}

const FORMATS: [LucideIcon, string, string][] = [
  [FileSpreadsheet, 'Legacy MCX Bhavcopy', 'Date, Symbol, Expiry Date, Close'],
  [FileSpreadsheet, 'UDiFF Bhavcopy', 'TradDt, TckrSymb, XpryDt, ClsPric'],
  [FileCode, 'MCX date-wise download (.xls)', 'an HTML table, read as data'],
  [Table2, 'GoldLensAI package tables', 'A1, A2, B1, B2'],
]

// --- Pipeline diagram ---------------------------------------------------------------

const MAX_SOURCES = 5

interface Source {
  id: string
  label: string
  rows: number
  accepted: number
  rejected: number
  duplicates: number
  skipped: number
}

type OutId = 'verified' | 'rejected' | 'dropped'
type Active = { kind: 'source'; id: string } | { kind: 'out'; id: OutId } | null

/**
 * Files → importer and normalizer → outcomes, with the counts the backend reported. Hovering or
 * focusing a file or an outcome lights its path and states its numbers underneath.
 */
function Pipeline({ status }: { status: DatasetStatus }) {
  const [active, setActive] = useState<Active>(null)
  const sources: Source[] = [
    ...status.files.map((f) => ({
      id: f.source_sha256,
      label: f.source_file,
      rows: f.rows_read,
      accepted: f.accepted,
      rejected: f.rejected_count,
      duplicates: f.exact_duplicates_dropped,
      skipped: Object.values(f.skipped).reduce((a, b) => a + b, 0),
    })),
    ...status.package.map((t) => ({
      id: t.source_sha256,
      label: `${t.table_id} · ${t.source_file}`,
      rows: t.rows_read,
      accepted: t.accepted,
      rejected: t.rejected_count,
      duplicates: t.exact_duplicates_dropped + t.cross_file_duplicates,
      skipped: 0,
    })),
  ]
  const sum = (k: 'rows' | 'accepted' | 'rejected' | 'duplicates' | 'skipped') => sources.reduce((n, s) => n + s[k], 0)
  const verified = status.contracts.filter((c) => c.spec_status === 'verified').reduce((n, c) => n + c.observations, 0)
  const unverified = status.contracts.filter((c) => c.spec_status !== 'verified').reduce((n, c) => n + c.observations, 0)
  const outs: { id: OutId; label: string; short: string; value: number; tone?: 'loss'; dashed?: boolean }[] = [
    { id: 'verified', label: 'Verified rows', short: 'Verified', value: verified },
    { id: 'rejected', label: 'Rejected', short: 'Rejected', value: sum('rejected'), tone: 'loss' },
    { id: 'dropped', label: 'Skipped · duplicates', short: 'Set aside', value: sum('duplicates') + sum('skipped'), dashed: true },
  ]
  const shown = sources.slice(0, MAX_SOURCES)
  const more = sources.length - shown.length

  // A source lights its own line and every outcome; an outcome lights itself and every source.
  const srcOn = (id: string | null) => active != null && (active.kind === 'out' || active.id === id)
  const outOn = (id: OutId) => active != null && (active.kind === 'source' || active.id === id)

  const caption = (() => {
    if (active?.kind === 'source') {
      const s = sources.find((x) => x.id === active.id)!
      return `${s.label}: ${count(s.rows)} rows read, ${count(s.accepted)} accepted, ${count(s.rejected)} rejected, ${count(s.duplicates)} duplicates and ${count(s.skipped)} out-of-scope rows set aside.`
    }
    if (active?.kind === 'out') {
      if (active.id === 'verified')
        return `${count(verified)} observations belong to contracts with a verified specification and are normalized to INR per gram at 999${unverified > 0 ? `; ${count(unverified)} more are kept but not normalized` : ''}.`
      if (active.id === 'rejected') return `${count(sum('rejected'))} rows failed validation; each is listed with its line number and reasons in the reports below.`
      return `${count(sum('duplicates'))} exact duplicates and ${count(sum('skipped'))} out-of-scope rows (other symbols, options) were set aside and counted.`
    }
    return sources.length === 0
      ? 'No files yet. Import a file or load the synthetic demo and its rows are counted here.'
      : `${count(sum('rows'))} rows read from ${count(sources.length)} ${sources.length === 1 ? 'file' : 'files'}, ${count(sum('accepted'))} accepted. Hover a file or an outcome for its numbers.`
  })()

  const bind = (a: NonNullable<Active>) => ({
    tabIndex: 0,
    onMouseEnter: () => setActive(a),
    onMouseLeave: () => setActive(null),
    onFocus: () => setActive(a),
    onBlur: () => setActive(null),
  })
  const on = (b: boolean) => (b ? 'true' : undefined)
  const valueClass = (o: (typeof outs)[number]) =>
    `num ${o.id === 'verified' ? 'fill-gold' : o.id === 'rejected' && o.value > 0 ? 'fill-loss' : 'fill-ink'}`
  const rows: (Source | null)[] = shown.length ? shown : [null]

  // Wide: sources left, hub centre, outcomes right.
  const rowH = 40
  const wideH = Math.max(176, (rows.length + (more ? 1 : 0)) * rowH + 24)
  const hub = { x: 320, y: wideH / 2 - 30, w: 140, h: 60 }
  const srcY = (i: number) => 16 + i * rowH
  const outY = (i: number) => wideH / 2 + (i - 1) * 54 - 18

  // Narrow: sources stacked, hub below, outcomes in a row.
  const nRows = rows.length + (more ? 1 : 0)
  const nHubY = 16 + nRows * 36 + 22
  const nOutY = nHubY + 52 + 34
  const narrowH = nOutY + 52

  return (
    <div>
      <svg className="ink-diagram mx-auto hidden max-w-[900px] md:block" viewBox={`0 0 760 ${wideH}`} role="group" aria-label="Import pipeline">
        {rows.map((s, i) => (
          <FlowLine key={s?.id ?? 'none'} d={elbow(214, srcY(i) + 15, hub.x, hub.y + hub.h / 2, 268)} on={s ? srcOn(s.id) : false} dashed={!s} />
        ))}
        {more > 0 && <FlowLine d={elbow(214, srcY(shown.length) + 15, hub.x, hub.y + hub.h / 2, 268)} dashed on={active?.kind === 'out'} />}
        {outs.map((o, i) => (
          <FlowLine key={o.id} d={curve(hub.x + hub.w, hub.y + hub.h / 2, 556, outY(i) + 18)} on={outOn(o.id)} dashed={o.dashed} tone={o.tone} />
        ))}

        {rows.map((s, i) =>
          s ? (
            <g key={s.id} className="ink-hit ink-lift" data-on={on(srcOn(s.id))} role="img" aria-label={`${s.label}: ${count(s.rows)} rows read`} {...bind({ kind: 'source', id: s.id })}>
              <rect className="ink-node" x={10} y={srcY(i)} width={204} height={30} rx={3} />
              <text x={22} y={srcY(i) + 19} fontSize={10} className="fill-ink-2">{clip(s.label, 24)}</text>
              <text x={204} y={srcY(i) + 19} fontSize={10} textAnchor="end" className="num fill-ink">{count(s.rows)}</text>
            </g>
          ) : (
            <g key="none">
              <rect className="ink-node" x={10} y={srcY(0)} width={204} height={30} rx={3} strokeDasharray="3 4" />
              <text x={22} y={srcY(0) + 19} fontSize={10} className="fill-ink-3">No files imported</text>
            </g>
          ),
        )}
        {more > 0 && <text x={22} y={srcY(shown.length) + 19} fontSize={10} className="fill-ink-3">+ {count(more)} more {more === 1 ? 'file' : 'files'}</text>}

        <g data-on={on(active != null)}>
          <rect className="ink-node" x={hub.x} y={hub.y} width={hub.w} height={hub.h} rx={6} />
          <text x={hub.x + hub.w / 2} y={hub.y + 24} fontSize={8.5} letterSpacing={1.2} textAnchor="middle" className="fill-ink-3">IMPORT · NORMALIZE</text>
          <text x={hub.x + hub.w / 2} y={hub.y + 44} fontSize={13} textAnchor="middle" className="num fill-ink">
            {count(sum('accepted'))} <tspan fontSize={9} className="fill-ink-3">accepted</tspan>
          </text>
        </g>

        {outs.map((o, i) => (
          <g key={o.id} className="ink-hit ink-lift" data-on={on(outOn(o.id))} role="img" aria-label={`${o.label}: ${count(o.value)}`} {...bind({ kind: 'out', id: o.id })}>
            <rect className="ink-node" x={556} y={outY(i)} width={194} height={36} rx={3} strokeDasharray={o.dashed ? '3 4' : undefined} />
            <text x={568} y={outY(i) + 22} fontSize={10} className="fill-ink-2">{o.label}</text>
            <text x={740} y={outY(i) + 23} fontSize={12} textAnchor="end" className={valueClass(o)}>{count(o.value)}</text>
          </g>
        ))}
      </svg>

      <svg className="ink-diagram block md:hidden" viewBox={`0 0 340 ${narrowH}`} role="group" aria-label="Import pipeline">
        {rows.map((s, i) => (
          <FlowLine key={s?.id ?? 'none'} d={elbow(30, 16 + i * 36 + 14, 110, nHubY + 26, 16)} on={s ? srcOn(s.id) : false} dashed={!s} />
        ))}
        {outs.map((o, i) => (
          <FlowLine
            key={o.id}
            d={`M170,${nHubY + 52} C170,${nHubY + 72} ${60 + i * 110},${nOutY - 20} ${60 + i * 110},${nOutY}`}
            on={outOn(o.id)}
            dashed={o.dashed}
            tone={o.tone}
          />
        ))}
        {rows.map((s, i) =>
          s ? (
            <g key={s.id} className="ink-hit" data-on={on(srcOn(s.id))} role="img" aria-label={`${s.label}: ${count(s.rows)} rows read`} {...bind({ kind: 'source', id: s.id })}>
              <rect className="ink-node" x={30} y={16 + i * 36} width={300} height={28} rx={3} />
              <text x={40} y={16 + i * 36 + 18} fontSize={12.5} className="fill-ink-2">{clip(s.label, 26)}</text>
              <text x={320} y={16 + i * 36 + 18} fontSize={12.5} textAnchor="end" className="num fill-ink">{count(s.rows)}</text>
            </g>
          ) : (
            <g key="none">
              <rect className="ink-node" x={30} y={16} width={300} height={28} rx={3} strokeDasharray="3 4" />
              <text x={40} y={34} fontSize={12.5} className="fill-ink-3">No files imported</text>
            </g>
          ),
        )}
        {more > 0 && <text x={40} y={16 + shown.length * 36 + 18} fontSize={12.5} className="fill-ink-3">+ {count(more)} more</text>}
        <g data-on={on(active != null)}>
          <rect className="ink-node" x={110} y={nHubY} width={120} height={52} rx={6} />
          <text x={170} y={nHubY + 20} fontSize={9.5} letterSpacing={0.8} textAnchor="middle" className="fill-ink-3">IMPORT · NORMALIZE</text>
          <text x={170} y={nHubY + 39} fontSize={14.5} textAnchor="middle" className="num fill-ink">{count(sum('accepted'))}</text>
        </g>
        {outs.map((o, i) => (
          <g key={o.id} className="ink-hit" data-on={on(outOn(o.id))} role="img" aria-label={`${o.label}: ${count(o.value)}`} {...bind({ kind: 'out', id: o.id })}>
            <rect className="ink-node" x={12 + i * 110} y={nOutY} width={96} height={48} rx={3} strokeDasharray={o.dashed ? '3 4' : undefined} />
            <text x={60 + i * 110} y={nOutY + 19} fontSize={11} textAnchor="middle" className="fill-ink-3">{o.short}</text>
            <text x={60 + i * 110} y={nOutY + 37} fontSize={14.5} textAnchor="middle" className={valueClass(o)}>{count(o.value)}</text>
          </g>
        ))}
      </svg>

      <p className="mt-3 min-h-[2.6em] text-center text-[13px] text-ink-2" aria-live="polite">{caption}</p>
    </div>
  )
}

const KIND_LABEL: Record<PackageTable['kind'], { label: string; tone: 'neutral' | 'info' }> = {
  annual: { label: 'Year-wise · reference only', tone: 'neutral' },
  futures: { label: 'Daily futures · feeds research', tone: 'info' },
  options: { label: 'Daily options · stored separately', tone: 'neutral' },
}

function PackageReport({ table: t }: { table: PackageTable }) {
  const k = KIND_LABEL[t.kind]
  const c = t.coverage as Record<string, unknown>
  const span =
    t.kind === 'annual'
      ? `${String(c.first_year ?? '—')} – ${String(c.last_year ?? '—')}`
      : c.first_date ? `${day(String(c.first_date))} – ${day(String(c.last_date))}` : '—'
  const gaps = Array.isArray(c.missing_years) && c.missing_years.length > 0 ? `missing years ${c.missing_years.join(', ')}` : null
  const warnings = [...Object.entries(t.row_warnings).map(([w, n]) => `${count(n)} × ${w}`), ...t.table_warnings]
  const missing = Object.entries(t.missing_values)

  return (
    <article className="ink-chip space-y-3 p-4">
      <header className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <h3 className="text-[14px] font-semibold">
          {t.table_id} <span className="font-normal text-ink-2">· {t.title}</span>
        </h3>
        <Pill tone={k.tone}>{k.label}</Pill>
        {t.synthetic ? <Pill tone="warn">Synthetic</Pill> : <Pill tone="info">User upload · unverified</Pill>}
      </header>
      <p className="text-xs break-all text-ink-3">
        {t.source_file} · {bytes(t.size_bytes)} · imported {timestamp(t.imported_at)} · SHA-256 {t.source_sha256.slice(0, 12)}…
      </p>
      <dl className="grid grid-cols-2 gap-x-6 gap-y-3 sm:grid-cols-5">
        <Fact label="Rows read" value={count(t.rows_read)} />
        <Fact label="Accepted" value={count(t.accepted)} />
        <Fact label="Rejected" value={count(t.rejected_count)} />
        <Fact label="Duplicates (in file · across files)" value={`${count(t.exact_duplicates_dropped)} · ${count(t.cross_file_duplicates)}`} />
        <Fact label={t.kind === 'annual' ? 'Years' : 'Trading dates'} value={span} />
      </dl>
      <p className="text-xs text-ink-3">
        {t.kind === 'annual'
          ? `${String(c.years ?? 0)} years${gaps ? `, ${gaps}` : ''}`
          : `${String(c.trading_dates ?? 0)} trading date(s), ${String(c.contract_expiries ?? 0)} contract expiries, symbols ${((c.symbols as string[]) ?? []).join(', ')}`}
        {missing.length > 0 && ` · NA values: ${missing.map(([col, n]) => `${col} ${n}`).join(', ')}`}
      </p>
      {warnings.length > 0 && (
        <ul className="space-y-0.5 text-xs text-ink-2">
          {warnings.map((w) => <li key={w}>Note: {w}</li>)}
        </ul>
      )}
      {t.rejected_count > 0 && (
        <Disclosure summary={`Rejected rows (${count(t.rejected_count)})`}>
          <Table caption={`Rejected rows in ${t.source_file}`}>
            <thead>
              <tr>
                <th className={thNum}>Line</th>
                <th className={th}>Reasons</th>
              </tr>
            </thead>
            <tbody>
              {t.rejected.map((x) => (
                <tr key={x.line_number}>
                  <td className={`${tdNum} w-16`}>{x.line_number}</td>
                  <td className={td}>{x.reasons.join('; ')}</td>
                </tr>
              ))}
            </tbody>
          </Table>
        </Disclosure>
      )}
    </article>
  )
}

function Session({
  status,
  unavailable,
  busy,
  confirmClear,
  onAskClear,
  onCancelClear,
  onClear,
}: {
  status: DatasetStatus | null
  unavailable: boolean
  busy: boolean
  confirmClear: boolean
  onAskClear: () => void
  onCancelClear: () => void
  onClear: () => void
}) {
  if (unavailable) return <Empty>Session details are unavailable until the server can be reached.</Empty>
  if (!status) return <Placeholder className="h-32 w-full" />
  const used = status.files.reduce((n, f) => n + f.size_bytes, 0)
  return (
    <div className="space-y-5">
      <div className="space-y-4">
        <Usage label="Files" used={status.files.length} max={status.limits.max_files} format={count} />
        <Usage label="Session size" used={used} max={status.limits.max_total_bytes} format={bytes} />
      </div>
      <p className="text-[13px] leading-relaxed text-ink-2">{status.storage}</p>
      <div className="border-t border-rule pt-4">
        {confirmClear ? (
          <div className="flex flex-wrap items-center gap-2 text-[13px]">
            <span className="text-ink">Remove all imported files and research results?</span>
            <Button variant="primary" onClick={onClear} disabled={busy}>Remove everything</Button>
            <Button variant="quiet" onClick={onCancelClear}>Cancel</Button>
          </div>
        ) : (
          <Button onClick={onAskClear} disabled={busy || status.kind === 'empty'}>
            Clear session
          </Button>
        )}
      </div>
    </div>
  )
}

/** A bar at the true ratio, both ends labelled. A zero has no stub. */
function Usage({ label, used, max, format }: { label: string; used: number; max: number; format: (n: number) => string }) {
  const ratio = max > 0 ? Math.min(1, used / max) : 0
  return (
    <div>
      <div className="flex items-baseline justify-between text-[13px]">
        <span className="text-ink-3">{label}</span>
        <span className="num text-ink">
          {format(used)} <span className="text-ink-3">of {format(max)}</span>
        </span>
      </div>
      <div
        role="meter"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={max}
        aria-valuenow={used}
        aria-valuetext={`${format(used)} of ${format(max)}`}
        className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-sunken"
      >
        {ratio > 0 && <div className="h-full rounded-full bg-ink-2" style={{ width: `${ratio * 100}%` }} />}
      </div>
    </div>
  )
}

function Report({ report: r }: { report: ImportReport }) {
  const skipped = Object.entries(r.skipped)
  const rowWarnings = Object.entries(r.row_warnings)
  return (
    <article className="ink-chip space-y-3 p-4">
      <header className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <h3 className="text-[14px] font-semibold break-all">{r.source_file}</h3>
        {r.synthetic ? <Pill tone="warn">Synthetic</Pill> : <Pill tone="info">User upload</Pill>}
        <span className="text-xs text-ink-3">
          {bytes(r.size_bytes)} · imported {timestamp(r.imported_at)} · SHA-256 {r.source_sha256.slice(0, 12)}…
        </span>
      </header>
      <p className="text-[13px] text-ink-2">{r.provenance}</p>
      <dl className="grid grid-cols-2 gap-x-6 gap-y-3 sm:grid-cols-5">
        <Fact label="Rows read" value={count(r.rows_read)} />
        <Fact label="Accepted" value={count(r.accepted)} />
        <Fact label="Rejected" value={count(r.rejected_count)} />
        <Fact label="Exact duplicates dropped" value={count(r.exact_duplicates_dropped)} />
        <Fact label="Trade dates" value={r.trade_dates ? `${day(r.trade_date_from)} – ${day(r.trade_date_to)}` : '—'} />
      </dl>
      <p className="text-xs text-ink-3">
        Layout {r.layout_id}
        {r.layout_verified_against_real_file ? '' : ' (not yet verified against a real MCX file)'} · date order{' '}
        {r.date_order ?? 'not needed'} · volume in {r.units.volume ?? '—'}
      </p>
      {(skipped.length > 0 || rowWarnings.length > 0 || r.warnings.length > 0) && (
        <ul className="space-y-0.5 text-xs text-ink-2">
          {skippedLines(skipped).map((line) => <li key={line}>{line}</li>)}
          {rowWarnings.map(([kind, n]) => <li key={kind}>Accepted with note: {count(n)} × {kind}</li>)}
          {r.warnings.map((w) => <li key={w}>File warning: {w}</li>)}
        </ul>
      )}
      {r.rejected_count > 0 && (
        <Disclosure summary={`Rejected rows (${count(r.rejected_count)})`}>
          <Table caption={`Rejected rows in ${r.source_file}`}>
            <thead>
              <tr>
                <th className={thNum}>Line</th>
                <th className={th}>Reasons</th>
              </tr>
            </thead>
            <tbody>
              {r.rejected.map((x) => (
                <tr key={x.line_number}>
                  <td className={`${tdNum} w-16`}>{x.line_number}</td>
                  <td className={td}>{x.reasons.join('; ')}</td>
                </tr>
              ))}
            </tbody>
          </Table>
          {r.rejected.length < r.rejected_count && (
            <p className="mt-1 text-xs text-ink-3">Showing the first {r.rejected.length} of {count(r.rejected_count)}.</p>
          )}
        </Disclosure>
      )}
    </article>
  )
}

/** Skipped rows by reason; out-of-scope symbols are summarised so a full-market file stays readable. */
function skippedLines(skipped: [string, number][]): string[] {
  const symbols = skipped.filter(([reason]) => reason.startsWith('symbol ') && !reason.startsWith('symbol GOLD '))
  const rest = skipped.filter((entry) => !symbols.includes(entry))
  const lines = rest.map(([reason, n]) => `Skipped ${count(n)} × ${reason}`)
  if (symbols.length > 3) {
    const total = symbols.reduce((sum, [, n]) => sum + n, 0)
    lines.push(`Skipped ${count(total)} rows of ${count(symbols.length)} other commodities (out of scope)`)
  } else {
    lines.push(...symbols.map(([reason, n]) => `Skipped ${count(n)} × ${reason}`))
  }
  return lines
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs text-ink-3">{label}</dt>
      <dd className="num text-[15px] font-medium text-ink">{value}</dd>
    </div>
  )
}

function Code({ children }: { children: string }) {
  return <code className="rounded bg-sunken px-1 py-px font-mono text-[12px] text-ink">{children}</code>
}
