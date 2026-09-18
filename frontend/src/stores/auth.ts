import { create } from 'zustand'

export interface User { id: string; email: string; name: string; created_at: string }

const KEY = 'triage.token'
const USER = 'triage.user'

function read<T>(k: string): T | null {
  try { const v = localStorage.getItem(k); return v ? (JSON.parse(v) as T) : null } catch { return null }
}
function write(k: string, v: unknown) {
  try { v == null ? localStorage.removeItem(k) : localStorage.setItem(k, JSON.stringify(v)) } catch { /* private mode */ }
}

interface AuthState {
  token: string | null
  user: User | null
  setSession: (token: string, user: User) => void
  clear: () => void
}

export const useAuth = create<AuthState>((set) => ({
  token: read<string>(KEY),
  user: read<User>(USER),
  setSession: (token, user) => { write(KEY, token); write(USER, user); set({ token, user }) },
  clear: () => { write(KEY, null); write(USER, null); set({ token: null, user: null }) },
}))

export const getToken = () => useAuth.getState().token
