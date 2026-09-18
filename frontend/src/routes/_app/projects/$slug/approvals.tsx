import { createFileRoute } from '@tanstack/react-router'
import { useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { PromptHeader, Tabs, Toast, useToast } from '@/components/ui'
import { ApprovalCard } from '@/components/features/ApprovalCard'
import { useActiveProject } from '@/components/layout/ProjectShell'
import { post } from '@/api/client'
import { qk, useApprovals } from '@/api/queries'

export const Route = createFileRoute('/_app/projects/$slug/approvals')({ component: Approvals })
const TABS = ['PENDING', 'RESOLVED'] as const

function Approvals() {
  const p = useActiveProject()
  const { data } = useApprovals(p.id)
  const qc = useQueryClient()
  const { toast, show, error } = useToast()
  const [tab, setTab] = useState<(typeof TABS)[number]>('PENDING')
  const [busy, setBusy] = useState<string | null>(null)
  const list = (data ?? []).filter((a) => tab === 'PENDING' ? a.status === 'pending' : a.status !== 'pending')
  async function decide(id: string, action: 'approve' | 'reject' | 'modify', severity?: string) {
    setBusy(id)
    try { await post(`/api/projects/${p.id}/approvals/${id}/${action}`, action === 'modify' ? { severity } : undefined); show(`${id} ${action}d`); qc.invalidateQueries({ queryKey: qk.approvals(p.id) }); qc.invalidateQueries({ queryKey: qk.project(p.id) }) } catch (e) { error(e) } finally { setBusy(null) }
  }
  const pending = (data ?? []).filter((a) => a.status === 'pending').length
  return (
    <div>
      <PromptHeader title="human_approval_queue" subtitle="Actions the agents are not allowed to take alone. A run pauses here until you decide." right={pending ? <span className="text-[11px] text-warn glow-amber px-1">● {pending} AWAITING INPUT</span> : null} />
      <Tabs value={tab} onChange={setTab} options={TABS} counts={{ PENDING: pending, RESOLVED: (data?.length ?? 0) - pending }} />
      <div className="mt-3 grid gap-3 md:grid-cols-2">
        {list.map((a) => <ApprovalCard key={a.id} a={a} slug={p.slug} onDecide={decide} busy={busy === a.id} />)}
        {!list.length && <div className="panel px-4 py-8 text-center text-fg-3 md:col-span-2"><span className="text-neon">$</span> approvals --{tab.toLowerCase()}<br />{tab === 'PENDING' ? 'Queue empty. No human input required.' : 'Nothing resolved yet.'}</div>}
      </div>
      <Toast msg={toast?.msg ?? null} tone={toast?.tone} />
    </div>
  )
}
