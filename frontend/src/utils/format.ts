export function hhmmss(ts: string | Date): string {
  const d = typeof ts === 'string' ? new Date(ts) : ts
  return d.toLocaleTimeString('en-GB', { hour12: false })
}
export function hhmm(ts: string | Date): string {
  return hhmmss(ts).slice(0, 5)
}
export function dateStamp(ts: string | Date): string {
  const d = typeof ts === 'string' ? new Date(ts) : ts
  const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()} ${p(d.getMonth() + 1)} ${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}
export function ago(ts: string | Date | null | undefined, now = Date.now()): string {
  if (!ts) return '—'
  const s = Math.max(0, Math.round((now - new Date(ts).getTime()) / 1000))
  if (s < 5) return 'now'
  if (s < 60) return `${s}s ago`
  const m = Math.round(s / 60)
  if (m < 60) return `${m}m ago`
  const h = Math.round(m / 60)
  if (h < 48) return `${h}h ago`
  return `${Math.round(h / 24)}d ago`
}
export function duration(ms: number | null | undefined, live?: string): string {
  if (ms == null && live) ms = Date.now() - new Date(live).getTime()
  if (ms == null) return '—'
  const s = Math.floor(ms / 1000)
  const p = (n: number) => String(n).padStart(2, '0')
  return s >= 3600 ? `${Math.floor(s / 3600)}:${p(Math.floor((s % 3600) / 60))}:${p(s % 60)}` : `${p(Math.floor(s / 60))}:${p(s % 60)}`
}
export function pad2(n: number) { return String(n).padStart(2, '0') }
export function bytes(n: number): string {
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${Math.round(n / 1024)} KB`
  return `${(n / 1024 / 1024).toFixed(1)} MB`
}
export function usd(n: number): string {
  return n < 0.01 && n > 0 ? `$${n.toFixed(4)}` : `$${n.toFixed(2)}`
}
export function bar(pct: number, width = 10): string {
  const full = Math.round((Math.max(0, Math.min(100, pct)) / 100) * width)
  return '█'.repeat(full) + '░'.repeat(width - full)
}
