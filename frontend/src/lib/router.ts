import { useEffect, useState } from 'react'

// Path-based routes. In production FastAPI serves index.html for these paths
// (SPA fallback); in development Vite does.
export const ROUTES = [
  { path: '/', label: 'Overview' },
  { path: '/contracts', label: 'Contracts' },
  { path: '/data', label: 'Data' },
  { path: '/research', label: 'Research' },
  { path: '/alerts', label: 'Alerts' },
  { path: '/methodology', label: 'Methodology' },
] as const

export type RoutePath = (typeof ROUTES)[number]['path']

function current(): RoutePath {
  const path = window.location.pathname.replace(/\/+$/, '') || '/'
  return (ROUTES.find((r) => r.path === path)?.path ?? '/') as RoutePath
}

const listeners = new Set<() => void>()

export function navigate(path: RoutePath) {
  if (path !== window.location.pathname) {
    window.history.pushState(null, '', path)
  }
  listeners.forEach((l) => l())
  window.scrollTo({ top: 0 })
}

export function useRoute(): RoutePath {
  const [route, setRoute] = useState<RoutePath>(current)
  useEffect(() => {
    const update = () => setRoute(current())
    listeners.add(update)
    window.addEventListener('popstate', update)
    return () => {
      listeners.delete(update)
      window.removeEventListener('popstate', update)
    }
  }, [])
  return route
}
