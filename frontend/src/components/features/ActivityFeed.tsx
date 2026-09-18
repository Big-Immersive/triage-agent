import { Link } from '@tanstack/react-router'
import { useRef } from 'react'
import { useVirtualizer } from '@tanstack/react-virtual'
import { clsx } from 'clsx'
import { hhmmss } from '@/utils/format'
import type { Activity } from '@/api/types'

const CAT_COLOR: Record<string, string> = { PROJECT: 'text-fg-2', AGENT: 'text-neon', RUN: 'text-neon-2', MEMORY: 'text-info', FILE: 'text-fg-1', KNOWLEDGE: 'text-fg-2', APPROVAL: 'text-warn', SYSTEM: 'text-fg-3' }

function refLink(a: Activity, slug?: string) {
  if (!slug || !a.ref_id) return null
  if (a.ref_type === 'run') return <Link to="/projects/$slug/runs/$runId" params={{ slug, runId: a.ref_id }} className="text-fg-3 hover:text-neon">→ {a.ref_id}</Link>
  if (a.ref_type === 'approval') return <Link to="/projects/$slug/approvals" params={{ slug }} className="text-fg-3 hover:text-warn">→ {a.ref_id}</Link>
  return null
}

export function ActivityFeed({ items, slug, height = 420, showProject, newestFirst = true }: { items: Activity[]; slug?: string; height?: number; showProject?: boolean; newestFirst?: boolean }) {
  const parent = useRef<HTMLDivElement>(null)
  const rows = newestFirst ? items : [...items]
  const v = useVirtualizer({ count: rows.length, getScrollElement: () => parent.current, estimateSize: () => 24, overscan: 20 })
  if (!rows.length) return <div className="px-3 py-6 text-center text-fg-3">no activity yet</div>
  return (
    <div ref={parent} style={{ height, maxHeight: height }} className="overflow-y-auto">
      <div style={{ height: v.getTotalSize(), position: 'relative' }}>
        {v.getVirtualItems().map((vi) => {
          const a = rows[vi.index]
          const s = a.project_slug ?? slug
          return (
            <div key={a.id} className="absolute left-0 right-0 grid grid-cols-[62px_78px_1fr] gap-2 px-2 text-[12px] md:grid-cols-[70px_90px_1fr_auto]" style={{ transform: `translateY(${vi.start}px)`, height: vi.size }}>
              <span className="text-fg-3 tabular-nums">{hhmmss(a.ts)}</span>
              <span className={clsx('tracking-wider', CAT_COLOR[a.category] ?? 'text-fg-2')}>{a.category}</span>
              <span className="truncate-1 text-fg-1">{showProject && s && <Link to="/projects/$slug" params={{ slug: s }} className="mr-2 text-fg-3 hover:text-neon">{s}</Link>}{a.message}</span>
              <span className="hidden md:block">{refLink(a, s)}</span>
            </div>
          )
        })}
      </div>
    </div>
  )
}
