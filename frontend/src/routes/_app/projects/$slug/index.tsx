import { Link, createFileRoute } from '@tanstack/react-router'
import { useMemo, useState } from 'react'
import { clsx } from 'clsx'
import { Panel, StatTile, StatusDot, ThinkingBars } from '@/components/ui'
import { ActivityFeed } from '@/components/features/ActivityFeed'
import { RunTimeline } from '@/components/features/RunTimeline'
import { useActiveProject } from '@/components/layout/ProjectShell'
import { useAgents, useOverview, useRunEvents, useRuns } from '@/api/queries'
import { ago, dateStamp, duration, hhmmss, pad2 } from '@/utils/format'
import type { RunEvent } from '@/api/types'

export const Route = createFileRoute('/_app/projects/$slug/')({ component: Overview })

const WORKING = ['thinking', 'running', 'tool_call', 'waiting', 'human_input']

function Overview() {
  const p = useActiveProject()
  const { data } = useOverview(p.id)
  const { data: agents } = useAgents(p.id)
  const { data: runs } = useRuns(p.id)
  const [showInstructions, setShowInstructions] = useState(false)
  const c = data?.counts ?? {}

  // The run the agents are working on right now (queued/running/waiting), else the most recent one.
  const activeRun = useMemo(() => (runs ?? []).find((r) => ['running', 'waiting_approval', 'queued'].includes(r.status)) ?? null, [runs])
  const shownRun = activeRun ?? (runs ?? [])[0] ?? null
  const { data: events } = useRunEvents(p.id, shownRun?.id ?? '')
  const live = !!activeRun

  // Last few observable steps per agent from the shown run, so each card tells what it is doing.
  const stepsByAgent = useMemo(() => {
    const m = new Map<string, RunEvent[]>()
    for (const e of events ?? []) {
      const who = e.actor.toLowerCase()
      if (!agents?.some((a) => a.name === who)) continue
      if (!m.has(who)) m.set(who, [])
      m.get(who)!.push(e)
    }
    return m
  }, [events, agents])

  const working = (agents ?? []).filter((a) => WORKING.includes(a.status)).length

  return (
    <div className="space-y-4">
      {/* ---- project identity ---- */}
      <section className="panel p-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex items-center gap-3">
              <span className="text-2xl text-neon glow-text">{p.icon}</span>
              <div>
                <h1 className="text-lg font-medium text-fg-1">{p.name}</h1>
                <div className="text-[11px] text-fg-3">~/projects/{p.slug}</div>
              </div>
            </div>
            <p className="mt-2 max-w-3xl text-[13px] text-fg-2 font-sans">{p.description || 'No description yet — add one under settings › project.config.'}</p>
          </div>
          <div className="grid grid-cols-2 gap-x-6 gap-y-1 text-[11px] sm:grid-cols-3">
            <div><div className="label">STATUS</div><StatusDot status={p.status === 'active' ? 'running' : p.status} label={p.status.toUpperCase()} /></div>
            <div><div className="label">CREATED</div><div className="text-fg-1">{dateStamp(p.created_at)}</div></div>
            <div><div className="label">LAST ACTIVITY</div><div className="text-fg-1">{ago(p.last_activity_at)}</div></div>
            <div><div className="label">AGENTS</div><div className="text-fg-1">{pad2(p.agents_total)} <span className={working ? 'text-neon' : 'text-fg-3'}>{working ? `${working} WORKING` : 'IDLE'}</span></div></div>
            <div><div className="label">RUNS</div><div className="text-fg-1">{pad2(p.runs_active)} <span className={p.runs_active ? 'text-neon' : 'text-fg-3'}>ACTIVE</span></div></div>
            <div><div className="label">MEMORY</div><div className={p.memory_synced ? 'text-fg-1' : 'text-warn'}>{p.memory_synced ? 'SYNCED' : '◉ INDEXING'}</div></div>
          </div>
        </div>
        {p.instructions && (
          <div className="mt-3 border-t border-line pt-2">
            <button onClick={() => setShowInstructions((s) => !s)} className="label hover:text-fg-2">{showInstructions ? '▾' : '▸'} project instructions (sent to every agent)</button>
            {showInstructions && <pre className="mt-2 whitespace-pre-wrap text-[12px] text-fg-2 font-sans">{p.instructions}</pre>}
          </div>
        )}
      </section>

      {/* ---- metrics ---- */}
      <div className="grid grid-cols-2 gap-2 md:grid-cols-3 xl:grid-cols-6">
        <StatTile label="ACTIVE_AGENTS" value={`${pad2(working)} / ${pad2(c.agents_enabled ?? 0)}`} sub={working ? '● WORKING' : '● ONLINE'} />
        <StatTile label="RUNNING_TASKS" value={pad2(c.running_tasks ?? 0)} sub={c.queued_tasks ? `${c.queued_tasks} queued` : ''} />
        <StatTile label="RUNS_TODAY" value={pad2(c.runs_today ?? 0)} sub={c.runs_active ? `◉ ${c.runs_active} active` : ''} />
        <StatTile label="WAITING_APPROVAL" value={pad2(c.waiting_approval ?? 0)} tone={c.waiting_approval ? 'amber' : 'neon'} sub={c.waiting_approval ? 'awaiting human input' : ''} />
        <StatTile label="MEMORY_RECORDS" value={pad2(c.memory_records ?? 0)} />
        <StatTile label="KNOWLEDGE_ITEMS" value={pad2(c.knowledge_items ?? 0)} sub={c.knowledge_indexing ? `INDEXING ${c.knowledge_indexing}` : `${c.knowledge_ready ?? 0} ready`} tone={c.knowledge_indexing ? 'amber' : 'neon'} />
      </div>

      {/* ---- agents at work ---- */}
      <Panel title={<span>AGENTS AT WORK {activeRun && <span className="ml-2 text-neon">· {activeRun.id} · {activeRun.task_external_id ?? ''}</span>}</span>}
        right={live ? <span className="text-[10px] text-neon anim-pulse">● LIVE</span> : <Link to="/projects/$slug/tasks" params={{ slug: p.slug }} className="text-[11px] text-fg-3 hover:text-neon">run a task →</Link>}>
        {!agents?.length ? (
          <div className="p-4 text-fg-3"><span className="text-neon">$</span> agent list — no agents deployed · <Link to="/projects/$slug/agents" params={{ slug: p.slug }} className="text-neon">configure agents</Link></div>
        ) : (
          <div className="grid gap-px bg-line sm:grid-cols-2 xl:grid-cols-4">
            {agents.map((a) => {
              const isWorking = WORKING.includes(a.status)
              const isCurrent = activeRun?.current_agent === a.name
              const steps = (stepsByAgent.get(a.name) ?? []).slice(-3)
              return (
                <Link key={a.id} to="/projects/$slug/agents/$agentId" params={{ slug: p.slug, agentId: a.id }}
                  className={clsx('block bg-bg-1 p-3 transition-shadow hover:bg-bg-2', isCurrent && 'glow-ring', !a.enabled && 'opacity-50')}>
                  <div className="flex items-center justify-between">
                    <span className="text-[13px] text-fg-1">{a.name}</span>
                    <span className="flex items-center gap-2">{a.status === 'thinking' && <ThinkingBars />}<StatusDot status={a.enabled ? a.status : 'disabled'} /></span>
                  </div>
                  <div className="text-[11px] text-fg-3">{a.role || '—'}{a.model ? <span> · {a.model}</span> : null}</div>
                  <div className={clsx('mt-2 min-h-[18px] truncate-1 text-[12px]', isWorking ? 'text-neon' : 'text-fg-3')}>
                    {a.current_process ? `▸ ${a.current_process}` : isWorking ? '▸ working' : a.last_active_at ? `last active ${ago(a.last_active_at)}` : 'never ran'}
                  </div>
                  {steps.length > 0 && (
                    <div className="mt-2 space-y-0.5 border-t border-line pt-2 text-[11px]">
                      {steps.map((e) => (
                        <div key={e.id} className="grid grid-cols-[62px_1fr] gap-1">
                          <span className="text-fg-3 tabular-nums">{hhmmss(e.ts)}</span>
                          <span className={clsx('truncate-1', e.kind === 'ERROR' ? 'text-danger' : e.kind === 'HANDOFF' ? 'text-neon-2' : e.kind === 'APPROVAL' ? 'text-warn' : 'text-fg-2')}>{e.message}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </Link>
              )
            })}
          </div>
        )}
      </Panel>

      {/* ---- live execution + activity ---- */}
      <div className="grid gap-4 xl:grid-cols-[3fr_2fr]">
        <Panel title={<span>{live ? 'LIVE EXECUTION' : 'LAST EXECUTION'} {shownRun && <Link to="/projects/$slug/runs/$runId" params={{ slug: p.slug, runId: shownRun.id }} className="ml-2 text-neon hover:underline">{shownRun.id}</Link>}</span>}
          right={shownRun ? <span className="flex items-center gap-3 text-[11px] text-fg-3"><StatusDot status={shownRun.status} /><span className="tabular-nums">{duration(shownRun.duration_ms, live ? shownRun.started_at : undefined)}</span></span> : null}>
          {shownRun ? <div className="py-1"><RunTimeline events={events ?? []} live={live} compact /></div> : (
            <div className="p-4 text-fg-3">nothing has run yet · <Link to="/projects/$slug/tasks" params={{ slug: p.slug }} className="text-neon">open tasks</Link> and press RUN</div>
          )}
          {shownRun?.status === 'waiting_approval' && (
            <div className="border-t border-warn/30 bg-warn/5 px-3 py-2 text-[11px] text-warn">● run paused for human approval — <Link to="/projects/$slug/approvals" params={{ slug: p.slug }} className="underline">open the approval queue</Link></div>
          )}
        </Panel>
        <Panel title="LIVE SYSTEM ACTIVITY" right={<Link to="/projects/$slug/activity" params={{ slug: p.slug }} className="text-[11px] text-fg-3 hover:text-neon">full feed →</Link>}>
          <ActivityFeed items={[...(data?.activity ?? [])].reverse()} slug={p.slug} height={320} />
        </Panel>
      </div>

      {/* ---- recent runs ---- */}
      <Panel title="RECENT RUNS" right={<Link to="/projects/$slug/runs" params={{ slug: p.slug }} className="text-[11px] text-fg-3 hover:text-neon">all runs →</Link>}>
        <div className="divide-y divide-line">
          {(runs ?? []).slice(0, 6).map((r) => (
            <Link key={r.id} to="/projects/$slug/runs/$runId" params={{ slug: p.slug, runId: r.id }} className="grid grid-cols-[1fr_auto] items-center gap-3 px-3 py-1.5 text-[12px] hover:bg-bg-2 md:grid-cols-[120px_90px_1fr_110px_70px]">
              <span className="text-fg-1">{r.id}</span>
              <span className="hidden text-fg-2 md:block">{r.task_external_id ?? '—'}</span>
              <span className="hidden truncate-1 text-fg-3 md:block">{r.result ? `${r.result.outcome}${r.result.ticket_id ? ' → ' + r.result.ticket_id : r.result.duplicate_of ? ' ↔ ' + r.result.duplicate_of : ''}` : r.current_agent ? `${r.current_agent} working` : ''}</span>
              <StatusDot status={r.status} />
              <span className="hidden text-right text-fg-3 tabular-nums md:block">{duration(r.duration_ms, ['running', 'waiting_approval'].includes(r.status) ? r.started_at : undefined)}</span>
            </Link>
          ))}
          {!runs?.length && <div className="px-3 py-3 text-fg-3">no runs yet</div>}
        </div>
      </Panel>
    </div>
  )
}
