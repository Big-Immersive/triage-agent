import { Link, createFileRoute } from '@tanstack/react-router'
import { useEffect, useState } from 'react'
import { Btn, Panel, StatusDot, Toast, useToast } from '@/components/ui'
import { RunTimeline } from '@/components/features/RunTimeline'
import { useActiveProject } from '@/components/layout/ProjectShell'
import { post } from '@/api/client'
import { useRun, useRunEvents } from '@/api/queries'
import { duration, hhmmss } from '@/utils/format'

export const Route = createFileRoute('/_app/projects/$slug/runs/$runId')({ component: RunDetail })

function RunDetail() {
  const p = useActiveProject()
  const { runId } = Route.useParams()
  const { data: run } = useRun(p.id, runId)
  const { data: events } = useRunEvents(p.id, runId)
  const { toast, show, error } = useToast()
  const [, tick] = useState(0)
  const live = !!run && ['queued', 'running', 'waiting_approval'].includes(run.status)
  useEffect(() => { if (!live) return; const id = setInterval(() => tick((t) => t + 1), 1000); return () => clearInterval(id) }, [live])
  if (!run) return <div className="text-fg-3">loading run…</div>
  async function cancel() { try { await post(`/api/projects/${p.id}/runs/${runId}/cancel`); show('cancel requested') } catch (e) { error(e) } }
  const r = run.result
  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center gap-x-6 gap-y-2 border-b border-line pb-3 text-[12px]">
        <span className="text-[15px] text-fg-1 glow-text">{run.id}</span>
        <span className="flex items-center gap-1.5"><span className="label">STATUS</span><StatusDot status={run.status} size="md" /></span>
        <span><span className="label">PROJECT</span> <span className="text-fg-1">{p.slug}</span></span>
        <span><span className="label">TASK</span> <span className="text-fg-1">{run.task_external_id ?? '—'}</span></span>
        <span><span className="label">STARTED</span> <span className="text-fg-1 tabular-nums">{hhmmss(run.started_at)}</span></span>
        <span><span className="label">DURATION</span> <span className="text-fg-1 tabular-nums">{duration(run.duration_ms, live ? run.started_at : undefined)}</span></span>
        <span><span className="label">AGENT</span> <span className={live ? 'text-neon' : 'text-fg-1'}>{run.current_agent ?? '—'}</span></span>
        <span className="ml-auto flex gap-2">
          {run.status === 'waiting_approval' && <Link to="/projects/$slug/approvals" params={{ slug: p.slug }}><Btn tone="amber" size="sm">● awaiting approval →</Btn></Link>}
          {live && <Btn tone="danger" size="sm" onClick={cancel}>cancel run</Btn>}
          <Link to="/projects/$slug/runs" params={{ slug: p.slug }} className="text-[11px] text-fg-3 hover:text-neon self-center">← runs</Link>
        </span>
      </div>
      <div className="grid gap-4 xl:grid-cols-[1fr_300px]">
        <Panel title="EXECUTION TIMELINE" right={<span className="text-[10px] text-fg-3">{events?.length ?? 0} events · click a row to inspect</span>}>
          <div className="py-1"><RunTimeline events={events ?? []} live={live} /></div>
        </Panel>
        <div className="space-y-4">
          <Panel title="RESULT">
            <div className="p-3 text-[12px]">
              {run.error && <div className="mb-2 text-danger">✖ {run.error}</div>}
              {r ? <div className="space-y-0.5">
                <div><span className="label">OUTCOME </span><span className="text-fg-1">{r.outcome}</span></div>
                {r.category && <div><span className="label">CATEGORY </span>{r.category}</div>}
                {r.severity && <div><span className="label">SEVERITY </span><span className={r.severity === 'critical' || r.severity === 'high' ? 'text-warn' : ''}>{r.severity}</span></div>}
                {r.component && <div><span className="label">COMPONENT </span>{r.component}</div>}
                {r.ticket_id && <div><span className="label">TICKET </span><Link to="/projects/$slug/tickets" params={{ slug: p.slug }} className="text-neon hover:underline">{r.ticket_id} →</Link></div>}
                {r.duplicate_of && <div><span className="label">DUPLICATE OF </span><span className="text-neon">{r.duplicate_of}</span></div>}
                {r.artifact && <div><span className="label">ARTIFACT </span><Link to="/projects/$slug/files" params={{ slug: p.slug }} className="text-fg-2 hover:text-neon">/out/{r.artifact}</Link></div>}
              </div> : <span className="text-fg-3">{live ? 'in progress…' : 'no result'}</span>}
              {run.final_text && <div className="mt-2 border-t border-line pt-2 text-fg-2 font-sans">{run.final_text}</div>}
            </div>
          </Panel>
          <Panel title="COUNTERS">
            <div className="grid grid-cols-3 gap-2 p-3 text-center">
              <div><div className="label">tools</div><div className="text-lg text-fg-1">{run.tool_call_count}</div></div>
              <div><div className="label">handoffs</div><div className="text-lg text-fg-1">{run.handoff_count}</div></div>
              <div><div className="label">approval</div><div className={`text-[12px] ${run.approval_state === 'pending' ? 'text-warn' : 'text-fg-1'}`}>{run.approval_state.toUpperCase()}</div></div>
            </div>
          </Panel>
        </div>
      </div>
      <Toast msg={toast?.msg ?? null} tone={toast?.tone} />
    </div>
  )
}
