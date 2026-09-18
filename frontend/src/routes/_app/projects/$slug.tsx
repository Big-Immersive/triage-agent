import { createFileRoute } from '@tanstack/react-router'
import { ProjectShell } from '@/components/layout/ProjectShell'

export const Route = createFileRoute('/_app/projects/$slug')({
  component: () => {
    const { slug } = Route.useParams()
    return <ProjectShell slug={slug} />
  },
})
