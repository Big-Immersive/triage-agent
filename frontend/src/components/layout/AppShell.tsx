import { Outlet, useRouterState } from '@tanstack/react-router'
import { Menu } from 'lucide-react'
import { useEffect, useRef } from 'react'
import { Sidebar } from './Sidebar'
import { PathBar } from './PathBar'
import { ProjectSwitcher } from './ProjectSwitcher'
import { useGlobalEvents } from '@/api/queries'
import { useUi } from '@/stores/ui'
import { wsClient } from '@/api/ws'

export function AppShell() {
  useGlobalEvents()
  const { setDrawer, setSwitcher } = useUi()
  const path = useRouterState({ select: (s) => s.location.pathname })
  const mainRef = useRef<HTMLElement>(null)
  useEffect(() => { wsClient.connect() }, [])
  // The content area is its own scroll container, so the router's window scroll restoration does not apply.
  useEffect(() => { mainRef.current?.scrollTo({ top: 0 }) }, [path])
  useEffect(() => {
    const h = (e: KeyboardEvent) => { if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); setSwitcher(true) } }
    window.addEventListener('keydown', h)
    return () => window.removeEventListener('keydown', h)
  }, [setSwitcher])
  return (
    <div className="flex h-full">
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <div className="flex h-9 items-center gap-2 border-b border-line bg-bg-1 px-3">
          <button onClick={() => setDrawer(true)} className="text-fg-3 hover:text-fg-1 lg:hidden" aria-label="menu"><Menu size={14} /></button>
          <PathBar path={path} />
        </div>
        <main ref={mainRef} className="canvas-grid min-w-0 flex-1 overflow-y-auto">
          <Outlet />
        </main>
      </div>
      <ProjectSwitcher />
    </div>
  )
}
