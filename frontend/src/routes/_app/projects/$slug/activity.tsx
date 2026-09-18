import { createFileRoute } from '@tanstack/react-router'
import { useState } from 'react'
import { Panel, PromptHeader, Tabs } from '@/components/ui'
import { ActivityFeed } from '@/components/features/ActivityFeed'
import { useActiveProject } from '@/components/layout/ProjectShell'
import { useActivity } from '@/api/queries'

export const Route = createFileRoute('/_app/projects/$slug/activity')({ component: ActivityPage })
const FILTERS = ['ALL', 'AGENTS', 'RUNS', 'MEMORY', 'FILES', 'APPROVALS', 'SYSTEM'] as const

function ActivityPage() {
  const p = useActiveProject()
  const [f, setF] = useState<(typeof FILTERS)[number]>('ALL')
  const { data } = useActivity(p.id, f)
  return (
    <div>
      <PromptHeader title="system_activity" subtitle="Everything that happened in this project, newest first." right={<span className="text-[10px] text-neon anim-pulse">● LIVE</span>} />
      <Tabs value={f} onChange={setF} options={FILTERS} />
      <Panel className="mt-3"><ActivityFeed items={data ?? []} slug={p.slug} height={560} /></Panel>
    </div>
  )
}
