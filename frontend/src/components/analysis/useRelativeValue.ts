import { useEffect, useState } from 'react'
import { api } from '../../api/client'
import type { RelativeValueResponse } from '../../api/types'
import { useSession } from '../../state/context'

/** Fetches /api/relative-value again whenever the imported data changes. */
export function useRelativeValue() {
  const { datasets } = useSession()
  const key = `${datasets.data?.kind}:${datasets.data?.observations}:${datasets.data?.files.length}`
  const [state, setState] = useState<{ key: string; data: RelativeValueResponse | null; error: string | null }>({
    key: '',
    data: null,
    error: null,
  })
  useEffect(() => {
    let live = true
    api
      .relativeValue()
      .then((data) => live && setState({ key, data, error: null }))
      .catch((e: Error) => live && setState({ key, data: null, error: e.message }))
    return () => {
      live = false
    }
  }, [key])
  return { data: state.key === key ? state.data : null, error: state.key === key ? state.error : null }
}
