import { createFileRoute } from '@tanstack/react-router'
import { Panel, PromptHeader } from '@/components/ui'
import { ActivityFeed } from '@/components/features/ActivityFeed'
import { useGlobalActivity } from '@/api/queries'

export const Route = createFileRoute('/_app/activity')({ component: GlobalActivity })

function GlobalActivity() {
  const { data } = useGlobalActivity()
  return (
    <div className="p-4 md:p-6">
      <PromptHeader title="global_activity" subtitle="Headlines across all of your projects. Open a project for its full feed." right={<span className="text-[10px] text-neon anim-pulse">● LIVE</span>} />
      <Panel><ActivityFeed items={data ?? []} showProject height={600} /></Panel>
    </div>
  )
}
