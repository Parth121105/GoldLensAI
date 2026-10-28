import type {
  DatasetStatus,
  InstrumentsResponse,
  ObservationsResponse,
  RelativeValueResponse,
  Readiness,
  ResearchRequest,
  ResearchResponse,
  UploadResponse,
} from './types'

export class ApiError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(path, init)
  } catch {
    throw new ApiError(0, 'The GoldLensAI server could not be reached.')
  }
  if (!response.ok) {
    throw new ApiError(response.status, await errorMessage(response))
  }
  return (await response.json()) as T
}

async function errorMessage(response: Response): Promise<string> {
  try {
    const body: unknown = await response.json()
    if (body && typeof body === 'object' && 'detail' in body) {
      const detail = (body as { detail: unknown }).detail
      if (typeof detail === 'string') return detail
      if (Array.isArray(detail)) {
        return detail
          .map((d) => (d && typeof d === 'object' && 'msg' in d ? String(d.msg) : String(d)))
          .join('; ')
      }
    }
  } catch {
    // fall through to the generic message
  }
  if (response.status >= 502 && response.status <= 504) {
    return `The GoldLensAI server is unavailable (HTTP ${response.status}). Check that the backend is running.`
  }
  return `Request failed (HTTP ${response.status}).`
}

export const api = {
  instruments: () => request<InstrumentsResponse>('/api/instruments'),
  datasets: () => request<DatasetStatus>('/api/datasets'),
  clearDatasets: () => request<DatasetStatus>('/api/datasets', { method: 'DELETE' }),
  loadDemo: () => request<UploadResponse>('/api/datasets/demo', { method: 'POST' }),
  upload: (file: File, dateOrder: '' | 'DMY' | 'MDY') => {
    const params = new URLSearchParams({ filename: file.name })
    if (dateOrder) params.set('date_order', dateOrder)
    return request<UploadResponse>(`/api/datasets?${params}`, {
      method: 'POST',
      headers: { 'Content-Type': 'text/csv' },
      body: file,
    })
  },
  observations: (symbols: string[], expiries: string[]) => {
    const params = new URLSearchParams()
    symbols.forEach((s) => params.append('symbol', s))
    expiries.forEach((e) => params.append('expiry', e))
    return request<ObservationsResponse>(`/api/observations?${params}`)
  },
  /** Latest research for the current data, or null if none has been run (200 with a null body). */
  latestResearch: () => request<ResearchResponse | null>('/api/research'),
  readiness: () => request<Readiness>('/api/readiness'),
  relativeValue: () => request<RelativeValueResponse>('/api/relative-value'),
  runResearch: (body: ResearchRequest) =>
    request<ResearchResponse>('/api/research', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
}
