// A contract-pair spread with its trailing baseline, a HOLDOUT divider at the start of the pair's
// final holdout, and a scrubbable readout (pointer or arrow keys). Values come straight from the
// research run; nothing is smoothed or interpolated.

import { useLayoutEffect, useMemo, useRef, useState } from 'react'
import type { KeyboardEvent, PointerEvent } from 'react'
import type { Series } from '../../../api/types'
import { bps, day, fixed, money, monthTick } from '../../../lib/format'
import { STATUSES } from '../../../lib/labels'

const PAD = { top: 20, right: 12, bottom: 26, left: 48 }

export function SpreadChart({ series, holdoutFrom, height = 300 }: { series: Series; holdoutFrom: string | null; height?: number }) {
  const wrapRef = useRef<HTMLDivElement>(null)
  const [width, setWidth] = useState(720)
  const [active, setActive] = useState<number | null>(null)

  useLayoutEffect(() => {
    const el = wrapRef.current
    if (!el) return
    const ro = new ResizeObserver(([e]) => setWidth(Math.max(280, e.contentRect.width)))
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  const pts = series.points
  const n = pts.length
  const { ticks, lo, hi } = useMemo(() => {
    const vals = pts.flatMap((p) => (p.baseline_mean_bps == null ? [p.spread_bps] : [p.spread_bps, p.baseline_mean_bps]))
    return niceScale(vals)
  }, [pts])

  const plotW = width - PAD.left - PAD.right
  const plotH = height - PAD.top - PAD.bottom
  const x = (i: number) => PAD.left + (n <= 1 ? plotW / 2 : (i / (n - 1)) * plotW)
  const y = (v: number) => PAD.top + plotH - ((v - lo) / (hi - lo || 1)) * plotH

  // Where the holdout starts in this series: inside it, before it (whole series is holdout) or after it.
  const split = holdoutFrom == null ? -1 : pts.findIndex((p) => p.trade_date >= holdoutFrom)
  const holdoutX = split === -1 ? null : split === 0 ? PAD.left : (x(split - 1) + x(split)) / 2

  const path = (get: (i: number) => number | null) => {
    let d = ''
    let open = false
    pts.forEach((_, i) => {
      const v = get(i)
      if (v == null) {
        open = false
        return
      }
      d += `${open ? 'L' : 'M'}${x(i).toFixed(1)},${y(v).toFixed(1)} `
      open = true
    })
    return d
  }
  const spreadD = path((i) => (pts[i].eligible ? pts[i].spread_bps : null))
  const baseD = path((i) => pts[i].baseline_mean_bps)
  const months = pts.flatMap((p, i) => (i === 0 || p.trade_date.slice(0, 7) !== pts[i - 1].trade_date.slice(0, 7) ? [i] : []))
  const every = Math.ceil(months.length / Math.max(2, Math.floor(plotW / 90))) || 1

  const indexAt = (clientX: number) => {
    const r = wrapRef.current?.getBoundingClientRect()
    if (!r || n === 0) return null
    return Math.min(n - 1, Math.max(0, Math.round(((clientX - r.left - PAD.left) / (plotW || 1)) * (n - 1))))
  }
  const onKey = (e: KeyboardEvent) => {
    if (e.key === 'ArrowRight' || e.key === 'ArrowLeft') {
      e.preventDefault()
      const step = e.key === 'ArrowRight' ? 1 : -1
      setActive((a) => Math.min(n - 1, Math.max(0, (a ?? (step > 0 ? -1 : n)) + step)))
    } else if (e.key === 'Escape') setActive(null)
  }

  const p = active == null ? null : pts[active]
  const tipRight = active != null && x(active) > width * 0.6

  return (
    <div ref={wrapRef} className="relative w-full select-none">
      <svg
        width={width}
        height={height}
        role="img"
        aria-label={`Spread between ${series.contract_a} and ${series.contract_b} in basis points with its trailing baseline${holdoutX != null ? `; the final holdout starts ${day(holdoutFrom)}` : ''}. Use the left and right arrow keys to read values.`}
        tabIndex={0}
        onKeyDown={onKey}
        onBlur={() => setActive(null)}
        onPointerMove={(e: PointerEvent) => setActive(indexAt(e.clientX))}
        onPointerLeave={() => setActive(null)}
        className="block cursor-crosshair touch-pan-y outline-none focus-visible:outline-2 focus-visible:outline-gold"
      >
        <defs>
          <pattern id={`hold-${series.pair_id}`} width="8" height="8" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
            <line x1="0" y1="0" x2="0" y2="8" stroke="var(--color-gold)" strokeOpacity="0.09" strokeWidth="3" />
          </pattern>
        </defs>
        {holdoutX != null && (
          <rect x={holdoutX} y={PAD.top} width={width - PAD.right - holdoutX} height={plotH} fill={`url(#hold-${series.pair_id})`} />
        )}
        {ticks.map((t) => (
          <g key={t}>
            <line x1={PAD.left} x2={width - PAD.right} y1={y(t)} y2={y(t)} stroke="var(--color-rule)" />
            <text x={PAD.left - 8} y={y(t)} dy="0.32em" textAnchor="end" className="num fill-ink-3 text-[11px]">{bps(t, 0)}</text>
          </g>
        ))}
        <text x={PAD.left - 8} y={10} textAnchor="end" className="fill-ink-3 text-[11px]">bps</text>
        {months
          .filter((_, k) => k % every === 0)
          .map((i) => (
            <text key={i} x={x(i)} y={height - 8} textAnchor="middle" className="fill-ink-3 text-[11px]">{monthTick(pts[i].trade_date)}</text>
          ))}

        <path d={baseD} fill="none" stroke="var(--color-ink-3)" strokeWidth={1.2} strokeDasharray="4 4" />
        <path d={spreadD} fill="none" stroke="var(--color-gold)" strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />

        {pts.map((pt, i) =>
          !pt.eligible ? (
            <circle key={i} cx={x(i)} cy={y(pt.spread_bps)} r={2} fill="var(--color-rule-strong)" />
          ) : pt.status === 'statistical_anomaly' || pt.status === 'cost_adjusted_candidate' ? (
            <circle key={i} cx={x(i)} cy={y(pt.spread_bps)} r={4.5} fill="var(--color-surface)" stroke="var(--color-ink)" strokeWidth={1.75} />
          ) : null,
        )}

        {holdoutX != null && (
          <g pointerEvents="none">
            <line x1={holdoutX} x2={holdoutX} y1={PAD.top - 6} y2={PAD.top + plotH} stroke="var(--color-gold)" strokeOpacity={0.7} strokeDasharray="2 3" />
            <text x={holdoutX + 6} y={PAD.top + 4} className="num fill-gold text-[10px]" letterSpacing={1.2}>HOLDOUT</text>
          </g>
        )}

        {p && active != null && (
          <g pointerEvents="none">
            <line x1={x(active)} x2={x(active)} y1={PAD.top} y2={PAD.top + plotH} stroke="var(--color-ink)" strokeOpacity={0.35} />
            {p.baseline_mean_bps != null && <circle cx={x(active)} cy={y(p.baseline_mean_bps)} r={3} fill="var(--color-ink-3)" />}
            <circle cx={x(active)} cy={y(p.spread_bps)} r={4} fill="var(--color-gold)" stroke="var(--color-surface)" strokeWidth={2} />
          </g>
        )}
      </svg>

      {p && active != null && (
        <div
          role="status"
          className="pointer-events-none absolute top-2 z-10 min-w-48 bg-ink px-2.5 py-2 text-xs text-ground"
          style={tipRight ? { right: width - x(active) + 10 } : { left: x(active) + 10 }}
        >
          <div className="mb-1 flex items-baseline justify-between gap-3 font-medium">
            <span>{day(p.trade_date)}</span>
            {holdoutFrom && p.trade_date >= holdoutFrom && <span className="num text-[10px] tracking-wider">HOLDOUT</span>}
          </div>
          <div className="num flex justify-between gap-3"><span>Spread</span><span>{bps(p.spread_bps)} bps</span></div>
          <div className="num flex justify-between gap-3"><span>Baseline</span><span>{p.baseline_mean_bps == null ? '—' : `${bps(p.baseline_mean_bps)} bps`}</span></div>
          <div className="mt-1 border-t border-ground/20 pt-1">
            {STATUSES[p.status].label}
            {p.z_score != null ? `, z ${fixed(p.z_score)}` : ''}
          </div>
          {!p.eligible && <div>{p.ineligible_reasons.join('; ')}</div>}
          <div className="num">{p.leg_a.contract_id}: ₹{money(p.leg_a.per_gram_999)}/g</div>
          <div className="num">{p.leg_b.contract_id}: ₹{money(p.leg_b.per_gram_999)}/g</div>
        </div>
      )}
    </div>
  )
}

function niceScale(values: number[]) {
  if (values.length === 0) return { ticks: [0, 1], lo: 0, hi: 1 }
  let lo = Math.min(...values)
  let hi = Math.max(...values)
  if (lo === hi) {
    lo -= 1
    hi += 1
  }
  const raw = (hi - lo) / 4
  const mag = 10 ** Math.floor(Math.log10(raw))
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw) ?? raw
  const a = Math.floor(lo / step) * step
  const b = Math.ceil(hi / step) * step
  const ticks: number[] = []
  for (let t = a; t <= b + step / 2; t += step) ticks.push(Number(t.toFixed(10)))
  return { ticks, lo: a, hi: b }
}
