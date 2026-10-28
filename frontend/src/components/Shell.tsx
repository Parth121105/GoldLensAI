import type { ReactNode } from 'react'
import { ROUTES, navigate, useRoute } from '../lib/router'
import type { RoutePath } from '../lib/router'
import { useSession } from '../state/context'
import { KindBadge, Notice } from './ui'

function Mark({ className = 'size-6' }: { className?: string }) {
  // A lens over a bar: the product's monogram.
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" className={`shrink-0 ${className}`}>
      <rect x="1" y="1" width="22" height="22" rx="7" fill="var(--color-gold)" />
      <circle cx="11" cy="11" r="5.25" fill="none" stroke="var(--color-ground)" strokeWidth="1.8" />
      <path d="M15 15l4.2 4.2" stroke="var(--color-ground)" strokeWidth="1.8" strokeLinecap="round" />
      <rect x="8.4" y="9.6" width="5.2" height="2.8" rx="0.6" fill="var(--color-ground)" />
    </svg>
  )
}

export function Shell({ children }: { children: ReactNode }) {
  const route = useRoute()
  const { datasets, instruments } = useSession()
  const kind = datasets.data?.kind

  return (
    <div className="flex min-h-dvh flex-col">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:top-3 focus:left-3 focus:z-50 focus:rounded focus:bg-surface focus:px-3 focus:py-2">
        Skip to content
      </a>
      <header className="sticky top-0 z-20 bg-ground/80 backdrop-blur-md">
        <div className="mx-auto flex max-w-[1180px] flex-wrap items-center gap-x-6 gap-y-3 px-4 py-3 sm:px-6 lg:flex-nowrap">
          <a
            href="/"
            onClick={(e) => {
              e.preventDefault()
              navigate('/')
            }}
            className="flex items-center gap-2.5 rounded-full"
          >
            <Mark />
            <span className="leading-tight">
              <span className="block text-[15px] font-semibold tracking-tight">GoldLensAI</span>
              <span className="hidden text-xs text-ink-3 sm:block">MCX gold futures · relative-value research</span>
            </span>
          </a>
          <nav aria-label="Sections" className="order-last w-full overflow-x-auto lg:order-none lg:mx-auto lg:w-auto">
            <div className="inline-flex rounded-full border border-rule p-0.5">
              {ROUTES.map((r) => (
                <NavLink key={r.path} path={r.path} label={r.label} active={route === r.path} />
              ))}
            </div>
          </nav>
          <div className="ml-auto flex items-center gap-2 lg:ml-0">
            {datasets.loading && !datasets.data ? (
              <span className="text-xs text-ink-3">Checking data…</span>
            ) : datasets.error ? (
              <span className="flex items-center gap-1.5 text-xs text-bad">
                <span aria-hidden="true" className="size-1.5 rounded-full bg-bad" />
                Server unreachable
              </span>
            ) : (
              <KindBadge kind={kind} bundled={datasets.data?.bundled} label={datasets.data?.source_label} compact />
            )}
          </div>
        </div>
      </header>

      {kind === 'synthetic' && (
        <div className="mx-auto w-full max-w-[1180px] px-4 pt-4 sm:px-6">
          <Notice>
            <strong className="font-semibold">Synthetic data.</strong> The loaded file is generated or labelled test data.
            Every price, spread and research result on screen describes invented numbers, not MCX markets.
          </Notice>
        </div>
      )}

      <main id="main" className="mx-auto w-full max-w-[1180px] flex-1 px-4 pt-4 pb-14 sm:px-6">
        {children}
      </main>

      <footer className="border-t border-rule/70">
        <div className="mx-auto flex max-w-[1180px] flex-wrap items-end justify-between gap-x-10 gap-y-4 px-4 py-8 sm:px-6">
          <div className="flex items-center gap-3">
            <Mark className="size-8" />
            <div>
              <p className="text-lg font-semibold tracking-tight">GoldLensAI</p>
              <p className="max-w-xl text-xs leading-relaxed text-ink-3">
                Research and decision support only. GoldLensAI does not trade, does not give investment advice, and never
                labels a result as executable or profitable.
              </p>
            </div>
          </div>
          <p className="text-xs text-ink-3">
            {instruments.data && <>Method {instruments.data.method_version} · </>}
            <a href="/api/docs" className="underline underline-offset-2 hover:text-ink">API documentation</a>
          </p>
        </div>
      </footer>
    </div>
  )
}

function NavLink({ path, label, active }: { path: RoutePath; label: string; active: boolean }) {
  return (
    <a
      href={path}
      aria-current={active ? 'page' : undefined}
      onClick={(e) => {
        if (e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return
        e.preventDefault()
        navigate(path)
      }}
      className={`flex h-8 items-center rounded-full px-3.5 text-[13px] whitespace-nowrap transition-colors duration-150 ${
        active ? 'bg-ink font-medium text-ground' : 'text-ink-3 hover:text-ink'
      }`}
    >
      {label}
    </a>
  )
}
