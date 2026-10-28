// Overview dashboard, adapted from the 21st.dev "Web3 bento" (@romanvasnev) for gold research.
// Presentational only: every number arrives through props, shaped by lib/bento-data.ts from
// the backend's responses. Nothing here simulates live data.

import { Activity, ArrowRight, BadgeCheck, CircleDot, Database, FlaskConical, Loader2, Sigma } from 'lucide-react'
import * as React from 'react'
import type { DataKind, PointStatus, Verdict } from '../../api/types'
import type { Composition, InstrumentCard, PairView, PriceSeries, SameDayView, SignalView, SpreadPoint } from '../../lib/bento-data'
import { BASELINE_DATES, contractLabel } from '../../lib/bento-data'
import { count, day, shortDay } from '../../lib/format'
import { STATUSES } from '../../lib/labels'

/* ------------------------------------------------------------------ */
/*  Props                                                              */
/* ------------------------------------------------------------------ */

export type ResearchState = 'loading' | 'none' | 'ready'

export interface GoldBentoProps {
  kind: DataKind | undefined
  /** Data is still being fetched for the first time. */
  loading: boolean
  price: PriceSeries | null
  instruments: InstrumentCard[]
  composition: Composition[]
  research: ResearchState
  pairs: PairView[]
  signals: SignalView[]
  /** The selected pair on the latest date, used until it has a baseline of BASELINE_DATES. */
  sameDay: (pairId: string) => SameDayView | null
  /** Eligible dates per pair a walk-forward verdict needs. */
  neededDates: number | null
  /** Real data held: the bundled MCX files (true) or browser uploads (false). */
  bundled?: boolean
  busy?: boolean
  onLoadDemo?: () => void
  onImport: () => void
  onRunResearch: () => void
  onOpenEvidence: () => void
  accent?: string
  accent2?: string
  className?: string
}

/* ------------------------------------------------------------------ */
/*  Helpers                                                            */
/* ------------------------------------------------------------------ */

const EASE = 'cubic-bezier(0.22, 1, 0.36, 1)'
const ACCENT = 'var(--color-gold)'
const ACCENT2 = 'var(--color-loss)'
const INK = 'var(--color-gold-ink)'

const rupees = new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 })
const inr = (v: number) => rupees.format(v)
const sign = (v: number) => (v >= 0 ? '+' : '−')
const signed = (v: number, d = 1) => `${sign(v)}${Math.abs(v).toFixed(d)}`

function cx(...parts: Array<string | false | null | undefined>) {
  return parts.filter(Boolean).join(' ')
}

function useReducedMotion() {
  const [r, setR] = React.useState(() => window.matchMedia('(prefers-reduced-motion: reduce)').matches)
  React.useEffect(() => {
    const mq = window.matchMedia('(prefers-reduced-motion: reduce)')
    const u = () => setR(mq.matches)
    mq.addEventListener('change', u)
    return () => mq.removeEventListener('change', u)
  }, [])
  return r
}

function useMounted() {
  const [on, setOn] = React.useState(false)
  React.useEffect(() => {
    const id = requestAnimationFrame(() => setOn(true))
    return () => cancelAnimationFrame(id)
  }, [])
  return on
}

function useCountUp(target: number, enabled: boolean, duration = 1300) {
  const [v, setV] = React.useState(0)
  React.useEffect(() => {
    if (!enabled) return
    let raf = 0
    const t0 = performance.now()
    const tick = (now: number) => {
      const p = Math.min(1, (now - t0) / duration)
      setV(target * (1 - Math.pow(1 - p, 4)))
      if (p < 1) raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [target, enabled, duration])
  return enabled ? v : target
}

function smooth(pts: ReadonlyArray<readonly [number, number]>) {
  return pts
    .map(([x, y], i) => {
      if (i === 0) return `M ${x.toFixed(1)} ${y.toFixed(1)}`
      const [px, py] = pts[i - 1]
      const m = (px + x) / 2
      return `C ${m.toFixed(1)} ${py.toFixed(1)}, ${m.toFixed(1)} ${y.toFixed(1)}, ${x.toFixed(1)} ${y.toFixed(1)}`
    })
    .join(' ')
}

/** The latest point that has a baseline, i.e. a z-score. */
function lastScored(points: SpreadPoint[]) {
  for (let i = points.length - 1; i >= 0; i--) if (points[i].z != null && points[i].std != null) return points[i]
  return null
}

/* ------------------------------------------------------------------ */
/*  Shell pieces                                                       */
/* ------------------------------------------------------------------ */

function Tile({
  title,
  action,
  className,
  children,
}: {
  title?: React.ReactNode
  action?: React.ReactNode
  className?: string
  children: React.ReactNode
}) {
  return (
    <section className={cx('relative flex min-w-0 flex-col overflow-hidden rounded-[26px] border border-border bg-card p-5 text-card-foreground', className)}>
      {(title || action) && (
        <header className="mb-4 flex items-center justify-between gap-3">
          {title && <h3 className="min-w-0 truncate text-[13px] font-medium text-muted-foreground">{title}</h3>}
          {action}
        </header>
      )}
      {children}
    </section>
  )
}

function Pills<T extends string>({ value, options, onChange, label }: { value: T; options: T[]; onChange: (v: T) => void; label: string }) {
  return (
    <div role="radiogroup" aria-label={label} className="inline-flex rounded-full border border-border p-0.5">
      {options.map((o) => (
        <button
          key={o}
          type="button"
          role="radio"
          aria-checked={o === value}
          onClick={() => onChange(o)}
          className={cx(
            'rounded-full px-2.5 py-1 font-mono text-[11px] font-medium transition-colors focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none',
            o === value ? 'bg-foreground text-background' : 'text-muted-foreground hover:text-foreground',
          )}
        >
          {o}
        </button>
      ))}
    </div>
  )
}

function Action({ children, onClick, primary, disabled }: { children: React.ReactNode; onClick?: () => void; primary?: boolean; disabled?: boolean }) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={cx(
        'inline-flex h-8 items-center gap-1.5 rounded-full px-3.5 text-[12px] font-semibold transition-[transform,background-color,border-color] active:scale-[0.97] disabled:cursor-not-allowed disabled:opacity-50',
        primary ? 'bg-foreground text-background hover:bg-foreground/85' : 'border border-border hover:border-muted-foreground',
      )}
    >
      {children}
    </button>
  )
}

/** What a tile shows when its data does not exist yet: one sentence and the step that creates it. */
function Missing({ children, action }: { children: React.ReactNode; action?: React.ReactNode }) {
  return (
    <div className="flex flex-1 flex-col items-start justify-center gap-3 rounded-2xl border border-dashed border-border p-4 text-[13px] leading-relaxed text-muted-foreground">
      <p>{children}</p>
      {action}
    </div>
  )
}

function Skeleton({ className }: { className: string }) {
  return <span aria-hidden className={cx('block rounded-xl bg-muted', className)} />
}

/** One plain line under an early, same-day view: what more history unlocks. */
function MoreData({ children }: { children: React.ReactNode }) {
  return <p className="mt-auto border-t border-border pt-3 text-[12px] leading-relaxed text-muted-foreground">{children}</p>
}

const needsDates = (what: string, loaded: number) => `${what} needs about ${BASELINE_DATES} trading days; ${loaded} loaded.`

/* ------------------------------------------------------------------ */
/*  Hero: latest close + daily change bars                             */
/* ------------------------------------------------------------------ */

function HeroTile({ price, loading, reduced, empty }: { price: PriceSeries | null; loading: boolean; reduced: boolean; empty: React.ReactNode }) {
  const mounted = useMounted()
  const points = price?.points ?? []
  const value = points.at(-1)?.price ?? 0
  const shown = useCountUp(value, !reduced)
  const daily = points.slice(1).map((p, i) => ({ date: p.date, pct: (p.price / points[i].price - 1) * 100 }))
  const maxAbs = Math.max(...daily.map((d) => Math.abs(d.pct)), 0.01)
  const first = points[0]?.price ?? 0
  const change = value - first
  const pct = first ? (value / first - 1) * 100 : 0
  const [hover, setHover] = React.useState<number | null>(null)

  return (
    <Tile className="sm:col-span-2 lg:col-span-2 lg:col-start-1 lg:row-start-1">
      <div className="flex flex-wrap items-start justify-between gap-6">
        <div className="min-w-0">
          <h1 className="text-[28px] leading-[1.1] font-semibold tracking-[-0.03em] sm:text-[34px]">
            Gold, <span style={{ color: ACCENT }}>{price ? contractLabel(price.symbol, price.expiry) : 'MCX'}</span>
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            {price ? `Daily closes, normalised to 999 fineness · to ${day(points.at(-1)!.date)}` : 'Futures research on MCX gold contracts.'}
          </p>
        </div>
        {price && (
          <div className="ml-auto text-right">
            <p className="text-[12px] text-muted-foreground">Last close · ₹ per 10 g</p>
            <p className="font-mono text-[34px] leading-none font-semibold tracking-[-0.04em] tabular-nums sm:text-[40px]">{inr(shown)}</p>
            <p className="mt-1.5 font-mono text-[12px] tabular-nums">
              <span style={{ color: change >= 0 ? ACCENT : ACCENT2 }}>
                {sign(change)}
                {inr(Math.abs(change))} ({signed(pct)}%)
              </span>
              <span className="text-muted-foreground"> · {daily.length} {daily.length === 1 ? 'session' : 'sessions'}</span>
            </p>
          </div>
        )}
      </div>

      {loading ? (
        <Skeleton className="mt-6 h-32 w-full" />
      ) : !price || daily.length === 0 ? (
        <div className="mt-6 flex flex-1">{empty}</div>
      ) : (
        <div className="mt-6 flex flex-1 flex-col">
          <div className="flex flex-1 items-end gap-[3px]" style={{ minHeight: 96 }} onPointerLeave={() => setHover(null)}>
            {daily.map((d, i) => {
              const h = 18 + (Math.abs(d.pct) / maxAbs) * 82
              const up = d.pct >= 0
              return (
                <button
                  key={d.date}
                  type="button"
                  onPointerEnter={() => setHover(i)}
                  onFocus={() => setHover(i)}
                  onBlur={() => setHover(null)}
                  aria-label={`${day(d.date)}: ${signed(d.pct, 2)}%`}
                  className="relative flex-1 rounded-[4px] focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
                  style={{
                    height: mounted || reduced ? `${h}%` : '6%',
                    background: up ? ACCENT : ACCENT2,
                    opacity: hover === null ? 0.35 + (Math.abs(d.pct) / maxAbs) * 0.65 : hover === i ? 1 : 0.25,
                    transition: reduced ? 'opacity 200ms ease' : `height 900ms ${EASE} ${i * 18}ms, opacity 200ms ease`,
                  }}
                />
              )
            })}
          </div>
          <div className="mt-2 flex items-center justify-between font-mono text-[11px] text-muted-foreground">
            <span>{shortDay(daily[0].date)}</span>
            <span className="text-foreground" aria-live="polite">
              {hover !== null ? `${shortDay(daily[hover].date)} · ${signed(daily[hover].pct, 2)}%` : 'Daily change'}
            </span>
            <span>{shortDay(daily.at(-1)!.date)}</span>
          </div>
        </div>
      )}
    </Tile>
  )
}

/* ------------------------------------------------------------------ */
/*  Contracts: fanned card stack, click a card to bring it forward     */
/* ------------------------------------------------------------------ */

// Card faces by contract: yellow, rose, white and antique gold.
const FACES: Record<string, { color: string; color2: string }> = {
  GOLDM: { color: 'oklch(0.88 0.13 90)', color2: 'oklch(0.74 0.15 72)' },
  GOLDTEN: { color: 'oklch(0.84 0.08 45)', color2: 'oklch(0.7 0.11 32)' },
  GOLDGUINEA: { color: 'oklch(0.92 0.02 95)', color2: 'oklch(0.76 0.03 80)' },
  GOLDPETAL: { color: 'oklch(0.78 0.1 78)', color2: 'oklch(0.6 0.1 60)' },
}
const FACE_FALLBACK = { color: 'oklch(0.84 0.1 85)', color2: 'oklch(0.66 0.12 70)' }
const CARD_INK = 'oklch(0.24 0.04 65)'

function Chip() {
  return (
    <svg width="26" height="20" viewBox="0 0 26 20" aria-hidden>
      <rect x="0.5" y="0.5" width="25" height="19" rx="4.5" fill="oklch(0.9 0.06 90)" stroke="oklch(0.62 0.07 80 / 0.6)" />
      <path d="M0.5 7h7.5v6H0.5M25.5 7H18v6h7.5M8 0.5v19M18 0.5v19M8 10h10" fill="none" stroke="oklch(0.6 0.07 80 / 0.55)" strokeWidth="0.9" />
    </svg>
  )
}

function CardFace({ c, glare }: { c: InstrumentCard; glare: number }) {
  const f = FACES[c.symbol] ?? FACE_FALLBACK
  return (
    <>
      <span
        aria-hidden
        className="absolute inset-0 overflow-hidden rounded-[12px]"
        style={{
          backgroundImage: [
            'linear-gradient(180deg, oklch(1 0 0 / 0.3) 0%, transparent 34%)',
            `radial-gradient(110% 90% at 100% 0%, ${f.color2} 0%, transparent 60%)`,
            `linear-gradient(135deg, ${f.color} 0%, ${f.color2} 100%)`,
          ].join(', '),
          boxShadow: 'inset 0 1px 0 oklch(1 0 0 / 0.5), inset 0 0 0 1px oklch(1 0 0 / 0.16)',
        }}
      >
        <span
          className="absolute inset-0"
          style={{
            backgroundImage:
              'linear-gradient(115deg, transparent 18%, oklch(0.95 0.08 90 / 0.55) 34%, oklch(0.98 0.03 95 / 0.6) 46%, oklch(0.9 0.1 75 / 0.45) 58%, transparent 76%)',
            backgroundSize: '260% 100%',
            backgroundPosition: `${glare}% 0`,
            mixBlendMode: 'soft-light',
            transition: `background-position 700ms ${EASE}`,
          }}
        />
      </span>
      <span className="relative flex items-center justify-between gap-3 px-4 pt-4">
        <span className="flex min-w-0 items-center gap-2.5">
          <Chip />
          <span className="truncate text-[13px] font-bold tracking-tight">{c.symbol}</span>
        </span>
        <span className="shrink-0 font-mono text-[12px] font-semibold tabular-nums">{count(Number(c.tradingUnitG))} g lot</span>
      </span>
      <span className="absolute right-4 bottom-3.5 font-mono text-[11px] font-semibold opacity-70">{c.fineness}</span>
    </>
  )
}

function CardsTile({ cards, front: initialFront, reduced }: { cards: InstrumentCard[]; front?: string; reduced: boolean }) {
  // Back → front; the contract shown in the hero starts in front.
  const [order, setOrder] = React.useState(() => {
    const ids = cards.map((c) => c.symbol).reverse()
    return initialFront && ids.includes(initialFront) ? [...ids.filter((x) => x !== initialFront), initialFront] : ids
  })
  const mounted = useMounted()
  const PEEK = 40
  const depth = order.length - 1
  const front = cards.find((c) => c.symbol === order[order.length - 1]) ?? cards[0]
  const [glare, setGlare] = React.useState(30)
  const dragGlare = React.useRef(false)
  React.useEffect(() => {
    if (reduced) return
    let raf = 0
    const t0 = performance.now()
    const tick = (now: number) => {
      setGlare((g) => (dragGlare.current ? g : 30 + Math.sin((now - t0) / 2600) * 30))
      raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [reduced])

  return (
    <Tile
      title={
        <span>
          Contracts <sup className="font-mono text-[10px]">{cards.length}</sup>
        </span>
      }
      className="lg:col-start-3 lg:row-start-1"
    >
      {!front ? (
        <Missing>Contract specifications could not be loaded.</Missing>
      ) : (
        <div
          className="relative -mx-5 -mb-5 flex flex-1 flex-col justify-end overflow-hidden pt-1"
          onPointerMove={(e) => {
            const r = e.currentTarget.getBoundingClientRect()
            dragGlare.current = true
            setGlare(((e.clientX - r.left) / r.width) * 100)
          }}
          onPointerLeave={() => {
            dragGlare.current = false
          }}
        >
          <div className="relative">
            {order.map((id, pos) => {
              const c = cards.find((x) => x.symbol === id)!
              const fromFront = order.length - 1 - pos
              const isFront = fromFront === 0
              return (
                <button
                  key={id}
                  type="button"
                  onClick={() => !isFront && setOrder((o) => [...o.filter((x) => x !== id), id])}
                  aria-label={`${c.name} (${c.symbol})${isFront ? ', selected' : ', bring to front'}`}
                  aria-pressed={isFront}
                  className="absolute left-1/2 block w-[calc(100%-32px)] max-w-[300px] rounded-[12px] p-0 text-left focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
                  style={{
                    top: (depth - fromFront) * PEEK,
                    zIndex: pos + 1,
                    transform: `translateX(-50%) scale(${1 - fromFront * 0.055}) translateY(${mounted || reduced ? 0 : 20}px)`,
                    transformOrigin: 'top center',
                    opacity: mounted || reduced ? 1 : 0,
                    color: CARD_INK,
                    boxShadow: '0 -10px 28px -14px oklch(0 0 0 / 0.75)',
                    transition: reduced
                      ? 'none'
                      : `top 650ms cubic-bezier(0.34, 1.35, 0.64, 1), transform 650ms cubic-bezier(0.34, 1.35, 0.64, 1), opacity 500ms ease ${pos * 90}ms`,
                    cursor: isFront ? 'default' : 'pointer',
                  }}
                >
                  <span className="relative block w-full" style={{ paddingTop: '63.08%' }}>
                    <span className="absolute inset-0 block">
                      <CardFace c={c} glare={glare + fromFront * 18} />
                    </span>
                  </span>
                </button>
              )
            })}
            {/* Gives the stack its real height; only the top of the front card shows above the panel. */}
            <div aria-hidden className="invisible mx-auto w-[calc(100%-32px)] max-w-[300px] shrink-0" style={{ marginTop: depth * PEEK }}>
              <div style={{ paddingTop: '30%' }} />
            </div>
          </div>

          <div
            className="relative z-10 flex shrink-0 items-end justify-between gap-3 px-5 pb-4"
            style={{
              height: 88,
              background: 'color-mix(in oklch, var(--color-card) 72%, transparent)',
              backdropFilter: 'blur(18px) saturate(1.3)',
              WebkitBackdropFilter: 'blur(18px) saturate(1.3)',
              borderTop: '1px solid color-mix(in oklch, var(--color-foreground) 10%, transparent)',
            }}
            aria-live="polite"
          >
            <div className="min-w-0">
              <p className="truncate text-[15px] font-semibold">{front.name}</p>
              <p className="mt-1 truncate text-[11px] text-muted-foreground">
                {count(Number(front.quoteBaseG))} g quote · {front.verified ? 'verified' : 'unverified'}
              </p>
            </div>
            <div className="shrink-0 text-right">
              <p className="font-mono text-[15px] font-semibold tabular-nums">{front.latest ? inr(front.latest.price) : '—'}</p>
              <p className="mt-1 font-mono text-[10px] text-muted-foreground">{front.latest ? `/10 g · ${shortDay(front.latest.date)}` : 'no data'}</p>
            </div>
          </div>
        </div>
      )}
    </Tile>
  )
}

/* ------------------------------------------------------------------ */
/*  Deviation gauge: today's z-score against the flag threshold        */
/* ------------------------------------------------------------------ */

const R = 62
const arcPoint = (t: number, r: number) => {
  const a = Math.PI * (1 - t)
  return [75 + r * Math.cos(a), 78 - r * Math.sin(a)] as const
}

function SameDayDeviationTile({ early }: { early: SameDayView }) {
  const r = early.maxResidual
  return (
    <Tile title="Same-day deviation (1 day of data)" className="lg:col-start-4 lg:row-start-1">
      <div className="flex flex-1 flex-col justify-center gap-4">
        <div>
          <p className="font-mono text-[26px] leading-none font-semibold tabular-nums">
            {early.gap.adjusted == null ? '—' : signed(early.gap.adjusted)} <span className="text-sm text-muted-foreground">bps</span>
          </p>
          <p className="mt-1.5 text-[12px] leading-snug text-muted-foreground">Carry-adjusted gap · {shortDay(early.date)} · {early.gap.legs}</p>
        </div>
        <div>
          <p className="font-mono text-[20px] leading-none font-semibold tabular-nums">
            {r ? signed(r.bps) : '—'} <span className="text-sm text-muted-foreground">bps</span>
          </p>
          <p className="mt-1.5 text-[12px] leading-snug text-muted-foreground">
            Largest distance of any expiry from its carry line{r ? ` · ${r.label}` : ''}
          </p>
        </div>
      </div>
      <MoreData>{needsDates("A z-score against the pair's normal gap", early.datesLoaded)}</MoreData>
    </Tile>
  )
}

function GaugeTile({ pair, threshold, onThreshold, empty }: { pair: PairView | null; threshold: number; onThreshold: (z: number) => void; empty: React.ReactNode }) {
  const point = pair ? lastScored(pair.points) : null
  const z = point?.z ?? 0
  const max = Math.max(4, threshold * 2)
  const t = Math.min(1, Math.abs(z) / max)
  const len = Math.PI * R
  const angle = -90 + t * 180
  const flagged = Math.abs(z) >= threshold
  const [x1, y1] = arcPoint(threshold / max, R - 9)
  const [x2, y2] = arcPoint(threshold / max, R + 9)
  const fmtZ = (v: number) => `${v}σ`

  return (
    <Tile title="Deviation" className="lg:col-start-4 lg:row-start-1" action={<span className="font-mono text-[11px] text-muted-foreground">z-score</span>}>
      {!pair || !point ? (
        empty
      ) : (
        <>
          <div className="flex flex-1 flex-col items-center justify-center">
            <svg width="150" height="86" viewBox="0 0 150 86" aria-hidden>
              <path d="M 13 78 A 62 62 0 0 1 137 78" fill="none" strokeWidth="10" strokeLinecap="round" style={{ stroke: 'var(--color-muted)' }} />
              <path
                d="M 13 78 A 62 62 0 0 1 137 78"
                fill="none"
                strokeWidth="10"
                strokeLinecap="round"
                strokeDasharray={len}
                style={{
                  stroke: flagged ? ACCENT : 'var(--color-muted-foreground)',
                  strokeDashoffset: len * (1 - t),
                  transition: `stroke-dashoffset 900ms ${EASE}, stroke 300ms ease`,
                }}
              />
              <line x1={x1} y1={y1} x2={x2} y2={y2} strokeWidth="2" strokeLinecap="round" style={{ stroke: 'var(--color-foreground)', opacity: 0.55 }} />
              <g style={{ transform: `rotate(${angle}deg)`, transformOrigin: '75px 78px', transition: `transform 900ms ${EASE}` }}>
                <line x1="75" y1="78" x2="75" y2="30" strokeWidth="2.5" strokeLinecap="round" style={{ stroke: 'var(--color-foreground)' }} />
              </g>
              <circle cx="75" cy="78" r="5" style={{ fill: 'var(--color-foreground)' }} />
            </svg>
            <p className="mt-2 font-mono text-[26px] leading-none font-semibold tabular-nums">
              {signed(z, 2)} <span className="text-sm text-muted-foreground">σ</span>
            </p>
            <p className="mt-1 text-center font-mono text-[11px] text-muted-foreground tabular-nums">
              {flagged ? 'beyond' : 'within'} {fmtZ(threshold)} · {shortDay(point.date)}
            </p>
          </div>
          <div className="mt-4 flex justify-center">
            <Pills
              label="Flag threshold"
              value={fmtZ(threshold)}
              options={pair.zOptions.map(fmtZ)}
              onChange={(v) => onThreshold(Number(v.slice(0, -1)))}
            />
          </div>
        </>
      )}
    </Tile>
  )
}

/* ------------------------------------------------------------------ */
/*  Spread vs baseline chart                                           */
/* ------------------------------------------------------------------ */

type Range = '1M' | 'All'

const bps = (v: number | null) => (v == null ? '—' : `${signed(v)} bps`)

function SameDayChartTile({ early }: { early: SameDayView }) {
  const cur = early.history.at(-1)
  return (
    <Tile
      title={`Gap by date · ${early.gap.legs}`}
      className="sm:col-span-2 lg:col-span-2 lg:col-start-1 lg:row-span-2 lg:row-start-2"
    >
      <div className="flex flex-wrap items-end gap-x-8 gap-y-2">
        <div>
          <p className="text-[12px] text-muted-foreground">Raw gap</p>
          <p className="mt-1 font-mono text-[22px] font-semibold tabular-nums">
            {cur ? signed(cur.raw) : '—'} <span className="text-[13px] text-muted-foreground">bps</span>
          </p>
        </div>
        <div>
          <p className="text-[12px] text-muted-foreground">Carry-adjusted</p>
          <p className="mt-1 font-mono text-[22px] font-semibold tabular-nums" style={{ color: ACCENT }}>
            {cur?.adjusted == null ? '—' : signed(cur.adjusted)} <span className="text-[13px] text-muted-foreground">bps</span>
          </p>
        </div>
        <span className="ml-auto rounded-full bg-muted px-2.5 py-1 font-mono text-[11px] font-semibold text-muted-foreground">
          {shortDay(early.date)} · no baseline yet
        </span>
      </div>

      <table className="mt-5 w-full text-[13px]">
        <caption className="sr-only">The same two contracts on each loaded date</caption>
        <thead>
          <tr className="text-left text-[11px] text-muted-foreground">
            <th scope="col" className="pb-1.5 font-normal">Date</th>
            <th scope="col" className="pb-1.5 text-right font-normal">Raw</th>
            <th scope="col" className="pb-1.5 text-right font-normal">Carry-adjusted</th>
          </tr>
        </thead>
        <tbody className="font-mono tabular-nums">
          {early.history.map((h) => (
            <tr key={h.date} className="border-t border-border">
              <td className="py-1.5">{day(h.date)}</td>
              <td className="py-1.5 text-right">{bps(h.raw)}</td>
              <td className="py-1.5 text-right">{bps(h.adjusted)}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <p className="mt-5 text-[12px] font-medium text-muted-foreground">Every expiry pairing · {shortDay(early.date)}</p>
      <ul className="mt-1.5 space-y-1 text-[12px]">
        {early.gaps.map((g) => (
          <li key={g.legs} className="flex items-baseline justify-between gap-3">
            <span className="min-w-0 truncate">
              {g.legs}
              {!g.tradeable && <span className="text-muted-foreground"> · in expiry buffer</span>}
            </span>
            <span className="shrink-0 font-mono tabular-nums">{bps(g.adjusted)}</span>
          </li>
        ))}
      </ul>
      {early.gap.locationBasis && (
        <p className="mt-3 text-[12px] text-muted-foreground">GOLDPETAL is priced in Mumbai, the others in Ahmedabad; these gaps include that location basis.</p>
      )}
      <div className="mt-auto pt-4">
        <MoreData>{needsDates("The pair's normal gap, and a chart of the spread against it,", early.datesLoaded)}</MoreData>
      </div>
    </Tile>
  )
}

function ChartTile({ pair, threshold, reduced, empty }: { pair: PairView | null; threshold: number; reduced: boolean; empty: React.ReactNode }) {
  const uid = React.useId().replace(/:/g, '')
  const [range, setRange] = React.useState<Range>('All')
  const [hover, setHover] = React.useState<number | null>(null)
  const mounted = useMounted()
  const pts = pair ? (range === '1M' ? pair.points.slice(-21) : pair.points) : []
  const ready = pts.length >= 2

  const W = 640
  const H = 220
  const values = pts.flatMap((p) => (p.baseline == null ? [p.spread] : [p.spread, p.baseline]))
  const lo = Math.min(...values)
  const hi = Math.max(...values)
  const xAt = (i: number) => (i / Math.max(1, pts.length - 1)) * W
  const y = (v: number) => H - 16 - ((v - lo) / (hi - lo || 1)) * (H - 40)
  const pa = pts.map((p, i) => [xAt(i), y(p.spread)] as const)
  const pb = pts.flatMap((p, i) => (p.baseline == null ? [] : [[xAt(i), y(p.baseline)] as const]))
  const la = smooth(pa)
  const lb = smooth(pb)
  const idx = hover ?? pts.length - 1
  const cur = pts[idx]
  const flaggedIdx = pts.flatMap((p, i) => (p.z != null && Math.abs(p.z) >= threshold ? [i] : []))
  const ticks = ready ? [0, 0.25, 0.5, 0.75, 1].map((f) => pts[Math.round(f * (pts.length - 1))].date) : []

  const onMove = (e: React.PointerEvent<HTMLDivElement>) => {
    const r = e.currentTarget.getBoundingClientRect()
    setHover(Math.max(0, Math.min(pts.length - 1, Math.round(((e.clientX - r.left) / r.width) * (pts.length - 1)))))
  }

  return (
    <Tile
      title={pair ? `Spread vs baseline · ${pair.legs}` : 'Spread vs baseline'}
      className="sm:col-span-2 lg:col-span-2 lg:col-start-1 lg:row-span-2 lg:row-start-2"
      action={ready && <Pills label="Chart range" value={range} options={['1M', 'All']} onChange={setRange} />}
    >
      {!ready || !cur ? (
        empty
      ) : (
        <>
          <div className="flex flex-wrap items-end gap-x-8 gap-y-2">
            <div>
              <p className="flex items-center gap-2 text-[12px] text-muted-foreground">
                <span className="h-[3px] w-4 rounded-full" style={{ background: ACCENT }} aria-hidden />
                Spread
              </p>
              <p className="mt-1 font-mono text-[22px] font-semibold tabular-nums">
                {signed(cur.spread)} <span className="text-[13px] text-muted-foreground">bps</span>
              </p>
            </div>
            <div>
              <p className="flex items-center gap-2 text-[12px] text-muted-foreground">
                <span className="h-0 w-4 border-t-2 border-dashed border-muted-foreground" aria-hidden />
                Baseline ({pair!.baselineWindow} obs)
              </p>
              <p className="mt-1 font-mono text-[22px] font-semibold text-muted-foreground tabular-nums">
                {cur.baseline == null ? '—' : signed(cur.baseline)} <span className="text-[13px]">bps</span>
              </p>
            </div>
            <span
              className="ml-auto rounded-full px-2.5 py-1 font-mono text-[11px] font-semibold tabular-nums"
              style={
                cur.z != null && Math.abs(cur.z) >= threshold
                  ? { background: `color-mix(in oklch, ${ACCENT} 18%, transparent)`, color: ACCENT }
                  : { background: 'var(--color-muted)', color: 'var(--color-muted-foreground)' }
              }
            >
              {shortDay(cur.date)} · {cur.z == null ? 'no baseline yet' : `z ${signed(cur.z, 2)}`}
            </span>
          </div>

          <div
            className="relative mt-4 flex-1 touch-pan-y"
            style={{ minHeight: 220 }}
            onPointerMove={onMove}
            onPointerLeave={() => setHover(null)}
            role="img"
            aria-label={`Spread of ${pair!.legs} over ${pts.length} eligible sessions, latest ${signed(pts.at(-1)!.spread)} bps; ${flaggedIdx.length} sessions beyond ${threshold} sigma`}
          >
            <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" className="absolute inset-0 h-full w-full" aria-hidden>
              <defs>
                <linearGradient id={`${uid}-f`} x1="0" x2="0" y1="0" y2="1">
                  <stop offset="0" style={{ stopColor: ACCENT, stopOpacity: 0.28 }} />
                  <stop offset="1" style={{ stopColor: ACCENT, stopOpacity: 0 }} />
                </linearGradient>
              </defs>
              {[0.25, 0.5, 0.75].map((f) => (
                <line key={f} x1={0} x2={W} y1={H * f} y2={H * f} vectorEffect="non-scaling-stroke" strokeDasharray="1 5" style={{ stroke: 'var(--color-border)' }} />
              ))}
              <path d={`${la} L ${W} ${H} L 0 ${H} Z`} fill={`url(#${uid}-f)`} style={{ opacity: mounted || reduced ? 1 : 0, transition: 'opacity 900ms ease 400ms' }} />
              {pb.length >= 2 && (
                <path d={lb} fill="none" strokeWidth={1.5} strokeDasharray="4 5" vectorEffect="non-scaling-stroke" style={{ stroke: 'var(--color-muted-foreground)' }} />
              )}
              <path
                key={`${pair!.id}-${range}`}
                d={la}
                fill="none"
                strokeWidth={2.5}
                strokeLinecap="round"
                vectorEffect="non-scaling-stroke"
                pathLength={1}
                style={{ stroke: ACCENT, strokeDasharray: 1, strokeDashoffset: mounted || reduced ? 0 : 1, transition: reduced ? 'none' : `stroke-dashoffset 1300ms ${EASE}` }}
              />
            </svg>
            {flaggedIdx.map((i) => (
              <span
                key={i}
                aria-hidden
                className="pointer-events-none absolute size-2 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-card"
                style={{ left: `${(pa[i][0] / W) * 100}%`, top: `${(pa[i][1] / H) * 100}%`, background: ACCENT }}
              />
            ))}
            <span aria-hidden className="pointer-events-none absolute inset-y-0 w-px -translate-x-1/2 bg-border" style={{ left: `${(pa[idx][0] / W) * 100}%`, opacity: hover !== null ? 1 : 0 }} />
            <span
              aria-hidden
              className="pointer-events-none absolute size-3.5 -translate-x-1/2 -translate-y-1/2 rounded-full border-[3px] border-card"
              style={{ left: `${(pa[idx][0] / W) * 100}%`, top: `${(pa[idx][1] / H) * 100}%`, background: ACCENT }}
            />
            {cur.baseline != null && (
              <span
                aria-hidden
                className="pointer-events-none absolute size-2.5 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-card bg-muted-foreground"
                style={{ left: `${(pa[idx][0] / W) * 100}%`, top: `${(y(cur.baseline) / H) * 100}%`, opacity: hover !== null ? 1 : 0 }}
              />
            )}
          </div>
          <div className="mt-3 flex justify-between font-mono text-[11px] text-muted-foreground" aria-hidden>
            {ticks.map((d, i) => (
              <span key={`${d}-${i}`}>{shortDay(d)}</span>
            ))}
          </div>
        </>
      )}
    </Tile>
  )
}

/* ------------------------------------------------------------------ */
/*  Dataset composition: segmented bar                                 */
/* ------------------------------------------------------------------ */

const SEGMENTS = [ACCENT, 'oklch(0.92 0.06 92)', 'oklch(0.72 0.03 80)', 'oklch(0.52 0.02 80)', 'oklch(0.4 0.01 80)']

function CompositionTile({ composition, empty }: { composition: Composition[]; empty: React.ReactNode }) {
  const mounted = useMounted()
  const total = composition.reduce((s, a) => s + a.value, 0)
  const [hover, setHover] = React.useState<number | null>(null)

  return (
    <Tile title="Observations by contract" className="lg:col-start-3 lg:row-start-2">
      {total === 0 ? (
        empty
      ) : (
        <>
          <p className="font-mono text-[22px] font-semibold tabular-nums">
            {count(total)} <span className="text-[13px] text-muted-foreground">obs</span>
          </p>
          <div className="mt-4 flex h-9 gap-1" onPointerLeave={() => setHover(null)}>
            {composition.map((a, i) => (
              <span
                key={a.symbol}
                onPointerEnter={() => setHover(i)}
                className="rounded-[8px]"
                style={{
                  flexBasis: mounted ? `${(a.value / total) * 100}%` : `${100 / composition.length}%`,
                  background: SEGMENTS[i % SEGMENTS.length],
                  opacity: hover === null || hover === i ? 1 : 0.3,
                  transition: `flex-basis 1000ms ${EASE} ${200 + i * 60}ms, opacity 200ms ease`,
                }}
                aria-hidden
              />
            ))}
          </div>
          <ul className="mt-4 grid grid-cols-1 gap-y-2">
            {composition.map((a, i) => (
              <li
                key={a.symbol}
                className="flex items-center justify-between gap-2 text-[12px]"
                onPointerEnter={() => setHover(i)}
                onPointerLeave={() => setHover(null)}
              >
                <span className="flex min-w-0 items-center gap-2">
                  <span className="size-2 shrink-0 rounded-full" style={{ background: SEGMENTS[i % SEGMENTS.length] }} aria-hidden />
                  <span className="truncate">{a.symbol}</span>
                </span>
                <span className="font-mono text-muted-foreground tabular-nums">{((a.value / total) * 100).toFixed(1)}%</span>
              </li>
            ))}
          </ul>
        </>
      )}
    </Tile>
  )
}

/* ------------------------------------------------------------------ */
/*  Verdict: the solid gold tile                                       */
/* ------------------------------------------------------------------ */

const VERDICT_SHORT: Record<Verdict, { label: string; negative: boolean }> = {
  insufficient_data: { label: 'Insufficient data', negative: false },
  not_supported: { label: 'Not supported', negative: true },
  supported_before_costs_costs_unknown: { label: 'Supported pre-costs', negative: false },
  not_supported_after_costs: { label: 'Fails after costs', negative: true },
  historically_validated: { label: 'Validated', negative: false },
}

function VerdictTile({
  pair,
  research,
  hasData,
  neededDates,
  onOpenEvidence,
  onRunResearch,
}: {
  pair: PairView | null
  research: ResearchState
  hasData: boolean
  neededDates: number | null
  onOpenEvidence: () => void
  onRunResearch: () => void
}) {
  const v = pair ? VERDICT_SHORT[pair.verdict] : null
  const h = pair?.holdout
  const tint = (a: number) => `color-mix(in oklch, ${INK} ${a}%, transparent)`

  return (
    <section
      className="relative flex min-w-0 flex-col overflow-hidden rounded-[26px] p-5 lg:col-start-4 lg:row-span-2 lg:row-start-2"
      style={{ background: ACCENT, color: INK }}
      aria-label="Research verdict"
    >
      <header className="flex items-center justify-between gap-2">
        <h3 className="text-[13px] font-semibold opacity-75">Verdict</h3>
        <span className="flex items-center gap-1.5 rounded-full px-2 py-0.5 font-mono text-[11px] font-semibold" style={{ background: tint(12) }}>
          <span className="size-1.5 rounded-full" style={{ background: v?.negative ? 'oklch(0.5 0.17 28)' : INK }} aria-hidden />
          {research === 'loading' ? 'Loading' : v ? v.label : hasData ? 'Not run' : 'No data'}
        </span>
      </header>

      {pair && !h && research === 'ready' ? (
        <div className="flex flex-1 flex-col">
          <p className="mt-5 font-mono text-[52px] leading-none font-semibold tracking-[-0.05em] tabular-nums">
            {pair.eligibleDates}
            <span className="text-[22px]">/{neededDates ?? '—'}</span>
          </p>
          <p className="mt-1 text-[12px] font-medium opacity-70">eligible dates · {pair.label}</p>
          <p className="mt-5 text-[13px] leading-relaxed font-medium opacity-80">
            Research has run on the loaded data. A walk-forward verdict needs {neededDates ?? 'several hundred'} eligible dates per pair:
            three training folds and a 30% holdout, each able to hold {pair.minEvents} separate signals. Until then no edge is claimed.
          </p>
          <div className="mt-auto pt-6">
            <button
              type="button"
              onClick={onOpenEvidence}
              className="flex w-full items-center justify-center gap-2 rounded-2xl py-3 text-sm font-semibold transition-transform focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:outline-none active:scale-[0.98]"
              style={{ background: INK, color: ACCENT }}
            >
              Open evidence <ArrowRight className="size-4" aria-hidden />
            </button>
          </div>
        </div>
      ) : !pair || !h ? (
        <div className="flex flex-1 flex-col">
          <p className="mt-5 font-mono text-[52px] leading-none font-semibold tracking-[-0.05em]">—</p>
          <p className="mt-3 text-[13px] leading-relaxed font-medium opacity-80">
            {!hasData
              ? 'Load data, then run research to test whether contract spreads revert after unusual moves.'
              : research === 'loading'
                ? 'Loading the latest research run.'
                : 'Research has not been run on the loaded data, so no verdict exists yet.'}
          </p>
          {hasData && research === 'none' && (
            <button
              type="button"
              onClick={onRunResearch}
              className="mt-auto flex w-full items-center justify-center gap-2 rounded-2xl py-3 text-sm font-semibold transition-transform focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:outline-none active:scale-[0.98]"
              style={{ background: INK, color: ACCENT }}
            >
              <FlaskConical className="size-4" aria-hidden /> Run research
            </button>
          )}
        </div>
      ) : (
        <>
          <p className="mt-5 font-mono text-[52px] leading-none font-semibold tracking-[-0.05em] tabular-nums">
            {h.n}
            <span className="text-[22px]">/{pair.minEvents}</span>
          </p>
          <p className="mt-1 text-[12px] font-medium opacity-70">
            holdout signals · {pair.label}
          </p>

          <div className="mt-5 rounded-2xl p-3" style={{ background: tint(10) }}>
            <div className="flex items-baseline justify-between text-[12px] font-semibold">
              <span className="opacity-70">Hit rate</span>
              <span className="font-mono tabular-nums">{h.hit_rate == null ? '—' : `${(h.hit_rate * 100).toFixed(0)}%`}</span>
            </div>
            <div className="relative mt-2 h-1.5 overflow-hidden rounded-full" style={{ background: tint(14) }}>
              <div className="h-full rounded-full" style={{ width: `${(h.hit_rate ?? 0) * 100}%`, background: INK, transition: `width 900ms ${EASE}` }} />
              <span aria-hidden className="absolute inset-y-0 left-1/2 w-px" style={{ background: tint(50) }} />
            </div>
          </div>
          <dl className="mt-3 space-y-1.5 text-[12px]">
            {[
              ['Threshold', `${pair.zThreshold}σ`],
              ['Baseline', `${pair.baselineWindow} obs`],
              ['Horizon', `${pair.horizon} obs`],
              ['Costs', pair.unknownCosts > 0 ? `${pair.unknownCosts} of 4 unknown` : `${pair.roundTripBps?.toFixed(1)} bps round trip`],
            ].map(([k, val]) => (
              <div key={k} className="flex justify-between gap-3">
                <dt className="opacity-70">{k}</dt>
                <dd className="font-mono font-semibold tabular-nums">{val}</dd>
              </div>
            ))}
          </dl>

          <div className="mt-auto pt-6">
            <p className="text-[12px] font-semibold opacity-70">Mean reversion, gross</p>
            <p className="mt-1 font-mono text-[20px] font-semibold tabular-nums">
              {h.mean_gross_bps == null ? '—' : signed(h.mean_gross_bps, 2)} <span className="text-[13px]">bps</span>
            </p>
            <p className="font-mono text-[12px] opacity-70 tabular-nums">
              net {h.mean_net_bps == null ? (pair.unknownCosts > 0 ? 'unknown · costs missing' : '—') : `${signed(h.mean_net_bps, 2)} bps`}
            </p>

            <div className="mt-5 flex h-12 items-end gap-1" aria-hidden>
              {pair.windows.map((w, i) => {
                const maxN = Math.max(1, ...pair.windows.map((x) => x.n))
                return (
                  <span
                    key={w.label}
                    className="flex-1 rounded-[4px]"
                    style={{ height: `${Math.max(6, (w.n / maxN) * 100)}%`, background: INK, opacity: 0.15 + (i / pair.windows.length) * 0.5 }}
                  />
                )
              })}
            </div>
            <p className="mt-1.5 font-mono text-[10px] opacity-60">Signals per test window · last is holdout</p>

            <button
              type="button"
              onClick={onOpenEvidence}
              className="mt-4 flex w-full items-center justify-center gap-2 rounded-2xl py-3 text-sm font-semibold transition-transform focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:outline-none active:scale-[0.98]"
              style={{ background: INK, color: ACCENT }}
            >
              Open evidence <ArrowRight className="size-4" aria-hidden />
            </button>
            <p className="mt-2 text-center text-[10px] font-medium opacity-60">A historical research result, not a trade signal.</p>
          </div>
        </>
      )}
    </section>
  )
}

/* ------------------------------------------------------------------ */
/*  Normal band: baseline ± threshold vs today's spread                */
/* ------------------------------------------------------------------ */

function SameDayRangeTile({ early }: { early: SameDayView }) {
  const values = early.gaps.flatMap((g) => (g.adjusted == null ? [] : [g.adjusted]))
  const lo = Math.min(...values)
  const hi = Math.max(...values)
  const pad = Math.max(1, (hi - lo) * 0.15)
  const pos = (v: number) => ((v - (lo - pad)) / (hi - lo + 2 * pad)) * 100
  return (
    <Tile title={`Same-day range · ${shortDay(early.date)}`} className="lg:col-start-3 lg:row-start-3">
      {values.length === 0 ? (
        <p className="text-[13px] text-muted-foreground">No carry-adjusted gap could be computed for this pair on {day(early.date)}.</p>
      ) : (
        <>
          <p className="font-mono text-[22px] font-semibold tabular-nums">
            {signed(lo)} to {signed(hi)} <span className="text-[13px] text-muted-foreground">bps</span>
          </p>
          <p className="font-mono text-[11px] text-muted-foreground">carry-adjusted · {values.length} expiry pairings</p>
          <div className="relative mt-5 h-8" role="img" aria-label={`Carry-adjusted gaps from ${signed(lo)} to ${signed(hi)} bps`}>
            <div className="absolute inset-x-0 top-1/2 h-[2px] -translate-y-1/2 rounded-full bg-muted" />
            {early.gaps.map((g) =>
              g.adjusted == null ? null : (
                <span
                  key={g.legs}
                  title={`${g.legs}: ${signed(g.adjusted)} bps`}
                  className="absolute top-1/2 size-2.5 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-card"
                  style={{ left: `${pos(g.adjusted)}%`, background: g === early.gap ? ACCENT : 'var(--color-muted-foreground)' }}
                />
              ),
            )}
          </div>
        </>
      )}
      <MoreData>{needsDates('A normal band', early.datesLoaded)}</MoreData>
    </Tile>
  )
}

function BandTile({ pair, threshold, empty }: { pair: PairView | null; threshold: number; empty: React.ReactNode }) {
  const p = pair ? lastScored(pair.points) : null
  if (!pair || !p || p.baseline == null || p.std == null) {
    return (
      <Tile title="Normal band" className="lg:col-start-3 lg:row-start-3">
        {empty}
      </Tile>
    )
  }
  const bandLo = p.baseline - threshold * p.std
  const bandHi = p.baseline + threshold * p.std
  const w = bandHi - bandLo || 1
  const lo = Math.min(bandLo - w * 0.45, p.spread - w * 0.1)
  const hi = Math.max(bandHi + w * 0.45, p.spread + w * 0.1)
  const pos = (v: number) => ((v - lo) / (hi - lo)) * 100
  const inside = p.spread >= bandLo && p.spread <= bandHi

  return (
    <Tile
      title={`Normal band · ±${threshold}σ`}
      className="lg:col-start-3 lg:row-start-3"
      action={
        <span
          className="shrink-0 rounded-full px-2 py-0.5 font-mono text-[11px] font-semibold"
          style={
            inside
              ? { background: 'var(--color-muted)', color: 'var(--color-muted-foreground)' }
              : { background: `color-mix(in oklch, ${ACCENT} 18%, transparent)`, color: ACCENT }
          }
        >
          {inside ? 'Within band' : 'Flagged'}
        </span>
      }
    >
      <p className="font-mono text-[22px] font-semibold tabular-nums">
        {signed(p.spread)} <span className="text-[13px] text-muted-foreground">bps</span>
      </p>
      <p className="font-mono text-[11px] text-muted-foreground">spread · {shortDay(p.date)}</p>

      <div className="relative mt-6 h-10" role="img" aria-label={`Band ${signed(bandLo)} to ${signed(bandHi)} bps, spread ${signed(p.spread)} bps`}>
        <div className="absolute inset-x-0 top-1/2 h-[2px] -translate-y-1/2 rounded-full bg-muted" />
        <div
          className="absolute top-1/2 h-10 -translate-y-1/2 rounded-[10px]"
          style={{
            left: `${pos(bandLo)}%`,
            width: `${pos(bandHi) - pos(bandLo)}%`,
            background: `repeating-linear-gradient(135deg, color-mix(in oklch, ${ACCENT} 26%, transparent) 0 6px, color-mix(in oklch, ${ACCENT} 12%, transparent) 6px 12px)`,
            boxShadow: `inset 0 0 0 1px color-mix(in oklch, ${ACCENT} 55%, transparent)`,
          }}
        />
        <div
          className="absolute top-1/2 h-14 w-[3px] -translate-x-1/2 -translate-y-1/2 rounded-full bg-foreground"
          style={{ left: `${Math.max(2, Math.min(98, pos(p.spread)))}%`, transition: `left 900ms ${EASE}` }}
        />
      </div>
      <div className="mt-2 flex justify-between font-mono text-[11px] text-muted-foreground tabular-nums">
        <span style={{ marginLeft: `${Math.max(0, pos(bandLo) - 6)}%` }}>{signed(bandLo)}</span>
        <span style={{ marginRight: `${Math.max(0, 100 - pos(bandHi) - 6)}%` }}>{signed(bandHi)}</span>
      </div>
      <p className="mt-auto pt-4 text-[12px] text-muted-foreground">
        Deviation <span className="font-mono font-semibold text-foreground tabular-nums">{p.deviation == null ? '—' : `${signed(p.deviation)} bps`}</span>
      </p>
    </Tile>
  )
}

/* ------------------------------------------------------------------ */
/*  Daily deviation stream                                             */
/* ------------------------------------------------------------------ */

function PairCounts({ pair }: { pair: PairView }) {
  return (
    <dl className="mt-4 grid grid-cols-3 gap-3 border-t border-border pt-3">
      {[
        ['Eligible dates', count(pair.eligibleDates)],
        ['Excluded dates', count(pair.excludedDates)],
        ['Missing a leg', count(pair.missingLegDates)],
      ].map(([k, val]) => (
        <div key={k} className="min-w-0">
          <dt className="text-[11px] text-muted-foreground">{k}</dt>
          <dd className="mt-0.5 font-mono text-[13px] font-semibold tabular-nums">{val}</dd>
        </div>
      ))}
    </dl>
  )
}

function SameDayResidualTile({ early, pair }: { early: SameDayView; pair: PairView }) {
  const [hover, setHover] = React.useState<number | null>(null)
  const rs = early.residuals
  const maxAbs = Math.max(1, ...rs.map((r) => Math.abs(r.bps)))
  const symbols = [...new Set(rs.map((r) => r.symbol))]
  return (
    <Tile
      title="Distance from carry line"
      className="sm:col-span-2 lg:col-span-2 lg:col-start-1 lg:row-start-4"
      action={<span className="font-mono text-[11px] text-muted-foreground">{shortDay(early.date)}</span>}
    >
      <p className="font-mono text-[11px] text-muted-foreground tabular-nums" aria-live="polite">
        {hover !== null ? `${rs[hover].label} · ${signed(rs[hover].bps)} bps` : `${symbols.map((s, i) => `${s} ${i === 0 ? 'gold' : 'grey'}`).join(' · ')} · above or below its own fitted curve, up to ${maxAbs.toFixed(1)} bps`}
      </p>
      <div className="relative mt-3 flex h-20 items-stretch gap-[3px]" onPointerLeave={() => setHover(null)} role="img" aria-label={rs.map((r) => `${r.label} ${signed(r.bps)} bps`).join(', ')}>
        <span aria-hidden className="absolute inset-x-0 top-1/2 h-px bg-border" />
        {rs.map((r, i) => {
          const h = (Math.abs(r.bps) / maxAbs) * 50
          return (
            <span key={r.contract} className="relative flex-1" onPointerEnter={() => setHover(i)} aria-hidden>
              <span
                className="absolute inset-x-0 rounded-[3px]"
                style={{
                  height: `${Math.max(2, h)}%`,
                  ...(r.bps >= 0 ? { bottom: '50%' } : { top: '50%' }),
                  background: r.symbol === symbols[0] ? ACCENT : 'var(--color-muted-foreground)',
                  opacity: hover === null || hover === i ? 0.9 : 0.3,
                }}
              />
            </span>
          )
        })}
      </div>
      <PairCounts pair={pair} />
      <MoreData>{needsDates('A daily z-score for the pair', early.datesLoaded)}</MoreData>
    </Tile>
  )
}

function StreamTile({ pair, threshold, reduced, empty }: { pair: PairView | null; threshold: number; reduced: boolean; empty: React.ReactNode }) {
  const mounted = useMounted()
  const bars = (pair?.points ?? []).filter((p) => p.z != null).slice(-42)
  const [hover, setHover] = React.useState<number | null>(null)
  const maxAbs = Math.max(threshold, ...bars.map((b) => Math.abs(b.z!)))
  const flagged = bars.filter((b) => Math.abs(b.z!) >= threshold).length

  return (
    <Tile
      title="Daily deviation"
      className="sm:col-span-2 lg:col-span-2 lg:col-start-1 lg:row-start-4"
      action={pair && bars.length > 0 && <span className="font-mono text-[11px] text-muted-foreground">{pair.label}</span>}
    >
      {!pair || bars.length === 0 ? (
        empty
      ) : (
        <>
          <div className="flex items-end justify-between gap-4">
            <div>
              <p className="font-mono text-[22px] font-semibold tabular-nums">
                {flagged}
                <span className="text-muted-foreground">/{bars.length}</span>
              </p>
              <p className="font-mono text-[11px] text-muted-foreground tabular-nums">sessions beyond {threshold}σ</p>
            </div>
            <p className="font-mono text-[11px] text-muted-foreground tabular-nums" aria-live="polite">
              {hover !== null ? `${shortDay(bars[hover].date)} · z ${signed(bars[hover].z!, 2)}` : `last ${bars.length} eligible sessions`}
            </p>
          </div>
          <div className="mt-4 flex flex-1 items-end gap-[3px]" style={{ minHeight: 72 }} onPointerLeave={() => setHover(null)}>
            {bars.map((b, i) => {
              const over = Math.abs(b.z!) >= threshold
              return (
                <span
                  key={b.date}
                  onPointerEnter={() => setHover(i)}
                  className="flex-1 rounded-[3px]"
                  style={{
                    height: mounted || reduced ? `${Math.max(4, (Math.abs(b.z!) / maxAbs) * 100)}%` : '4%',
                    background: over ? ACCENT : 'var(--color-muted-foreground)',
                    opacity: hover === i ? 1 : over ? 0.95 : 0.15 + (i / bars.length) * 0.45,
                    transition: reduced ? 'opacity 200ms ease' : `height 800ms ${EASE} ${i * 12}ms, opacity 200ms ease`,
                  }}
                  aria-hidden
                />
              )
            })}
          </div>
          <PairCounts pair={pair} />
        </>
      )}
    </Tile>
  )
}

/* ------------------------------------------------------------------ */
/*  Recent flags                                                       */
/* ------------------------------------------------------------------ */

function StatusIcon({ status }: { status: PointStatus }) {
  const p = { className: 'size-4', 'aria-hidden': true, strokeWidth: 1.9 }
  if (status === 'cost_adjusted_candidate') return <BadgeCheck {...p} />
  if (status === 'statistical_anomaly') return <Activity {...p} />
  if (status === 'candidate_anomaly') return <CircleDot {...p} />
  return <Sigma {...p} />
}

function SignalsTile({ signals, empty }: { signals: SignalView[]; empty: React.ReactNode }) {
  const mounted = useMounted()
  return (
    <Tile title="Recent flags" className="sm:col-span-2 lg:col-span-2 lg:col-start-3 lg:row-start-4">
      {signals.length === 0 ? (
        empty
      ) : (
        <ul className="-mx-2 -my-1">
          {signals.map((s, i) => (
            <li
              key={s.id}
              className="flex items-center gap-3 rounded-2xl px-2 py-2 transition-colors hover:bg-muted/50"
              style={{
                opacity: mounted ? 1 : 0,
                transform: mounted ? 'none' : 'translateY(6px)',
                transition: `opacity 500ms ease ${300 + i * 70}ms, transform 500ms ${EASE} ${300 + i * 70}ms, background-color 150ms ease`,
              }}
            >
              <span className="grid size-9 shrink-0 place-items-center rounded-xl bg-muted text-foreground">
                <StatusIcon status={s.status} />
              </span>
              <div className="min-w-0 flex-1">
                <p className="truncate text-[13px] font-medium">{s.pair}</p>
                <p className="truncate text-[11px] text-muted-foreground">
                  {s.legs} · {shortDay(s.date)}
                </p>
              </div>
              <div className="shrink-0 text-right">
                <p className="font-mono text-[13px] font-medium tabular-nums">
                  {signed(s.deviation)} bps
                </p>
                <p
                  className="mt-0.5 font-mono text-[10px] font-semibold"
                  style={{ color: s.status === 'cost_adjusted_candidate' ? ACCENT : 'var(--color-muted-foreground)' }}
                >
                  z {signed(s.z, 2)}
                  <span className="hidden sm:inline"> · {STATUSES[s.status].label.toLowerCase()}</span>
                </p>
              </div>
            </li>
          ))}
        </ul>
      )}
    </Tile>
  )
}

/* ------------------------------------------------------------------ */
/*  Dashboard                                                          */
/* ------------------------------------------------------------------ */

const KIND_LABEL: Record<DataKind, string> = { empty: 'No data', synthetic: 'Synthetic demo', user_uploaded: 'Uploaded data' }

export function GoldBento({
  kind,
  loading,
  price,
  instruments,
  composition,
  research,
  pairs,
  signals,
  sameDay,
  neededDates,
  bundled = false,
  busy = false,
  onLoadDemo,
  onImport,
  onRunResearch,
  onOpenEvidence,
  className,
}: GoldBentoProps) {
  const reduced = useReducedMotion()
  const [pairId, setPairId] = React.useState<string | null>(null)
  const pair = pairs.find((p) => p.id === pairId) ?? pairs[0] ?? null
  // Until the pair has a baseline, the tiles show what the loaded days support on their own.
  const scored = !!pair && pair.eligibleDates >= BASELINE_DATES && lastScored(pair.points) != null
  const early = pair && !scored ? sameDay(pair.id) : null
  // The threshold the user picked, kept only while the same pair is selected.
  const [override, setOverride] = React.useState<{ pair: string; z: number } | null>(null)
  const threshold = pair && override?.pair === pair.id ? override.z : (pair?.zThreshold ?? 2)
  const hasData = !!price || composition.length > 0

  const noData = (
    <Missing
      action={
        <div className="flex flex-wrap gap-2">
          {onLoadDemo && (
            <Action primary onClick={onLoadDemo} disabled={busy}>
              {busy ? <Loader2 className="size-3.5 animate-spin motion-reduce:animate-none" aria-hidden /> : <Database className="size-3.5" aria-hidden />}
              Load synthetic demo
            </Action>
          )}
          <Action onClick={onImport}>Import data</Action>
        </div>
      }
    >
      No market data is loaded. Load the synthetic demo to try every tile, or import MCX bhavcopy files.
    </Missing>
  )
  const quiet = (text: string) => <Missing>{text}</Missing>
  const researchEmpty = loading || research === 'loading' ? (
    <Skeleton className="min-h-24 w-full flex-1" />
  ) : !hasData ? (
    quiet('Appears once data is loaded and research has run.')
  ) : research === 'none' ? (
    <Missing
      action={
        <Action primary onClick={onRunResearch}>
          <FlaskConical className="size-3.5" aria-hidden /> Run research
        </Action>
      }
    >
      Research has not been run on the loaded data.
    </Missing>
  ) : pairs.length === 0 ? (
    quiet('No two contracts were close enough in expiry to compare.')
  ) : (
    quiet('Not enough eligible history in this pair for a baseline.')
  )

  return (
    <div className={cx('w-full', className)}>
      <nav className="mb-3 flex flex-wrap items-center justify-between gap-3 px-1" aria-label="Dashboard">
        {pairs.length > 0 ? (
          <label className="flex items-center gap-2 rounded-full border border-border py-1 pr-1 pl-3 text-[12px] font-medium">
            <span className="text-muted-foreground">Pair</span>
            <select
              value={pair?.id}
              onChange={(e) => setPairId(e.target.value)}
              className="cursor-pointer rounded-full bg-muted px-2.5 py-1 font-mono text-[12px] font-semibold text-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
            >
              {pairs.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.label}
                </option>
              ))}
            </select>
          </label>
        ) : (
          <span />
        )}
        <div className="flex items-center gap-2">
          <span className="flex items-center gap-2 rounded-full border border-border px-3 py-1.5 text-[12px] font-medium">
            <span className="size-2 rounded-full" style={{ background: ACCENT }} aria-hidden />
            MCX
          </span>
          <span className="rounded-full bg-foreground px-3 py-1.5 font-mono text-[12px] font-semibold text-background">
            {kind ? (kind === 'user_uploaded' && bundled ? 'Real MCX data' : KIND_LABEL[kind]) : loading ? 'Loading…' : 'Offline'}
          </span>
        </div>
      </nav>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <HeroTile price={price} loading={loading} reduced={reduced} empty={noData} />
        <CardsTile key={instruments.map((c) => c.symbol).join() + (price?.symbol ?? '')} cards={instruments} front={price?.symbol} reduced={reduced} />
        {early ? (
          <SameDayDeviationTile early={early} />
        ) : (
          <GaugeTile pair={pair} threshold={threshold} onThreshold={(z) => pair && setOverride({ pair: pair.id, z })} empty={researchEmpty} />
        )}
        {early ? <SameDayChartTile early={early} /> : <ChartTile pair={pair} threshold={threshold} reduced={reduced} empty={researchEmpty} />}
        <CompositionTile composition={composition} empty={loading ? <Skeleton className="min-h-24 w-full flex-1" /> : quiet('No observations imported yet.')} />
        <VerdictTile pair={pair} research={loading ? 'loading' : research} hasData={hasData} neededDates={neededDates} onOpenEvidence={onOpenEvidence} onRunResearch={onRunResearch} />
        {early ? <SameDayRangeTile early={early} /> : <BandTile pair={pair} threshold={threshold} empty={researchEmpty} />}
        {early && pair ? (
          <SameDayResidualTile early={early} pair={pair} />
        ) : (
          <StreamTile pair={pair} threshold={threshold} reduced={reduced} empty={researchEmpty} />
        )}
        <SignalsTile
          signals={signals}
          empty={
            research === 'ready' && pairs.length > 0
              ? quiet(
                  early
                    ? `No dates flagged. ${needsDates("A flag needs the pair's normal gap, which", early.datesLoaded)}`
                    : 'No dates were flagged in this run.',
                )
              : researchEmpty
          }
        />
      </div>
    </div>
  )
}

export default GoldBento
