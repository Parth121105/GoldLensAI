import { useEffect, useState } from 'react'
import { api } from '../../api/client'
import type { LifecycleResponse, RelativeValueResponse, TermStructureResponse } from '../../api/types'
import { useSession } from '../../state/context'

/** Fetches an analysis endpoint again whenever the imported data changes. */
function useAnalysis<T>(fetcher: () => Promise<T>) {
  const { datasets } = useSession()
  const key = `${datasets.data?.kind}:${datasets.data?.observations}:${datasets.data?.files.length}`
  const [state, setState] = useState<{ key: string; data: T | null; error: string | null }>({
    key: '',
    data: null,
    error: null,
  })
  useEffect(() => {
    let live = true
    fetcher()
      .then((data) => live && setState({ key, data, error: null }))
      .catch((e: Error) => live && setState({ key, data: null, error: e.message }))
    return () => {
      live = false
    }
  }, [key, fetcher])
  return { data: state.key === key ? state.data : null, error: state.key === key ? state.error : null }
}

export const useRelativeValue = () => useAnalysis<RelativeValueResponse>(api.relativeValue)
export const useTermStructure = () => useAnalysis<TermStructureResponse>(api.termStructure)
export const useLifecycle = () => useAnalysis<LifecycleResponse>(api.lifecycle)
