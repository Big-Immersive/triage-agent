import { Link, useNavigate } from '@tanstack/react-router'
import { useState, type FormEvent } from 'react'
import { Btn, Input } from '@/components/ui'
import { post } from '@/api/client'
import { useAuth, type User } from '@/stores/auth'

export function AuthForm({ mode }: { mode: 'login' | 'register' }) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [name, setName] = useState('')
  const [err, setErr] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const nav = useNavigate()
  const setSession = useAuth((s) => s.setSession)

  async function submit(e: FormEvent) {
    e.preventDefault(); setErr(null); setBusy(true)
    try {
      const r = await post<{ user: User; token: string }>(`/api/auth/${mode}`, mode === 'login' ? { email, password } : { email, password, name })
      setSession(r.token, r.user)
      nav({ to: mode === 'register' ? '/projects' : '/dashboard' })
    } catch (e) { setErr(e instanceof Error ? e.message : 'failed') } finally { setBusy(false) }
  }

  return (
    <div className="canvas-grid flex min-h-full items-center justify-center p-4">
      <form onSubmit={submit} className="panel glow-ring w-full max-w-sm p-6 anim-fade">
        <pre className="text-neon glow-text text-[11px] leading-[11px]">{'▄▀█\n█▀█'}</pre>
        <div className="mt-2 text-[14px] tracking-wider text-fg-1">triage<span className="text-neon">.</span>agents</div>
        <div className="mt-1 text-[10px] tracking-widest text-neon">● SYSTEM ONLINE</div>
        <div className="mt-5 prompt text-fg-1">{mode === 'login' ? 'authenticate' : 'create_account'}</div>
        <div className="mt-3 space-y-3">
          {mode === 'register' && <Input label="name" value={name} onChange={(e) => setName(e.target.value)} placeholder="Ada" autoComplete="name" />}
          <Input label="email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@company.com" autoComplete="email" />
          <Input label="password" type="password" required minLength={8} value={password} onChange={(e) => setPassword(e.target.value)} placeholder="••••••••" autoComplete={mode === 'login' ? 'current-password' : 'new-password'} hint={mode === 'register' ? 'at least 8 characters' : undefined} />
        </div>
        {err && <div className="mt-3 border border-danger/40 bg-danger/10 px-2 py-1.5 text-[11px] text-danger">✖ {err}</div>}
        <Btn tone="primary" type="submit" loading={busy} className="mt-5 w-full">[ {mode === 'login' ? 'AUTHENTICATE' : 'INITIALIZE ACCOUNT'} ]</Btn>
        <div className="mt-4 text-center text-[11px] text-fg-3">
          {mode === 'login' ? <>no account? <Link to="/register" className="text-neon">register</Link></> : <>have an account? <Link to="/login" className="text-neon">log in</Link></>}
        </div>
      </form>
    </div>
  )
}
