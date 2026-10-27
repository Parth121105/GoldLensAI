import { useCallback, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { api } from '../api/client'
import type { DatasetStatus, InstrumentsResponse, Readiness, ResearchResponse } from '../api/types'
import { SessionContext } from './context'
import type { Loadable } from './context'

const initial = { data: null, error: null, loading: true }

function message(error: unknown) {
  return error instanceof Error ? error.message : 'Unexpected error.'
}

export function SessionProvider({ children }: { children: ReactNode }) {
  const [instruments, setInstruments] = useState<Loadable<InstrumentsResponse>>(initial)
  const [datasets, setDatasets] = useState<Loadable<DatasetStatus>>(initial)
  const [research, setResearchState] = useState<Loadable<ResearchResponse>>(initial)
  const [readiness, setReadiness] = useState<Loadable<Readiness>>(initial)

  const refreshReadiness = useCallback(async () => {
    try {
      setReadiness({ data: await api.readiness(), error: null, loading: false })
    } catch (e) {
      setReadiness((s) => ({ ...s, error: message(e), loading: false }))
    }
  }, [])

  const refreshDatasets = useCallback(async () => {
    setDatasets((s) => ({ ...s, loading: true }))
    try {
      setDatasets({ data: await api.datasets(), error: null, loading: false })
    } catch (e) {
      setDatasets((s) => ({ ...s, error: message(e), loading: false }))
    }
    await refreshReadiness()
  }, [refreshReadiness])

  const refreshResearch = useCallback(async () => {
    setResearchState((s) => ({ ...s, loading: true }))
    try {
      setResearchState({ data: await api.latestResearch(), error: null, loading: false })
    } catch (e) {
      setResearchState((s) => ({ ...s, error: message(e), loading: false }))
    }
  }, [])

  const setResearch = useCallback((r: ResearchResponse | null) => {
    setResearchState({ data: r, error: null, loading: false })
  }, [])

  // Initial load: state starts as loading, so only the async results set state here.
  useEffect(() => {
    api
      .instruments()
      .then((data) => setInstruments({ data, error: null, loading: false }))
      .catch((e: unknown) => setInstruments({ data: null, error: message(e), loading: false }))
    api
      .datasets()
      .then((data) => setDatasets({ data, error: null, loading: false }))
      .catch((e: unknown) => setDatasets({ data: null, error: message(e), loading: false }))
    api
      .readiness()
      .then((data) => setReadiness({ data, error: null, loading: false }))
      .catch((e: unknown) => setReadiness({ data: null, error: message(e), loading: false }))
    api
      .latestResearch()
      .then((data) => setResearchState({ data, error: null, loading: false }))
      .catch((e: unknown) => setResearchState({ data: null, error: message(e), loading: false }))
  }, [])

  const value = useMemo(
    () => ({ instruments, datasets, research, readiness, refreshDatasets, refreshResearch, setResearch }),
    [instruments, datasets, research, readiness, refreshDatasets, refreshResearch, setResearch],
  )
  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>
}
