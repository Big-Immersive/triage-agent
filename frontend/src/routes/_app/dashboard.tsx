import { Link, createFileRoute, useNavigate } from '@tanstack/react-router'
import { clsx } from 'clsx'
import { Btn, Panel, PromptHeader, StatTile, StatusDot } from '@/components/ui'
import { ActivityFeed } from '@/components/features/ActivityFeed'
import { useDashboard, useHealth } from '@/api/queries'
import { ago, pad2 } from '@/utils/format'

export const Route = createFileRoute('/_app/dashboard')({ component: Dashboard })

function Dashboard() {
  const { data, isLoading } = useDashboard()
  const { data: health } = useHealth()
  const nav = useNavigate()
  const m = data?.metrics
  return (
    <div className="p-4 md:p-6">
      <PromptHeader title="control_center" subtitle="All workspaces at a glance. Project memory and context never leave their project." right={<Btn tone="primary" onClick={() => nav({ to: '/projects/new' })}>* INITIALIZE PROJECT</Btn>} />
      <div className="grid grid-cols-2 gap-2 md:grid-cols-5">
        <StatTile label="TOTAL PROJECTS" value={pad2(m?.total_projects ?? 0)} />
        <StatTile label="ACTIVE AGENTS" value={pad2(m?.active_agents ?? 0)} sub={m?.active_agents ? '● WORKING' : '○ idle'} />
        <StatTile label="ACTIVE RUNS" value={pad2(m?.active_runs ?? 0)} sub={m?.active_runs ? '◉ PROCESSING' : ''} />
        <StatTile label="WAITING APPROVALS" value={pad2(m?.waiting_approvals ?? 0)} tone={m?.waiting_approvals ? 'amber' : 'neon'} sub={m?.waiting_approvals ? 'awaiting human input' : ''} />
        <StatTile label="SYSTEM STATUS" value={health == null ? '…' : health.online ? 'ONLINE' : 'DEGRADED'} tone={health?.online === false ? 'amber' : 'neon'} sub={health ? `${health.ws_clients} live · ${health.run_workers} workers` : ''} />
      </div>
      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <Panel title="RECENT PROJECTS" right={<Link to="/projects" className="text-[11px] text-fg-3 hover:text-neon">all →</Link>}>
          {isLoading ? <div className="p-3 text-fg-3">loading…</div> : !data?.recent_projects.length ? (
            <div className="p-4 text-fg-3"><span className="text-neon">$</span> project list<br />No projects detected. <Link to="/projects/new" className="text-neon">Initialize a workspace</Link> to begin.</div>
          ) : (
            <div className="divide-y divide-line">
              {data.recent_projects.map((p) => (
                <Link key={p.id} to="/projects/$slug" params={{ slug: p.slug }} className="flex items-center justify-between px-3 py-2 hover:bg-bg-2">
                  <span className="truncate-1"><span className="mr-2 text-neon">{p.icon}</span><span className="text-fg-1">{p.slug}</span></span>
                  <span className="flex items-center gap-3 text-[11px] text-fg-3"><StatusDot status={p.status === 'active' ? 'running' : p.status} label={p.status.toUpperCase()} />{ago(p.last_activity_at)}</span>
                </Link>
              ))}
            </div>
          )}
        </Panel>
        <Panel title="APPROVAL QUEUE" right={data?.approval_queue.length ? <span className="text-[11px] text-warn">● {data.approval_queue.length} PENDING</span> : null}>
          {!data?.approval_queue.length ? <div className="p-4 text-fg-3">queue empty · no human input required</div> : (
            <div className="divide-y divide-line">
              {data.approval_queue.map((a) => (
                <Link key={a.id} to="/projects/$slug/approvals" params={{ slug: a.project_slug }} className="block px-3 py-2 hover:bg-bg-2">
                  <div className="flex items-center justify-between"><span className="text-warn">{a.id}</span><span className="text-[11px] text-fg-3">{a.project_slug} · {ago(a.requested_at)}</span></div>
                  <div className="truncate-1 text-[12px] text-fg-1 font-sans">{a.agent_name}: {a.action}</div>
                </Link>
              ))}
            </div>
          )}
        </Panel>
        <Panel title="LIVE ACTIVITY" className="lg:col-span-1">
          <ActivityFeed items={data?.activity ?? []} showProject height={320} />
        </Panel>
        <Panel title="SYSTEM HEALTH">
          <div className="grid grid-cols-2 gap-x-4 px-3 py-2 text-[12px]">
            {Object.entries(health?.checks ?? {}).map(([k, v]) => (
              <div key={k} className="flex items-center justify-between border-b border-line/60 py-1.5">
                <span className="text-fg-2">{k}</span>
                <span className={clsx(v.ok ? 'text-neon' : 'text-warn')}>{v.ok ? '● OK' : '● CHECK'}{'model' in v && v.model ? <span className="ml-1 text-fg-3">{String(v.model)}</span> : null}</span>
              </div>
            ))}
            {health && <>
              <div className="flex items-center justify-between py-1.5"><span className="text-fg-2">replica</span><span className="truncate-1 text-fg-3">{health.replica}</span></div>
              <div className="flex items-center justify-between py-1.5"><span className="text-fg-2">storage</span><span className="text-fg-3">{health.storage}</span></div>
            </>}
            {!health && <div className="col-span-2 py-2 text-fg-3">checking…</div>}
          </div>
          {health?.checks.llm && !health.checks.llm.ok && <div className="border-t border-warn/30 bg-warn/5 px-3 py-2 text-[11px] text-warn">{String(health.checks.llm.note)} <Link to="/settings" className="underline">open settings</Link></div>}
        </Panel>
      </div>
    </div>
  )
}
