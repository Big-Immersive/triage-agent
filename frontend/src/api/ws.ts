/** One WebSocket per tab. Components subscribe to a channel (project id or "global")
 *  and receive every event on it; the socket reconnects with backoff and re-subscribes. */
import { API_BASE } from './client'
import { getToken } from '@/stores/auth'

export interface WsEvent { type: string; channel: string; payload: Record<string, unknown> }
type Listener = (ev: WsEvent) => void

class WsClient {
  private ws: WebSocket | null = null
  private listeners = new Map<string, Set<Listener>>()
  private wanted = new Set<string>()
  private backoff = 1000
  private timer: number | null = null
  private statusListeners = new Set<(s: 'connected' | 'connecting' | 'offline') => void>()
  status: 'connected' | 'connecting' | 'offline' = 'offline'

  private url() {
    const base = API_BASE || `${location.protocol}//${location.host}`
    return `${base.replace(/^http/, 'ws')}/ws?token=${encodeURIComponent(getToken() ?? '')}`
  }

  private setStatus(s: typeof this.status) { this.status = s; this.statusListeners.forEach((l) => l(s)) }
  onStatus(l: (s: typeof this.status) => void) { this.statusListeners.add(l); l(this.status); return () => { this.statusListeners.delete(l) } }

  connect() {
    if (!getToken() || (this.ws && this.ws.readyState <= 1)) return
    this.setStatus('connecting')
    const ws = new WebSocket(this.url())
    this.ws = ws
    ws.onopen = () => {
      this.backoff = 1000
      this.setStatus('connected')
      this.wanted.forEach((ch) => ws.send(JSON.stringify({ subscribe: ch })))
    }
    ws.onmessage = (m) => {
      let ev: WsEvent
      try { ev = JSON.parse(m.data) } catch { return }
      this.listeners.get(ev.channel)?.forEach((l) => l(ev))
      if (ev.channel.startsWith('global:')) this.listeners.get('global')?.forEach((l) => l(ev))
      this.listeners.get('*')?.forEach((l) => l(ev))
    }
    ws.onclose = () => {
      this.setStatus('offline')
      if (!getToken()) return
      this.timer = window.setTimeout(() => this.connect(), this.backoff)
      this.backoff = Math.min(this.backoff * 2, 15000)
    }
    ws.onerror = () => ws.close()
  }

  disconnect() {
    if (this.timer) window.clearTimeout(this.timer)
    this.ws?.close()
    this.ws = null
    this.setStatus('offline')
  }

  subscribe(channel: string, l: Listener) {
    if (!this.listeners.has(channel)) this.listeners.set(channel, new Set())
    this.listeners.get(channel)!.add(l)
    if (channel !== 'global' && channel !== '*' && !this.wanted.has(channel)) {
      this.wanted.add(channel)
      if (this.ws?.readyState === 1) this.ws.send(JSON.stringify({ subscribe: channel }))
    }
    this.connect()
    return () => {
      this.listeners.get(channel)?.delete(l)
      if (this.listeners.get(channel)?.size === 0 && channel !== 'global' && channel !== '*') {
        this.wanted.delete(channel)
        if (this.ws?.readyState === 1) this.ws.send(JSON.stringify({ unsubscribe: channel }))
      }
    }
  }
}

export const wsClient = new WsClient()
