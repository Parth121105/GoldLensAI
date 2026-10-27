import { useLayoutEffect, useMemo, useRef, useState } from 'react'
import type { KeyboardEvent, PointerEvent, ReactNode } from 'react'
import { day, monthTick } from '../../lib/format'
import { EASE_OUT, gsap, prefersReducedMotion, useGSAP } from '../../lib/gsap'

export interface ChartSeries {
  id: string
  label: string
  color: string
  /** Value per date in ``dates`` order; null means no observation and breaks the line. */
  values: (number | null)[]
  width?: number
}

export interface ChartMarker {
  index: number
  value: number
  kind: 'flag' | 'muted'
}

interface Props {
  dates: string[]
  series: ChartSeries[]
  markers?: ChartMarker[]
  unit: string
  formatValue: (v: number) => string
  /** Plain-language summary for screen readers. */
  description: string
  height?: number
  tooltipExtra?: (index: number) => ReactNode
}

const PAD = { top: 24, right: 12, bottom: 26, left: 64 }

export function TimeChart({ dates, series, markers = [], unit, formatValue, description, height = 260, tooltipExtra }: Props) {
  const wrapRef = useRef<HTMLDivElement>(null)
  const svgRef = useRef<SVGSVGElement>(null)
  const [width, setWidth] = useState(640)

  // Draw the lines in when the data changes (not on resize), so a new selection reads as
  // a new series rather than a jump. Skipped for reduced motion.
  const drawKey = `${dates[0]}|${dates.at(-1)}|${dates.length}|${series.map((s) => s.id).join(',')}`
  useGSAP(
    () => {
      const lines = svgRef.current?.querySelectorAll<SVGPolylineElement>('polyline[data-draw]')
      if (!lines?.length || prefersReducedMotion()) return
      lines.forEach((line) => {
        const length = line.getTotalLength()
        gsap.fromTo(
          line,
          { strokeDasharray: length, strokeDashoffset: length },
          { strokeDashoffset: 0, duration: 0.6, ease: EASE_OUT, clearProps: 'strokeDasharray,strokeDashoffset' },
        )
      })
    },
    { dependencies: [drawKey], scope: svgRef },
  )
  const [active, setActive] = useState<number | null>(null)

  useLayoutEffect(() => {
    const el = wrapRef.current
    if (!el) return
    const observer = new ResizeObserver(([entry]) => setWidth(Math.max(280, entry.contentRect.width)))
    observer.observe(el)
    return () => observer.disconnect()
  }, [])

  const { yTicks, yMin, yMax } = useMemo(() => {
    const all = series.flatMap((s) => s.values.filter((v): v is number => v != null))
    markers.forEach((m) => all.push(m.value))
    return niceScale(all)
  }, [series, markers])

  const plotW = width - PAD.left - PAD.right
  const plotH = height - PAD.top - PAD.bottom
  const n = dates.length
  const x = (i: number) => PAD.left + (n <= 1 ? plotW / 2 : (i / (n - 1)) * plotW)
  const y = (v: number) => PAD.top + plotH - ((v - yMin) / (yMax - yMin || 1)) * plotH

  const xTicks = useMemo(() => monthStarts(dates, Math.max(2, Math.floor(plotW / 90))), [dates, plotW])

  function indexAt(clientX: number) {
    const rect = wrapRef.current?.getBoundingClientRect()
    if (!rect || n === 0) return null
    const rel = (clientX - rect.left - PAD.left) / (plotW || 1)
    return Math.min(n - 1, Math.max(0, Math.round(rel * (n - 1))))
  }

  function onKey(e: KeyboardEvent) {
    if (n === 0) return
    if (e.key === 'ArrowRight' || e.key === 'ArrowLeft') {
      e.preventDefault()
      const step = e.key === 'ArrowRight' ? 1 : -1
      setActive((a) => Math.min(n - 1, Math.max(0, (a ?? (step > 0 ? -1 : n)) + step)))
    } else if (e.key === 'Escape') {
      setActive(null)
    }
  }

  const tipLeft = active == null ? 0 : x(active)
  const tipOnLeft = tipLeft > width * 0.6

  return (
    <div ref={wrapRef} className="relative w-full select-none">
      <svg
        ref={svgRef}
        width={width}
        height={height}
        role="img"
        aria-label={`${description} Use the left and right arrow keys to read values.`}
        tabIndex={0}
        onKeyDown={onKey}
        onBlur={() => setActive(null)}
        onPointerMove={(e: PointerEvent) => setActive(indexAt(e.clientX))}
        onPointerLeave={() => setActive(null)}
        className="block touch-pan-y outline-none focus-visible:outline-2 focus-visible:outline-gold"
      >
        {yTicks.map((t) => (
          <g key={t}>
            <line x1={PAD.left} x2={width - PAD.right} y1={y(t)} y2={y(t)} stroke="var(--color-rule)" strokeWidth={1} />
            <text x={PAD.left - 8} y={y(t)} dy="0.32em" textAnchor="end" className="num fill-ink-3 text-[11px]">
              {formatValue(t)}
            </text>
          </g>
        ))}
        <text x={PAD.left - 8} y={10} textAnchor="end" className="fill-ink-3 text-[11px]">{unit}</text>
        {xTicks.map((i) => (
          <text key={i} x={x(i)} y={height - 8} textAnchor="middle" className="fill-ink-3 text-[11px]">
            {monthTick(dates[i])}
          </text>
        ))}

        {series.map((s) => (
          <g key={s.id}>
            {segments(s.values).map((seg) =>
              seg.length === 1 ? (
                <circle key={seg[0]} cx={x(seg[0])} cy={y(s.values[seg[0]]!)} r={2.5} fill={s.color} />
              ) : (
                <polyline
                  key={seg[0]}
                  data-draw
                  points={seg.map((i) => `${x(i)},${y(s.values[i]!)}`).join(' ')}
                  fill="none"
                  stroke={s.color}
                  strokeWidth={s.width ?? 2}
                  strokeLinejoin="round"
                  strokeLinecap="round"
                />
              ),
            )}
          </g>
        ))}

        {markers.map((m, k) =>
          m.kind === 'flag' ? (
            <circle key={k} cx={x(m.index)} cy={y(m.value)} r={4.5} fill="var(--color-surface)" stroke="var(--color-ink)" strokeWidth={1.75} />
          ) : (
            <circle key={k} cx={x(m.index)} cy={y(m.value)} r={2} fill="var(--color-rule-strong)" />
          ),
        )}

        {active != null && (
          <g pointerEvents="none">
            <line x1={x(active)} x2={x(active)} y1={PAD.top} y2={PAD.top + plotH} stroke="var(--color-ink-3)" strokeWidth={1} />
            {series.map((s) =>
              s.values[active] != null ? (
                <circle key={s.id} cx={x(active)} cy={y(s.values[active]!)} r={4} fill={s.color} stroke="var(--color-surface)" strokeWidth={2} />
              ) : null,
            )}
          </g>
        )}
      </svg>

      {active != null && (
        <div
          role="status"
          className="pointer-events-none absolute top-2 z-10 min-w-44 rounded-xl border border-rule-strong bg-sunken px-2.5 py-2 text-xs shadow-[0_12px_28px_rgba(0,0,0,0.45)]"
          style={tipOnLeft ? { right: width - tipLeft + 10 } : { left: tipLeft + 10 }}
        >
          <div className="mb-1 font-medium text-ink">{day(dates[active])}</div>
          {series.map((s) => (
            <div key={s.id} className="flex items-center justify-between gap-3">
              <span className="flex items-center gap-1.5 text-ink-2">
                <span className="inline-block h-0.5 w-3" style={{ background: s.color }} />
                {s.label}
              </span>
              <span className="num text-ink">{s.values[active] != null ? formatValue(s.values[active]!) : 'no observation'}</span>
            </div>
          ))}
          {tooltipExtra?.(active)}
        </div>
      )}
    </div>
  )
}

/** Runs of consecutive indices with a value; a null ends a run. */
function segments(values: (number | null)[]): number[][] {
  const out: number[][] = []
  let run: number[] = []
  values.forEach((v, i) => {
    if (v == null) {
      if (run.length) out.push(run)
      run = []
    } else {
      run.push(i)
    }
  })
  if (run.length) out.push(run)
  return out
}

function niceScale(values: number[]) {
  if (values.length === 0) return { yTicks: [0, 1], yMin: 0, yMax: 1 }
  let lo = Math.min(...values)
  let hi = Math.max(...values)
  if (lo === hi) {
    const pad = Math.abs(lo) * 0.01 || 1
    lo -= pad
    hi += pad
  }
  const raw = (hi - lo) / 4
  const mag = 10 ** Math.floor(Math.log10(raw))
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw) ?? raw
  const yMin = Math.floor(lo / step) * step
  const yMax = Math.ceil(hi / step) * step
  const yTicks: number[] = []
  for (let t = yMin; t <= yMax + step / 2; t += step) yTicks.push(Number(t.toFixed(10)))
  return { yTicks, yMin, yMax }
}

function monthStarts(dates: string[], maxTicks: number): number[] {
  const starts: number[] = []
  dates.forEach((d, i) => {
    if (i === 0 || d.slice(0, 7) !== dates[i - 1].slice(0, 7)) starts.push(i)
  })
  const every = Math.ceil(starts.length / maxTicks) || 1
  return starts.filter((_, k) => k % every === 0)
}
