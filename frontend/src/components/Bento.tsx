import { motion } from 'motion/react'
import type { Variants } from 'motion/react'
import type { ReactNode } from 'react'

// Bento layout: a 12-column grid at lg, 6 at md, one column on phones.
// Tiles use the 26px radius and 12px gutter of the Overview bento (components/ui/gold-bento.tsx).

const SPAN_LG = {
  3: 'lg:col-span-3',
  4: 'lg:col-span-4',
  5: 'lg:col-span-5',
  6: 'lg:col-span-6',
  7: 'lg:col-span-7',
  8: 'lg:col-span-8',
  12: 'lg:col-span-12',
} as const

const SPAN_MD = { full: 'md:col-span-6', half: 'md:col-span-3' } as const

export type Span = keyof typeof SPAN_LG

// The lead tile (the block answering the screen's question): a stronger edge and a faint
// gold wash over its top 160px that fades into the surface. Remove the background to go flat.
const LEAD = 'border-rule-strong bg-[linear-gradient(180deg,color-mix(in_oklch,var(--color-gold)_7%,transparent)_0,transparent_160px)]' // taste-skill-ignore

const EASE = [0.23, 1, 0.32, 1] as const

const grid: Variants = {
  hidden: {},
  show: { transition: { staggerChildren: 0.045 } },
}

// Opacity and a short rise, once, when the screen mounts. MotionConfig
// reducedMotion="user" (App.tsx) drops the rise for reduced-motion users.
const tile: Variants = {
  hidden: { opacity: 0, transform: 'translateY(10px)' },
  show: { opacity: 1, transform: 'translateY(0px)', transition: { duration: 0.28, ease: EASE } },
}

export function BentoGrid({ children, still = false, className = '' }: { children: ReactNode; still?: boolean; className?: string }) {
  const cls = `grid grid-cols-1 gap-3 md:grid-cols-6 lg:grid-cols-12 ${className}`
  if (still) return <div className={cls}>{children}</div>
  return (
    <motion.div className={cls} variants={grid} initial="hidden" animate="show">
      {children}
    </motion.div>
  )
}

export function BentoTile({
  title,
  meta,
  actions,
  children,
  span = 12,
  md = 'full',
  lead = false,
  footer,
  labelledBy,
  className = '',
}: {
  title?: ReactNode
  /** One grey line under the title: the scope, period or source of what the tile shows. */
  meta?: ReactNode
  actions?: ReactNode
  children: ReactNode
  span?: Span
  md?: keyof typeof SPAN_MD
  /** The block that answers the screen's question. */
  lead?: boolean
  footer?: ReactNode
  labelledBy?: string
  className?: string
}) {
  return (
    <motion.section
      variants={tile}
      aria-labelledby={labelledBy}
      className={`flex min-w-0 flex-col rounded-[26px] border border-rule bg-surface ${lead ? LEAD : ''} ${SPAN_MD[md]} ${SPAN_LG[span]} ${className}`}
    >
      {(title || actions) && (
        <header className="flex flex-wrap items-start justify-between gap-x-4 gap-y-2 px-5 pt-5">
          <div className="min-w-0">
            {title && (
              <h2 id={labelledBy} className="text-[15px] font-semibold tracking-tight text-ink">
                {title}
              </h2>
            )}
            {meta && <p className="mt-0.5 text-[13px] leading-snug text-ink-3">{meta}</p>}
          </div>
          {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
        </header>
      )}
      <div className={`flex-1 px-5 pb-5 ${title || actions ? 'pt-4' : 'pt-5'}`}>{children}</div>
      {footer && <footer className="border-t border-rule rounded-b-[26px] px-5 py-3 text-[13px] text-ink-2">{footer}</footer>}
    </motion.section>
  )
}

/** The screen's one h1, its one-sentence finding, and any real actions. */
export function PageHeader({ title, finding, aside }: { title: string; finding?: ReactNode; aside?: ReactNode }) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-x-6 gap-y-2 pb-1">
      <div className="min-w-0">
        <h1 className="text-[26px] leading-tight font-semibold tracking-[-0.02em] text-ink">{title}</h1>
        {finding && <p className="mt-1 max-w-3xl text-[15px] leading-relaxed text-ink-2">{finding}</p>}
      </div>
      {aside && <div className="text-xs text-ink-3">{aside}</div>}
    </div>
  )
}

/** A figure with its label above and an optional grey unit and note. Type, not a tile. */
export function Figure({
  label,
  value,
  unit,
  note,
  size = 'md',
}: {
  label: ReactNode
  value: ReactNode
  unit?: ReactNode
  note?: ReactNode
  size?: 'md' | 'lg'
}) {
  return (
    <div className="min-w-0">
      <dt className="text-[13px] text-ink-3">{label}</dt>
      <dd className={`num mt-1 font-medium tracking-tight text-ink ${size === 'lg' ? 'text-[32px] leading-none' : 'text-xl leading-tight'}`}>
        {value}
        {unit && <span className="ml-1 text-[13px] font-normal tracking-normal text-ink-3">{unit}</span>}
      </dd>
      {note && <dd className="mt-1 text-[13px] text-ink-3">{note}</dd>}
    </div>
  )
}
