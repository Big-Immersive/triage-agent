import { useEffect, useRef, useState } from 'react'
import { clsx } from 'clsx'
import { hhmmss } from '@/utils/format'
import type { RunEvent } from '@/api/types'

const KIND_COLOR: Record<string, string> = {
  SYSTEM: 'text-fg-3', AGENT: 'text-neon', MEMORY: 'text-info', TOOL: 'text-fg-1', TOOL_RESULT: 'text-fg-2', HANDOFF: 'text-neon-2', APPROVAL: 'text-warn', ERROR: 'text-danger', FINAL: 'text-neon',
}

export function RunTimeline({ events, live, compact }: { events: RunEvent[]; live?: boolean; compact?: boolean }) {
  const [open, setOpen] = useState<Set<number>>(new Set())
  const [follow, setFollow] = useState(true)
  const end = useRef<HTMLDivElement>(null)
  useEffect(() => { if (follow && live) end.current?.scrollIntoView({ block: 'nearest' }) }, [events.length, follow, live])
  const toggle = (id: number) => setOpen((s) => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n })
  return (
    <div className="relative">
      {live && <button onClick={() => setFollow((f) => !f)} className={clsx('absolute right-2 top-1 z-10 text-[10px] tracking-wider', follow ? 'text-neon' : 'text-fg-3')}>{follow ? '● FOLLOW' : '○ FOLLOW'}</button>}
      <div className={clsx('overflow-y-auto', compact ? 'max-h-72' : 'max-h-[60vh]')} onScroll={(e) => { const el = e.currentTarget; setFollow(el.scrollHeight - el.scrollTop - el.clientHeight < 24) }}>
        {events.map((e) => {
          const expandable = !compact && (e.input || e.output || (e.meta && Object.keys(e.meta).length > 0))
          const isOpen = open.has(e.id)
          return (
            <div key={e.id} className="anim-fade">
              <div onClick={() => expandable && toggle(e.id)} className={clsx('grid grid-cols-[62px_110px_1fr] gap-2 px-2 py-0.5 text-[12px] md:grid-cols-[70px_130px_1fr_60px]', expandable && 'cursor-pointer hover:bg-bg-2', e.kind === 'APPROVAL' && 'bg-warn/5')}>
                <span className="text-fg-3 tabular-nums">{hhmmss(e.ts)}</span>
                <span className={clsx('truncate-1 tracking-wider', KIND_COLOR[e.kind] ?? 'text-fg-2')}>{e.kind === 'AGENT' || e.kind === 'TOOL' ? e.actor : e.kind}</span>
                <span className={clsx('min-w-0 break-words', e.kind === 'ERROR' ? 'text-danger' : 'text-fg-1')}>{e.kind === 'TOOL' ? <span className="text-fg-1">{e.message}</span> : e.message}{expandable && <span className="ml-2 text-fg-3">{isOpen ? '▾' : '▸'}</span>}</span>
                <span className="hidden text-right text-fg-3 tabular-nums md:block">{e.duration_ms != null ? `${e.duration_ms}ms` : ''}</span>
              </div>
              {isOpen && (
                <div className="mx-2 mb-1 grid gap-2 border border-line bg-bg-0 p-2 text-[11px] md:grid-cols-2">
                  {e.input && <div><div className="label mb-1">input / tool arguments</div><pre className="max-h-48 overflow-auto whitespace-pre-wrap text-fg-2">{JSON.stringify(e.input, null, 1)}</pre></div>}
                  {e.output && <div><div className="label mb-1">output / tool result</div><pre className="max-h-48 overflow-auto whitespace-pre-wrap text-fg-2">{e.output.text ?? JSON.stringify(e.output, null, 1)}</pre></div>}
                  <div className="md:col-span-2 flex flex-wrap gap-3 text-fg-3"><span>seq {e.seq}</span><span>actor {e.actor}</span>{e.duration_ms != null && <span>execution {e.duration_ms} ms</span>}{Object.entries(e.meta ?? {}).map(([k, v]) => <span key={k}>{k} {String(v)}</span>)}</div>
                </div>
              )}
            </div>
          )
        })}
        {live && <div className="px-2 py-1 text-[11px] text-neon anim-blink">▮</div>}
        <div ref={end} />
      </div>
    </div>
  )
}
