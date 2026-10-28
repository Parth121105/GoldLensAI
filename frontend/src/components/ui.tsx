import { AnimatePresence, motion } from 'motion/react'
import { useId, useState } from 'react'
import type { ReactNode } from 'react'

export function Panel({
  title,
  subtitle,
  actions,
  children,
  className = '',
}: {
  title: ReactNode
  subtitle?: ReactNode
  actions?: ReactNode
  children: ReactNode
  className?: string
}) {
  return (
    <section className={`rounded-[26px] border border-rule bg-surface ${className}`}>
      <header className="flex flex-wrap items-start justify-between gap-x-4 gap-y-2 px-5 pt-4">
        <div className="min-w-0">
          <h2 className="text-[15px] font-semibold tracking-tight text-ink">{title}</h2>
          {subtitle && <p className="mt-0.5 text-[13px] leading-snug text-ink-3">{subtitle}</p>}
        </div>
        {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
      </header>
      <div className="px-5 pt-4 pb-5">{children}</div>
    </section>
  )
}

export type Tone = 'neutral' | 'good' | 'warn' | 'bad' | 'info' | 'gold'

const TONES: Record<Tone, string> = {
  neutral: 'bg-sunken text-ink-2',
  good: 'bg-good-soft text-good',
  warn: 'bg-warn-soft text-warn',
  bad: 'bg-bad-soft text-bad',
  info: 'bg-info-soft text-info',
  gold: 'bg-gold-soft text-gold',
}

export function Pill({ tone = 'neutral', children }: { tone?: Tone; children: ReactNode }) {
  return (
    <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium whitespace-nowrap ${TONES[tone]}`}>
      {children}
    </span>
  )
}

/** One sentence inside the frame where data would be, never a blank box. */
export function Empty({ children, action }: { children: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-dashed border-rule-strong px-4 py-3 text-sm text-ink-2">
      <span>{children}</span>
      {action}
    </div>
  )
}

export function ErrorNote({ children, onRetry }: { children: ReactNode; onRetry?: () => void }) {
  return (
    <div role="alert" className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-bad/30 bg-bad-soft px-3 py-2 text-sm text-bad">
      <span>{children}</span>
      {onRetry && (
        <button type="button" onClick={onRetry} className="text-sm font-medium underline underline-offset-2">
          Retry
        </button>
      )}
    </div>
  )
}

export function Notice({ tone = 'warn', children }: { tone?: 'warn' | 'info'; children: ReactNode }) {
  const style =
    tone === 'warn'
      ? 'border-warn/30 bg-warn-soft text-warn'
      : 'border-info/25 bg-info-soft text-info'
  return <div className={`rounded-2xl border px-3 py-2 text-[13px] leading-relaxed ${style}`}>{children}</div>
}

/** A loading placeholder at the size of the value it stands in for. */
export function Placeholder({ className = 'h-4 w-24' }: { className?: string }) {
  return <span aria-hidden="true" className={`inline-block rounded bg-sunken align-middle ${className}`} />
}

export function Button({
  children,
  onClick,
  variant = 'secondary',
  disabled,
  type = 'button',
}: {
  children: ReactNode
  onClick?: () => void
  variant?: 'primary' | 'secondary' | 'quiet'
  disabled?: boolean
  type?: 'button' | 'submit'
}) {
  const styles = {
    primary: 'bg-ink text-ground hover:bg-ink/85 border border-ink',
    secondary: 'bg-transparent text-ink border border-rule-strong hover:border-ink-3 hover:bg-sunken',
    quiet: 'text-ink-2 hover:text-ink hover:bg-sunken border border-transparent',
  }[variant]
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      className={`inline-flex h-8 shrink-0 items-center gap-1.5 rounded-full px-3.5 whitespace-nowrap text-[13px] font-medium transition-[background-color,border-color,color,transform] duration-150 active:scale-[0.97] disabled:cursor-not-allowed disabled:opacity-50 ${styles}`}
    >
      {children}
    </button>
  )
}

/** Label over value; numbers in tabular figures. */
export function Stat({ label, value, hint }: { label: string; value: ReactNode; hint?: ReactNode }) {
  return (
    <div className="min-w-0">
      <dt className="text-[13px] text-ink-3">{label}</dt>
      <dd className="num mt-1 truncate text-lg font-medium text-ink">{value}</dd>
      {hint && <dd className="mt-0.5 text-[13px] text-ink-3">{hint}</dd>}
    </div>
  )
}

export function Disclosure({ summary, children }: { summary: ReactNode; children: ReactNode }) {
  const [open, setOpen] = useState(false)
  const id = useId()
  return (
    <div>
      <button
        type="button"
        aria-expanded={open}
        aria-controls={id}
        onClick={() => setOpen((o) => !o)}
        className="inline-flex items-center gap-1.5 text-[13px] font-medium text-ink-2 hover:text-ink"
      >
        <motion.svg
          aria-hidden="true"
          viewBox="0 0 12 12"
          className="size-3"
          animate={{ rotate: open ? 90 : 0 }}
          transition={{ duration: 0.15, ease: 'easeOut' }}
        >
          <path d="M4 2.5 7.5 6 4 9.5" fill="none" stroke="currentColor" strokeWidth="1.5" />
        </motion.svg>
        {summary}
      </button>
      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            id={id}
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2, ease: [0.2, 0, 0, 1] }}
            className="overflow-hidden"
          >
            <div className="pt-2">{children}</div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

export function KindBadge({
  kind,
  bundled,
  label,
  compact,
}: {
  kind: 'empty' | 'user_uploaded' | 'synthetic' | undefined
  bundled?: boolean
  label?: string
  /** Header use: a narrow box that wraps the label over two or three lines. */
  compact?: boolean
}) {
  if (kind === 'synthetic') return <Pill tone="warn">Synthetic data — not market data</Pill>
  if (kind === 'user_uploaded' && bundled && label) {
    // Long enough to wrap, so it is not a nowrap pill.
    return (
      <span className={`inline-block rounded-xl bg-good-soft px-2 py-0.5 text-right text-xs leading-snug font-medium text-good ${compact ? 'max-w-52' : ''}`}>
        {label}
      </span>
    )
  }
  if (kind === 'user_uploaded') return <Pill tone="info">User-uploaded · origin unverified</Pill>
  return <Pill>No market data loaded</Pill>
}

export function Table({ children, caption }: { children: ReactNode; caption?: string }) {
  return (
    <div className="relative -mx-5 overflow-x-auto px-5">
      <table className="w-full border-collapse text-[13px]">
        {caption && <caption className="sr-only">{caption}</caption>}
        {children}
      </table>
    </div>
  )
}
