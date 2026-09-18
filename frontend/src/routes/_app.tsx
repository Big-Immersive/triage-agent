import { createFileRoute, redirect } from '@tanstack/react-router'
import { AppShell } from '@/components/layout/AppShell'
import { getToken } from '@/stores/auth'

export const Route = createFileRoute('/_app')({
  beforeLoad: ({ location }) => { if (!getToken()) throw redirect({ to: '/login', search: { redirect: location.href } }) },
  component: AppShell,
})
