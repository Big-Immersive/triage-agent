import { Link, Outlet, useRouterState } from '@tanstack/react-router'
import { clsx } from 'clsx'
import { ChevronsUpDown } from 'lucide-react'
import { createContext, useContext, useEffect, useRef } from 'react'
import { StatusDot } from '@/components/ui'
import { useProject, useProjectEvents } from '@/api/queries'
import type { Project } from '@/api/types'
import { useUi } from '@/stores/ui'
import { pad2 } from '@/utils/format'

const Ctx = createContext<Project | null>(null)
export const useActiveProject = () => {
  const p = useContext(Ctx)
  if (!p) throw new Error('no active project')
  return p
}

const SECTIONS = [
  ['', 'overview'], ['agents', 'agents'], ['graph', 'graph'], ['runs', 'runs'], ['tasks', 'tasks'], ['tickets', 'tickets'], ['memory', 'memory'], ['knowledge', 'knowledge'],
  ['approvals', 'approvals'], ['activity', 'activity'], ['files', 'files'], ['integrations', 'integrations'], ['settings', 'settings'],
] as const

export function ProjectShell({ slug }: { slug: string }) {
  const { data: project, isLoading, error } = useProject(slug)
  useProjectEvents(project?.id)
  const { setSwitcher } = useUi()
  const path = useRouterState({ select: (s) => s.location.pathname })
  const contentRef = useRef<HTMLDivElement>(null)
  useEffect(() => { contentRef.current?.scrollTo({ top: 0 }) }, [path])
  if (isLoading) return <div className="p-6 text-fg-3">loading project…</div>
  if (error || !project) return <div className="p-6 text-danger">project not found</div>
  const base = `/projects/${project.slug}`
  const rest = path.slice(base.length).replace(/^\//, '').split('/')[0]
  return (
    <Ctx.Provider value={project}>
      <div className="flex h-full flex-col">
        <div className="flex flex-wrap items-center gap-x-5 gap-y-1 border-b border-line bg-bg-1 px-4 py-2 text-[11px]">
          <button onClick={() => setSwitcher(true)} className="flex items-center gap-1.5 text-fg-1 hover:text-neon" title="switch project (⌘K)">
            <span className="label">PROJECT /</span> <span className="text-[12px] font-medium glow-text text-neon">{project.slug}</span> <ChevronsUpDown size={12} className="text-fg-3" />
          </button>
          <span className="flex items-center gap-1.5"><span className="label">STATUS</span><StatusDot status={project.status === 'active' ? 'running' : project.status} label={project.status.toUpperCase()} /></span>
          <span><span className="label">AGENTS</span> <span className="text-fg-1">{pad2(project.agents_total)}</span>{project.agents_online > 0 && <span className="text-neon"> · {project.agents_online} online</span>}</span>
          <span><span className="label">RUNS</span> <span className={clsx(project.runs_active ? 'text-neon' : 'text-fg-1')}>{pad2(project.runs_active)}</span></span>
          {project.approvals_pending > 0 && <span className="text-warn glow-amber px-1">● {project.approvals_pending} AWAITING APPROVAL</span>}
          <span className={clsx('ml-auto', project.memory_synced ? 'text-fg-2' : 'text-warn')}>{project.memory_synced ? 'MEMORY SYNCED' : '◉ INDEXING'}</span>
        </div>
        <div className="flex min-h-0 flex-1">
          <nav className="hidden w-40 shrink-0 border-r border-line bg-bg-1/60 py-2 md:block">
            {SECTIONS.map(([seg, label]) => {
              const active = rest === seg
              return (
                <Link key={seg} to={seg ? `${base}/${seg}` : base} className={clsx('flex items-center justify-between px-3 py-1.5 text-[12px]', active ? 'text-neon border-r-2 border-neon bg-neon/5' : 'text-fg-2 hover:text-fg-1')}>
                  <span><span className={active ? 'text-neon' : 'text-fg-3'}>&gt;</span> {label}</span>
                  {seg === 'approvals' && project.approvals_pending > 0 && <span className="text-[10px] text-warn">{project.approvals_pending}</span>}
                </Link>
              )
            })}
          </nav>
          <div ref={contentRef} className="min-w-0 flex-1 overflow-y-auto">
            <div className="flex gap-1 overflow-x-auto border-b border-line px-2 py-1 md:hidden">
              {SECTIONS.map(([seg, label]) => <Link key={seg} to={seg ? `${base}/${seg}` : base} className={clsx('whitespace-nowrap px-2 py-1 text-[11px]', rest === seg ? 'text-neon' : 'text-fg-3')}>{label}</Link>)}
            </div>
            <div className="p-4 md:p-5"><Outlet /></div>
          </div>
        </div>
      </div>
    </Ctx.Provider>
  )
}
