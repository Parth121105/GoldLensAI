// Ink kit: the visual language of the "ink orbit" features section, rebuilt for GoldLensAI's
// Data, Contracts, Research and Methodology pages. Bracketed frames, a hatched page, line
// diagrams that light up in gold on hover. Nothing moves on its own: motion happens only
// while the pointer or keyboard is on an item, and not at all with reduced motion (ink.css).

import { ChevronRight } from 'lucide-react'
import type { ReactNode } from 'react'
import './ink.css'

function cx(...parts: Array<string | false | null | undefined>) {
  return parts.filter(Boolean).join(' ')
}

/** The hatched page every ink screen sits on. */
export function InkPage({ children }: { children: ReactNode }) {
  return <div className="ink-page space-y-8">{children}</div>
}

/** Tag, two-tone h1 (`*word*` is muted) and the screen's one-sentence finding. */
export function InkHead({ tag, title, finding, aside }: { tag: string; title: string; finding?: ReactNode; aside?: ReactNode }) {
  return (
    <header className="flex flex-col items-start gap-3">
      <span className="ink-tag">{tag}</span>
      <div className="flex w-full flex-wrap items-end justify-between gap-x-6 gap-y-2">
        <h1 className="ink-title">
          {title.split('*').map((run, i) => (i % 2 === 1 ? <span key={i} className="ink-muted">{run}</span> : run))}
        </h1>
        {aside && <div className="text-xs text-ink-3">{aside}</div>}
      </div>
      {finding && <p className="max-w-3xl text-[15px] leading-relaxed text-ink-2">{finding}</p>}
    </header>
  )
}

/** Grid for frames; the gap leaves room for the corner brackets. */
export function InkGrid({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cx('grid grid-cols-1 gap-7 lg:grid-cols-12', className)}>{children}</div>
}

export function Frame({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div className={cx('ink-frame', className)}>
      <span className="ink-c ink-c-tl" aria-hidden="true" />
      <span className="ink-c ink-c-tr" aria-hidden="true" />
      <span className="ink-c ink-c-bl" aria-hidden="true" />
      <span className="ink-c ink-c-br" aria-hidden="true" />
      {children}
    </div>
  )
}

/** Collapsed longer text, so a card keeps one title and one sentence without losing anything. */
export function Details({ summary = 'Details', children }: { summary?: ReactNode; children: ReactNode }) {
  return (
    <details className="ink-details">
      <summary>
        <ChevronRight className="ink-chev size-3.5" aria-hidden="true" />
        {summary}
      </summary>
      <div className="pt-3 text-[13px] leading-relaxed text-ink-2">{children}</div>
    </details>
  )
}

/** A bracketed card: one title, one sentence, then the diagram or data, then optional Details. */
export function DiagramCard({
  title,
  description,
  actions,
  details,
  detailsSummary,
  children,
  className,
  labelledBy,
}: {
  title: ReactNode
  description?: ReactNode
  actions?: ReactNode
  details?: ReactNode
  detailsSummary?: ReactNode
  children?: ReactNode
  className?: string
  labelledBy?: string
}) {
  return (
    <Frame className={className}>
      <section className="ink-card" aria-labelledby={labelledBy}>
        <header className="flex flex-wrap items-start justify-between gap-x-4 gap-y-2">
          <div className="min-w-0">
            <h2 id={labelledBy} className="ink-card-title">{title}</h2>
            {description && <p className="ink-card-desc">{description}</p>}
          </div>
          {actions && <div className="flex max-w-full min-w-0 flex-wrap items-center gap-2">{actions}</div>}
        </header>
        {children}
        {details && <Details summary={detailsSummary}>{details}</Details>}
      </section>
    </Frame>
  )
}

/** One connector in a diagram; gold while `on`, red for a rejection path. */
export function FlowLine({ d, on, dashed, tone }: { d: string; on?: boolean; dashed?: boolean; tone?: 'loss' }) {
  return <path d={d} className={cx('ink-flow', dashed && 'ink-flow-dash')} data-on={on ? 'true' : undefined} data-tone={tone} />
}
