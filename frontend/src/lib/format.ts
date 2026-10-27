// Display formatting only. No financial calculation happens in the frontend.

const inr = new Intl.NumberFormat('en-IN', { maximumFractionDigits: 2, minimumFractionDigits: 2 })
const inrWhole = new Intl.NumberFormat('en-IN', { maximumFractionDigits: 0 })
const plain = new Intl.NumberFormat('en-IN')

/** A decimal string from the API, shown with Indian digit grouping. */
export function money(value: string | null | undefined, decimals = 2): string {
  if (value == null) return '—'
  const n = Number(value)
  if (!Number.isFinite(n)) return '—'
  return decimals === 0 ? inrWhole.format(n) : inr.format(n)
}

export function count(value: number | null | undefined): string {
  return value == null ? '—' : plain.format(value)
}

export function bps(value: number | null | undefined, digits = 1): string {
  if (value == null || !Number.isFinite(value)) return '—'
  const sign = value > 0 ? '+' : value < 0 ? '−' : ''
  return `${sign}${Math.abs(value).toFixed(digits)}`
}

export function fixed(value: number | null | undefined, digits = 2): string {
  if (value == null || !Number.isFinite(value)) return '—'
  return value.toFixed(digits)
}

export function percent(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return '—'
  return `${(value * 100).toFixed(0)}%`
}

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
const timeFmt = new Intl.DateTimeFormat('en-GB', { dateStyle: 'medium', timeStyle: 'short' })

/** ISO date (YYYY-MM-DD) to "15 Oct 2025". */
export function day(iso: string | null | undefined): string {
  if (!iso) return '—'
  const [y, m, d] = iso.split('-')
  return `${d} ${MONTHS[Number(m) - 1]} ${y}`
}

/** ISO date (YYYY-MM-DD) to "15 Oct". */
export function shortDay(iso: string): string {
  const [, m, d] = iso.split('-')
  return `${Number(d)} ${MONTHS[Number(m) - 1]}`
}

export function monthTick(iso: string): string {
  const [y, m] = iso.split('-')
  return `${MONTHS[Number(m) - 1]} ${y.slice(2)}`
}

/** Year-month (YYYY-MM) to "Sep 2025". */
export function month(ym: string): string {
  const [y, m] = ym.split('-')
  return `${MONTHS[Number(m) - 1]} ${y}`
}

export function timestamp(iso: string): string {
  return timeFmt.format(new Date(iso))
}

export function bytes(n: number): string {
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  if (n < 1024 ** 3) return `${(n / 1024 / 1024).toFixed(1)} MB`
  return `${(n / 1024 ** 3).toFixed(1)} GB`
}

export function humanize(code: string): string {
  return code.replaceAll('_', ' ')
}
