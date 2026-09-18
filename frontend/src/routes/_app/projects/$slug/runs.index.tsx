import { createFileRoute, useNavigate } from '@tanstack/react-router'
import { useState } from 'react'
import { PromptHeader, StatusDot, Tabs, TermTable } from '@/components/ui'
import { useActiveProject } from '@/components/layout/ProjectShell'
import { useRuns } from '@/api/queries'
import { duration, hhmm, pad2 } from '@/utils/format'

export const Route = createFileRoute('/_app/projects/$slug/runs/')({ component: Runs })
const FILTERS = ['ALL', 'ACTIVE', 'COMPLETE', 'FAILED'] as const

function Runs() {
  const p = useActiveProject()
  const { data } = useRuns(p.id)
  const nav = useNavigate()
  const [f, setF] = useState<(typeof FILTERS)[number]>('ALL')
  const runs = (data ?? []).filter((r) => f === 'ALL' || (f === 'ACTIVE' && ['queued', 'running', 'waiting_approval'].includes(r.status)) || (f === 'COMPLETE' && r.status === 'complete') || (f === 'FAILED' && ['error', 'cancelled'].includes(r.status)))
  return (
    <div>
      <PromptHeader title="execution_runs" subtitle="Every workflow execution in this project. Click a run to open its console." />
      <Tabs value={f} onChange={setF} options={FILTERS} />
      <div className="panel mt-3">
        <TermTable flexCol={3} cols={['RUN_ID', 'TASK', 'STARTING_AGENT', 'CURRENT_AGENT', 'STATUS', 'STARTED', 'DURATION', 'TOOL_CALLS', 'HANDOFFS', 'APPROVAL']}
          keyOf={(i) => runs[i].id} onRowClick={(i) => nav({ to: '/projects/$slug/runs/$runId', params: { slug: p.slug, runId: runs[i].id } })}
          rowClass={(i) => runs[i].status === 'waiting_approval' ? 'bg-warn/5' : ''}
          empty={<><span className="text-neon">$</span> run list — no runs yet</>}
          rows={runs.map((r) => [
            <span className="text-fg-1">{r.id}</span>, r.task_external_id ?? '—', r.starting_agent ?? '—', <span className={r.status === 'running' ? 'text-neon' : ''}>{r.current_agent ?? '—'}</span>,
            <StatusDot status={r.status} />, hhmm(r.started_at), <span className="tabular-nums">{duration(r.duration_ms, ['running', 'waiting_approval'].includes(r.status) ? r.started_at : undefined)}</span>,
            pad2(r.tool_call_count), pad2(r.handoff_count), <span className={r.approval_state === 'pending' ? 'text-warn' : r.approval_state === 'none' ? 'text-fg-3' : ''}>{r.approval_state.toUpperCase()}</span>,
          ])} />
      </div>
    </div>
  )
}
