import { createFileRoute, redirect } from '@tanstack/react-router'
import { AuthForm } from '@/components/features/AuthForm'
import { getToken } from '@/stores/auth'

export const Route = createFileRoute('/login')({
  beforeLoad: () => { if (getToken()) throw redirect({ to: '/dashboard' }) },
  component: () => <AuthForm mode="login" />,
})
