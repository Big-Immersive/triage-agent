import { createFileRoute, redirect } from '@tanstack/react-router'
import { AuthForm } from '@/components/features/AuthForm'
import { getToken } from '@/stores/auth'

export const Route = createFileRoute('/register')({
  beforeLoad: () => { if (getToken()) throw redirect({ to: '/dashboard' }) },
  component: () => <AuthForm mode="register" />,
})
