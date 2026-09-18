import { Link, useNavigate, useRouterState } from '@tanstack/react-router'
import { clsx } from 'clsx'
import { LogOut, Menu, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useAuth } from '@/stores/auth'
import { post } from '@/api/client'
import { useHealth } from '@/api/queries'
import { wsClient } from '@/api/ws'
import { useUi } from '@/stores/ui'

const NAV = [
  { to: '/dashboard', label: 'dashboard', star: false },
  { to: '/projects', label: 'projects', star: false },
  { to: '/projects/new', label: 'new_project', star: true },
  { to: '/activity', label: 'global_activity', star: false },
  { to: '/settings', label: 'settings', star: false },
] as const

export function Sidebar() {
  const { user, clear } = useAuth()
  const nav = useNavigate()
  const path = useRouterState({ select: (s) => s.location.pathname })
  const { data: health } = useHealth()
  const { collapsed, toggleCollapsed, drawerOpen, setDrawer } = useUi()
  const [ws, setWs] = useState(wsClient.status)
  useEffect(() => wsClient.onStatus(setWs), [])
  useEffect(() => { setDrawer(false) }, [path, setDrawer])

  async function logout() {
    try { await post('/api/auth/logout') } catch { /* ignore */ }
    wsClient.disconnect(); clear(); nav({ to: '/login' })
  }

  const online = health?.online
  const body = (
    <div className="flex h-full flex-col">
      <div className="border-b border-line px-3 py-3">
        <div className="flex items-center justify-between">
          <Link to="/dashboard" className="flex items-center gap-2">
            <pre className="text-neon glow-text text-[10px] leading-[10px]">{'▄▀█\n█▀█'}</pre>
            {!collapsed && <span className="text-[13px] font-medium tracking-wider text-fg-1">triage<span className="text-neon">.</span>agents</span>}
          </Link>
          <button onClick={toggleCollapsed} className="hidden text-fg-3 hover:text-fg-1 lg:block" aria-label="collapse sidebar"><Menu size={14} /></button>
          <button onClick={() => setDrawer(false)} className="text-fg-3 hover:text-fg-1 lg:hidden" aria-label="close"><X size={14} /></button>
        </div>
        {!collapsed && (
          <div className={clsx('mt-2 text-[10px] tracking-widest', online == null ? 'text-fg-3' : online ? 'text-neon' : 'text-warn')}>
            <span className={clsx('mr-1.5 inline-block h-1.5 w-1.5 rounded-full bg-current', online && 'glow-sm anim-pulse')} />
            {online == null ? 'SYSTEM …' : online ? 'SYSTEM ONLINE' : 'SYSTEM DEGRADED'}
          </div>
        )}
      </div>
      <nav className="flex-1 space-y-0.5 px-2 py-3">
        {NAV.map((n) => {
          const active = n.to === '/projects' ? path === '/projects' || (path.startsWith('/projects/') && !path.startsWith('/projects/new')) : path.startsWith(n.to)
          return (
            <Link key={n.to} to={n.to} title={n.label} className={clsx('block border px-2 py-1.5 text-[12px] tracking-wide transition-colors', active ? 'border-neon/40 bg-neon/5 text-neon glow-sm' : 'border-transparent text-fg-2 hover:text-fg-1 hover:border-line')}>
              <span className={n.star ? 'text-neon' : 'text-fg-3'}>{n.star ? '*' : '>'}</span>{!collapsed && <span className="ml-1.5">{n.label}</span>}
            </Link>
          )
        })}
      </nav>
      <div className="border-t border-line px-3 py-3 text-[11px]">
        {!collapsed && (
          <>
            <div className="truncate-1 text-fg-1">{user?.name || user?.email}</div>
            <div className="truncate-1 text-fg-3">{user?.email}</div>
            <div className="mt-2 flex items-center justify-between">
              <span className="label">workspace</span><span className="text-fg-2">personal</span>
            </div>
            <div className="mt-1 flex items-center justify-between">
              <span className="label">connection</span>
              <span className={clsx(ws === 'connected' ? 'text-neon' : ws === 'connecting' ? 'text-warn' : 'text-fg-3')}>● {ws.toUpperCase()}</span>
            </div>
          </>
        )}
        <button onClick={logout} className="mt-3 flex w-full items-center gap-1.5 text-fg-3 hover:text-danger"><LogOut size={12} />{!collapsed && 'logout'}</button>
      </div>
    </div>
  )

  return (
    <>
      <aside className={clsx('hidden shrink-0 border-r border-line bg-bg-1 lg:block transition-[width]', collapsed ? 'w-12' : 'w-56')}>{body}</aside>
      {drawerOpen && (
        <div className="fixed inset-0 z-40 lg:hidden" onClick={() => setDrawer(false)}>
          <div className="absolute inset-0 bg-black/60" />
          <aside className="absolute inset-y-0 left-0 w-64 border-r border-line bg-bg-1 anim-fade" onClick={(e) => e.stopPropagation()}>{body}</aside>
        </div>
      )}
    </>
  )
}
