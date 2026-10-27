import { createContext, useContext } from 'react'
import type { DatasetStatus, InstrumentsResponse, Readiness, ResearchResponse } from '../api/types'

export interface Loadable<T> {
  data: T | null
  error: string | null
  loading: boolean
}

export interface Session {
  instruments: Loadable<InstrumentsResponse>
  datasets: Loadable<DatasetStatus>
  research: Loadable<ResearchResponse>
  /** Whether the loaded data can support walk-forward research; reloaded with the datasets. */
  readiness: Loadable<Readiness>
  refreshDatasets: () => Promise<void>
  refreshResearch: () => Promise<void>
  setResearch: (r: ResearchResponse | null) => void
}

export const SessionContext = createContext<Session | null>(null)

export function useSession(): Session {
  const session = useContext(SessionContext)
  if (!session) throw new Error('useSession must be used inside SessionProvider')
  return session
}
