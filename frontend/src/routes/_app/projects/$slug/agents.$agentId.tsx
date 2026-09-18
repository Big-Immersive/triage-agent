import { Link, createFileRoute } from '@tanstack/react-router'
import { useEffect } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { Field, Panel, PromptHeader, StatusDot, ThinkingBars } from '@/components/ui'
import { useActiveProject } from '@/components/layout/ProjectShell'
import { qk, useAgentDetail, useProjectEvents } from '@/api/queries'
import { ago, hhmmss } from '@/utils/format'

export const Route = createFileRoute('/_app/projects/$slug/agents/$agentId')({ component: AgentDetail })

function AgentDetail() {
  const p = useActiveProject()
  const { agentId } = Route.useParams()
  const { data, refetch } = useAgentDetail(p.id, agentId)
  const qc = useQueryClient()
  // Live: any run event / status change for this project refreshes the panel.
  useProjectEvents(p.id, (ev) => { if (ev.type === 'run.event' || ev.type === 'run.status' || ev.type === 'agent.status') qc.invalidateQueries({ queryKey: qk.agentDetail(p.id, agentId) }) })
  useEffect(() => { refetch() }, [refetch])
  if (!data) return <div className="text-fg-3">loading…</div>
  const a = data.agent
  const live = data.run && (data.run.status === 'running' || data.run.status === 'waiting_approval')
  return (
    <div>
      <PromptHeader title={`agent ${a.name}`} subtitle={a.description || a.role} right={<Link to="/projects/$slug/agents" params={{ slug: p.slug }} className="text-[11px] text-fg-3 hover:text-neon">← all agents</Link>} />
      <div className="grid gap-4 xl:grid-cols-[260px_1fr_280px]">
        <Panel title="IDENTITY">
          <div className="p-3">
            <Field k="AGENT" v={a.name} />
            <Field k="ROLE" v={a.role || '—'} mono={false} />
            <Field k="MODEL" v={a.model || 'default'} />
            <Field k="STATUS" v={<span className="flex items-center gap-2"><StatusDot status={a.enabled ? a.status : 'disabled'} />{a.status === 'thinking' && <ThinkingBars />}</span>} />
            <Field k="PROCESS" v={a.current_process ?? '—'} />
            <Field k="LAST ACTIVE" v={ago(a.last_active_at)} />
            <div className="mt-3 label">tools</div>
            <div className="mt-1 flex flex-wrap gap-1">{a.tools.map((t) => <span key={t} className="border border-line px-1.5 py-0.5 text-[10px] text-fg-2">{t}</span>)}{!a.tools.length && <span className="text-fg-3">none</span>}</div>
            <div className="mt-3 label">permissions</div>
            <div className="mt-1 text-[11px] text-fg-2">{a.permissions.side_effects ? 'may write artifacts' : 'read-only'} · {a.permissions.requires_approval ? 'gated actions need a human' : 'autonomous'}</div>
            <div className="mt-3 label">hands off to</div>
            <div className="mt-1 text-[11px] text-fg-2">{a.can_handoff_to.join(', ') || '—'}</div>
          </div>
        </Panel>
        <Panel title={<span>LIVE EXECUTION {data.run && <Link to="/projects/$slug/runs/$runId" params={{ slug: p.slug, runId: data.run.id }} className="ml-2 text-neon hover:underline">{data.run.id}</Link>}</span>} right={live ? <span className="text-[10px] text-neon anim-pulse">● LIVE</span> : <span className="text-[10px] text-fg-3">last run</span>}>
          {data.events.length ? (
            <div className="py-1">
              {data.events.map((e) => (
                <div key={e.id} className="grid grid-cols-[80px_1fr] gap-2 px-3 py-0.5 text-[12px] anim-fade">
                  <span className="text-fg-3">[{hhmmss(e.ts)}]</span>
                  <span className={e.kind === 'ERROR' ? 'text-danger' : e.kind === 'HANDOFF' ? 'text-neon-2' : e.kind === 'APPROVAL' ? 'text-warn' : 'text-fg-1'}>{e.kind === 'TOOL' ? e.message : e.kind === 'TOOL_RESULT' ? `↳ ${e.message}` : e.message}</span>
                </div>
              ))}
              {live && <div className="px-3 text-neon anim-blink">▮</div>}
            </div>
          ) : <div className="p-4 text-fg-3">no execution yet · run a task to see this agent work</div>}
        </Panel>
        <div className="space-y-4">
          <Panel title="CURRENT TASK"><div className="p-3 text-[12px]">{data.run ? <><div className="text-fg-1">{data.run.id}</div><div className="text-fg-3"><StatusDot status={data.run.status} /></div></> : <span className="text-fg-3">idle</span>}</div></Panel>
          <Panel title="MEMORY USED"><div className="p-3 text-[11px] text-fg-2">{data.memory_used.length ? data.memory_used.map((m, i) => <div key={i} className="truncate-1">{m}</div>) : <span className="text-fg-3">—</span>}</div></Panel>
          <Panel title="FILES ACCESSED"><div className="p-3 text-[11px] text-fg-2">{data.files_accessed.length ? data.files_accessed.map((f) => <div key={f}>{f}</div>) : <span className="text-fg-3">—</span>}</div></Panel>
          <Panel title="TOOLS CALLED"><div className="p-3 text-[11px]">{data.tools_called.length ? data.tools_called.map((t) => <div key={t.tool} className="flex justify-between"><span className="text-fg-2">{t.tool}()</span><span className="text-fg-3">{t.count}</span></div>) : <span className="text-fg-3">—</span>}</div></Panel>
          <Panel title="HANDOFF HISTORY"><div className="p-3 text-[11px]">{data.handoffs.length ? data.handoffs.map((h, i) => <div key={i} className="flex justify-between"><span className="text-fg-2">{h.from} → {h.to}</span><Link to="/projects/$slug/runs/$runId" params={{ slug: p.slug, runId: h.run_id }} className="text-fg-3 hover:text-neon">{h.run_id}</Link></div>) : <span className="text-fg-3">—</span>}</div></Panel>
        </div>
      </div>
    </div>
  )
}
