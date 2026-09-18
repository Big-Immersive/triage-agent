import { clsx } from 'clsx'
import { X } from 'lucide-react'
import { useEffect, useId, useState, type ReactNode } from 'react'
import type { AgentStatus, RunStatus } from '@/api/types'
import { bar } from '@/utils/format'

/* ---------- primitives ---------- */
export function Panel({ className, children, title, right, glow }: { className?: string; children: ReactNode; title?: ReactNode; right?: ReactNode; glow?: boolean }) {
  return (
    <section className={clsx('panel', glow && 'glow-ring', className)}>
      {(title || right) && (
        <header className="flex items-center justify-between gap-3 border-b border-line px-3 py-2">
          <div className="label-2 truncate-1">{title}</div>
          <div className="flex items-center gap-2">{right}</div>
        </header>
      )}
      {children}
    </section>
  )
}

export function PromptHeader({ title, subtitle, right }: { title: string; subtitle?: string; right?: ReactNode }) {
  return (
    <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="prompt text-lg font-medium text-fg-1 glow-text">{title}</h1>
        {subtitle && <p className="mt-0.5 text-[12px] text-fg-2 font-sans">{subtitle}</p>}
      </div>
      {right && <div className="flex flex-wrap items-center gap-2">{right}</div>}
    </div>
  )
}

export function StatTile({ label, value, sub, tone = 'neon', className }: { label: string; value: ReactNode; sub?: ReactNode; tone?: 'neon' | 'amber' | 'muted' | 'red'; className?: string }) {
  const color = { neon: 'text-neon', amber: 'text-warn', muted: 'text-fg-2', red: 'text-danger' }[tone]
  return (
    <div className={clsx('panel px-3 py-2.5 min-w-0', className)}>
      <div className="label">{label}</div>
      <div className={clsx('mt-1 text-xl font-medium tabular-nums truncate-1', color, tone === 'neon' && 'glow-text')}>{value}</div>
      {sub && <div className="mt-0.5 text-[11px] text-fg-3 truncate-1">{sub}</div>}
    </div>
  )
}

export const AGENT_STATUS_LABEL: Record<AgentStatus, string> = {
  idle: 'IDLE', thinking: 'THINKING', running: 'RUNNING', tool_call: 'TOOL CALL', waiting: 'WAITING', human_input: 'HUMAN INPUT', complete: 'COMPLETE', error: 'ERROR', disabled: 'DISABLED',
}
const ACTIVE: AgentStatus[] = ['thinking', 'running', 'tool_call', 'waiting', 'human_input']

export function StatusDot({ status, label, size = 'sm', className }: { status: AgentStatus | RunStatus | string; label?: string; size?: 'sm' | 'md'; className?: string }) {
  const s = status as string
  const isAmber = s === 'human_input' || s === 'waiting_approval' || s === 'pending'
  const isRed = s === 'error' || s === 'failed' || s === 'rejected'
  const isMuted = s === 'idle' || s === 'disabled' || s === 'cancelled' || s === 'expired' || s === 'not_connected' || s === 'draft' || s === 'archived'
  const isActive = ACTIVE.includes(s as AgentStatus) || s === 'running' || s === 'queued' || s === 'indexing'
  const hollow = s === 'waiting' || s === 'queued' || s === 'not_connected' || s === 'disabled'
  const color = isAmber ? 'text-warn' : isRed ? 'text-danger' : isMuted ? 'text-fg-3' : 'text-neon'
  const glow = isActive && !isMuted ? (isAmber ? 'glow-amber' : 'glow-sm') : ''
  const text = label ?? (AGENT_STATUS_LABEL[s as AgentStatus] ?? s.replace(/_/g, ' ').toUpperCase())
  return (
    <span className={clsx('inline-flex items-center gap-1.5 whitespace-nowrap', color, size === 'md' ? 'text-[12px]' : 'text-[11px]', className)}>
      <span className={clsx('inline-block rounded-full', size === 'md' ? 'h-2 w-2' : 'h-1.5 w-1.5', hollow ? 'border border-current' : 'bg-current', glow, isActive && 'anim-pulse')} />
      <span className="tracking-wider">{text}</span>
    </span>
  )
}

export function ThinkingBars() {
  return <span className="thinking-bars inline-flex items-end" aria-label="thinking"><span /><span /><span /></span>
}

export function ProgressBar({ pct, width = 10, indeterminate }: { pct: number; width?: number; indeterminate?: boolean }) {
  return (
    <span className={clsx('progress-track inline-block tabular-nums text-neon', indeterminate && 'indeterminate')}>
      {bar(pct, width)} <span className="text-fg-2">{Math.round(pct)}%</span>
    </span>
  )
}

type BtnProps = React.ButtonHTMLAttributes<HTMLButtonElement> & { tone?: 'primary' | 'ghost' | 'danger' | 'amber'; size?: 'sm' | 'md'; loading?: boolean }
export function Btn({ tone = 'ghost', size = 'md', loading, className, children, disabled, ...rest }: BtnProps) {
  const base = 'inline-flex items-center justify-center gap-1.5 whitespace-nowrap border font-medium tracking-wider uppercase transition-colors disabled:opacity-40 disabled:cursor-not-allowed'
  const sz = size === 'sm' ? 'h-7 px-2.5 text-[10px]' : 'h-8 px-3 text-[11px]'
  const tones = {
    primary: 'border-neon/60 bg-neon/10 text-neon hover:bg-neon/20 glow-sm',
    ghost: 'border-line text-fg-2 hover:border-line-strong hover:text-fg-1',
    danger: 'border-danger/40 text-danger hover:bg-danger/10',
    amber: 'border-warn/50 bg-warn/10 text-warn hover:bg-warn/20',
  }[tone]
  return <button className={clsx(base, sz, tones, className)} disabled={disabled || loading} {...rest}>{loading ? <span className="anim-blink">…</span> : children}</button>
}

export function Input({ className, label, hint, ...rest }: React.InputHTMLAttributes<HTMLInputElement> & { label?: string; hint?: string }) {
  const id = useId()
  return (
    <label htmlFor={id} className="block">
      {label && <span className="label mb-1 block">{label}</span>}
      <input id={id} className={clsx('h-8 w-full border border-line bg-bg-0 px-2.5 text-[12px] text-fg-1 placeholder:text-fg-3 focus:border-line-strong', className)} {...rest} />
      {hint && <span className="mt-1 block text-[11px] text-fg-3 font-sans">{hint}</span>}
    </label>
  )
}

export function TextArea({ className, label, hint, ...rest }: React.TextareaHTMLAttributes<HTMLTextAreaElement> & { label?: string; hint?: string }) {
  const id = useId()
  return (
    <label htmlFor={id} className="block">
      {label && <span className="label mb-1 block">{label}</span>}
      <textarea id={id} className={clsx('w-full border border-line bg-bg-0 px-2.5 py-2 text-[12px] leading-relaxed text-fg-1 placeholder:text-fg-3 focus:border-line-strong', className)} {...rest} />
      {hint && <span className="mt-1 block text-[11px] text-fg-3 font-sans">{hint}</span>}
    </label>
  )
}

export function Select({ className, label, children, ...rest }: React.SelectHTMLAttributes<HTMLSelectElement> & { label?: string }) {
  const id = useId()
  return (
    <label htmlFor={id} className="block">
      {label && <span className="label mb-1 block">{label}</span>}
      <select id={id} className={clsx('h-8 w-full border border-line bg-bg-0 px-2 text-[12px] text-fg-1 focus:border-line-strong', className)} {...rest}>{children}</select>
    </label>
  )
}

export function KeyField({ label, masked, has, onChange, value, hint }: { label: string; masked: string | null; has: boolean; value: string; onChange: (v: string) => void; hint?: string }) {
  const [show, setShow] = useState(false)
  return (
    <div>
      <div className="mb-1 flex items-center justify-between"><span className="label">{label}</span>{has && <span className="text-[10px] text-neon">● SAVED {masked}</span>}</div>
      <div className="flex gap-2">
        <input type={show ? 'text' : 'password'} value={value} onChange={(e) => onChange(e.target.value)} placeholder={has ? 'leave blank to keep the saved key' : 'paste key'} autoComplete="off" spellCheck={false}
          className="h-8 w-full border border-line bg-bg-0 px-2.5 text-[12px] text-fg-1 placeholder:text-fg-3 focus:border-line-strong" />
        <Btn size="sm" type="button" onClick={() => setShow((s) => !s)}>{show ? 'hide' : 'show'}</Btn>
      </div>
      {hint && <span className="mt-1 block text-[11px] text-fg-3 font-sans">{hint}</span>}
    </div>
  )
}

export function Kbd({ children }: { children: ReactNode }) {
  return <kbd className="border border-line bg-bg-2 px-1 text-[10px] text-fg-2">{children}</kbd>
}

export function Empty({ command, lines, action }: { command: string; lines: string[]; action?: ReactNode }) {
  return (
    <div className="panel mx-auto max-w-lg px-6 py-8 text-center anim-fade">
      <div className="text-fg-3"><span className="text-neon">$</span> {command}</div>
      <div className="mt-3 space-y-0.5 text-fg-2">{lines.map((l) => <div key={l}>{l}</div>)}</div>
      {action && <div className="mt-5 flex justify-center">{action}</div>}
    </div>
  )
}

export function Modal({ open, onClose, title, children, wide }: { open: boolean; onClose: () => void; title: ReactNode; children: ReactNode; wide?: boolean }) {
  useEffect(() => {
    if (!open) return
    const h = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', h)
    return () => window.removeEventListener('keydown', h)
  }, [open, onClose])
  if (!open) return null
  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/70 p-4 pt-[8vh]" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose() }}>
      <div role="dialog" aria-modal className={clsx('panel glow-ring w-full anim-fade', wide ? 'max-w-4xl' : 'max-w-xl')}>
        <header className="flex items-center justify-between border-b border-line px-4 py-2.5">
          <div className="prompt text-fg-1">{title}</div>
          <button onClick={onClose} className="text-fg-3 hover:text-fg-1" aria-label="close"><X size={14} /></button>
        </header>
        <div className="p-4">{children}</div>
      </div>
    </div>
  )
}

export function ConfirmModal({ open, onClose, onConfirm, title, body, confirmText = 'CONFIRM', typed, danger, loading }: { open: boolean; onClose: () => void; onConfirm: () => void; title: string; body: ReactNode; confirmText?: string; typed?: string; danger?: boolean; loading?: boolean }) {
  const [v, setV] = useState('')
  useEffect(() => { if (!open) setV('') }, [open])
  return (
    <Modal open={open} onClose={onClose} title={title}>
      <div className="space-y-3 text-fg-2 font-sans text-[13px]">{body}</div>
      {typed && <div className="mt-3"><Input label={`type ${typed} to confirm`} value={v} onChange={(e) => setV(e.target.value)} autoFocus /></div>}
      <div className="mt-4 flex justify-end gap-2">
        <Btn onClick={onClose}>cancel</Btn>
        <Btn tone={danger ? 'danger' : 'primary'} loading={loading} disabled={!!typed && v !== typed} onClick={onConfirm}>{confirmText}</Btn>
      </div>
    </Modal>
  )
}

export function Tabs<T extends string>({ value, onChange, options, counts }: { value: T; onChange: (v: T) => void; options: readonly T[]; counts?: Partial<Record<T, number>> }) {
  return (
    <div className="flex flex-wrap gap-1 border-b border-line">
      {options.map((o) => (
        <button key={o} onClick={() => onChange(o)} className={clsx('-mb-px border-b px-2.5 py-1.5 text-[11px] tracking-wider', value === o ? 'border-neon text-neon' : 'border-transparent text-fg-3 hover:text-fg-2')}>
          {o}{counts?.[o] != null && <span className="ml-1 text-fg-3">{counts[o]}</span>}
        </button>
      ))}
    </div>
  )
}

/** Table that collapses to stacked cards under md. `cols` are header labels; each row is an array of cells. */
/** `flexCol` = index of the column that absorbs the remaining width and truncates (its cells should render a `truncate-1` block). Other columns stay at their content width. */
export function TermTable({ cols, rows, onRowClick, empty, rowClass, keyOf, flexCol }: { cols: string[]; rows: ReactNode[][]; onRowClick?: (i: number) => void; empty?: ReactNode; rowClass?: (i: number) => string; keyOf?: (i: number) => string; flexCol?: number }) {
  if (!rows.length) return <div className="px-3 py-6 text-center text-fg-3">{empty ?? 'no records'}</div>
  return (
    <>
      <div className="hidden overflow-x-auto md:block">
      <table className="w-full border-collapse">
        <thead><tr className="border-b border-line">{cols.map((c, j) => <th key={c} className={clsx('label whitespace-nowrap px-3 py-2 text-left font-normal', j === flexCol && 'w-full')}>{c}</th>)}</tr></thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={keyOf?.(i) ?? i} onClick={() => onRowClick?.(i)} className={clsx('border-b border-line/60 align-top', onRowClick && 'cursor-pointer hover:bg-bg-2', rowClass?.(i))}>
              {r.map((c, j) => <td key={j} className={clsx('px-3 py-2 text-[12px]', j === flexCol ? 'w-full max-w-0' : 'whitespace-nowrap')}>{c}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
      </div>
      <div className="space-y-2 md:hidden">
        {rows.map((r, i) => (
          <div key={keyOf?.(i) ?? i} onClick={() => onRowClick?.(i)} className={clsx('panel-2 grid grid-cols-2 gap-x-3 gap-y-1 p-3', onRowClick && 'cursor-pointer', rowClass?.(i))}>
            {r.map((c, j) => <div key={j} className="min-w-0"><div className="label">{cols[j]}</div><div className="text-[12px] break-words">{c}</div></div>)}
          </div>
        ))}
      </div>
    </>
  )
}

export function Field({ k, v, mono = true }: { k: string; v: ReactNode; mono?: boolean }) {
  return (
    <div className="grid grid-cols-[110px_1fr] gap-2 py-0.5 text-[12px]">
      <div className="label pt-0.5">{k}</div>
      <div className={clsx('min-w-0 break-words text-fg-1', !mono && 'font-sans')}>{v}</div>
    </div>
  )
}

export function Toast({ msg, tone = 'neon' }: { msg: string | null; tone?: 'neon' | 'red' | 'amber' }) {
  if (!msg) return null
  const c = { neon: 'border-neon/50 text-neon', red: 'border-danger/50 text-danger', amber: 'border-warn/50 text-warn' }[tone]
  return <div className={clsx('fixed bottom-4 right-4 z-50 panel px-3 py-2 text-[12px] anim-fade', c)}>{msg}</div>
}

export function useToast() {
  const [t, setT] = useState<{ msg: string; tone: 'neon' | 'red' | 'amber' } | null>(null)
  useEffect(() => { if (!t) return; const id = setTimeout(() => setT(null), 3500); return () => clearTimeout(id) }, [t])
  return { toast: t, show: (msg: string, tone: 'neon' | 'red' | 'amber' = 'neon') => setT({ msg, tone }), error: (e: unknown) => setT({ msg: e instanceof Error ? e.message : String(e), tone: 'red' }) }
}
