import { getToken, useAuth } from '@/stores/auth'

export const API_BASE = (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/$/, '') ?? ''

export class ApiError extends Error {
  status: number
  detail: unknown
  constructor(status: number, detail: unknown) {
    super(typeof detail === 'string' ? detail : (detail as { detail?: string })?.detail ?? `HTTP ${status}`)
    this.status = status
    this.detail = detail
  }
}

export async function api<T = unknown>(path: string, init: RequestInit & { json?: unknown; form?: FormData } = {}): Promise<T> {
  const headers = new Headers(init.headers)
  const token = getToken()
  if (token) headers.set('Authorization', `Bearer ${token}`)
  let body = init.body
  if (init.json !== undefined) { headers.set('Content-Type', 'application/json'); body = JSON.stringify(init.json) }
  if (init.form) body = init.form
  const res = await fetch(`${API_BASE}${path}`, { ...init, headers, body, credentials: 'include' })
  if (res.status === 401 && !path.startsWith('/api/auth/')) {
    useAuth.getState().clear()
    if (!location.pathname.startsWith('/login')) location.assign('/login')
  }
  if (!res.ok) {
    let detail: unknown = await res.text()
    try { detail = JSON.parse(detail as string) } catch { /* text */ }
    throw new ApiError(res.status, detail)
  }
  if (res.status === 204) return undefined as T
  const ct = res.headers.get('content-type') ?? ''
  return (ct.includes('application/json') ? res.json() : res.text()) as Promise<T>
}

export const get = <T,>(path: string) => api<T>(path)
export const post = <T,>(path: string, json?: unknown) => api<T>(path, { method: 'POST', json })
export const put = <T,>(path: string, json?: unknown) => api<T>(path, { method: 'PUT', json })
export const patch = <T,>(path: string, json?: unknown) => api<T>(path, { method: 'PATCH', json })
export const del = <T,>(path: string) => api<T>(path, { method: 'DELETE' })
export const upload = <T,>(path: string, form: FormData) => api<T>(path, { method: 'POST', form })

export function fileUrl(projectId: string, fileId: string, download = false) {
  const t = getToken()
  return `${API_BASE}/api/projects/${projectId}/files/${fileId}/content?${download ? 'download=true&' : ''}token=${t ?? ''}`
}
