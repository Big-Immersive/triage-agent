import { Link, createFileRoute } from '@tanstack/react-router'
import { useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { clsx } from 'clsx'
import { Btn, ConfirmModal, Field, Modal, PromptHeader, Select, TextArea, Toast, useToast } from '@/components/ui'
import { useActiveProject } from '@/components/layout/ProjectShell'
import { del, patch, post } from '@/api/client'
import { useMemories } from '@/api/queries'
import { dateStamp } from '@/utils/format'
import { MEMORY_TYPES, type Memory, type MemoryType } from '@/api/types'

export const Route = createFileRoute('/_app/projects/$slug/memory')({ component: MemoryPage })

function MemoryPage() {
  const p = useActiveProject()
  const [type, setType] = useState<'ALL' | MemoryType>('ALL')
  const [q, setQ] = useState('')
  const { data } = useMemories(p.id, type, q)
  const qc = useQueryClient()
  const { toast, show, error } = useToast()
  const [edit, setEdit] = useState<Partial<Memory> | null>(null)
  const [remove, setRemove] = useState<Memory | null>(null)
  const [busy, setBusy] = useState(false)
  const refresh = () => qc.invalidateQueries({ queryKey: ['memories', p.id] })

  async function save() {
    if (!edit?.content?.trim()) return
    setBusy(true)
    try {
      if (edit.id) await patch(`/api/projects/${p.id}/memories/${edit.id}`, { type: edit.type, content: edit.content, pinned: edit.pinned })
      else await post(`/api/projects/${p.id}/memories`, { type: edit.type ?? 'CUSTOM_MEMORY', content: edit.content, pinned: !!edit.pinned, source: 'user' })
      show('memory saved'); setEdit(null); refresh()
    } catch (e) { error(e) } finally { setBusy(false) }
  }
  async function pin(m: Memory) { try { await post(`/api/projects/${p.id}/memories/${m.id}/pin`); refresh() } catch (e) { error(e) } }
  async function doRemove() { if (!remove) return; setBusy(true); try { await del(`/api/projects/${p.id}/memories/${remove.id}`); setRemove(null); refresh() } catch (e) { error(e) } finally { setBusy(false) } }

  return (
    <div>
      <PromptHeader title="memory" subtitle="Persistent project intelligence. Pinned PROJECT_CONTEXT entries are injected into every agent run." right={<Btn tone="primary" onClick={() => setEdit({ type: 'CUSTOM_MEMORY', content: '', pinned: false })}>* ADD MEMORY</Btn>} />
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <div className="flex items-center border border-line bg-bg-0 px-2"><span className="text-neon">$</span><input value={q} onChange={(e) => setQ(e.target.value)} placeholder="search_memory" className="h-8 w-56 bg-transparent px-2 text-[12px] text-fg-1 placeholder:text-fg-3 outline-none" /></div>
        <div className="flex flex-wrap gap-1">
          {(['ALL', ...MEMORY_TYPES] as const).map((t) => <button key={t} onClick={() => setType(t)} className={clsx('border px-2 py-1 text-[10px] tracking-wider', type === t ? 'border-neon/60 text-neon bg-neon/10' : 'border-line text-fg-3 hover:text-fg-2')}>{t}</button>)}
        </div>
      </div>
      {!data?.length ? <div className="panel px-4 py-8 text-center text-fg-3"><span className="text-neon">$</span> search_memory {q && `"${q}"`}<br />No memory records{type !== 'ALL' && ` of type ${type}`}. Runs write memories automatically; you can add your own.</div> : (
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {data.map((m) => (
            <div key={m.id} className={clsx('panel hover-neon p-3 anim-fade', m.pinned && 'border-neon/40')}>
              <div className="mb-1 flex items-center justify-between"><span className="text-fg-1">{m.id}</span>{m.pinned && <span className="text-[10px] text-neon">📌 PINNED</span>}</div>
              <Field k="TYPE" v={<span className="text-neon-2">{m.type}</span>} />
              <Field k="SOURCE" v={m.source} />
              <Field k="CREATED" v={dateStamp(m.created_at)} />
              <Field k="CONTENT" v={<span className="whitespace-pre-wrap">{m.content}</span>} mono={false} />
              {m.related_run_id && <Field k="RELATED RUN" v={<Link to="/projects/$slug/runs/$runId" params={{ slug: p.slug, runId: m.related_run_id }} className="text-neon hover:underline">{m.related_run_id}</Link>} />}
              <div className="mt-2 flex gap-1 border-t border-line pt-2"><Btn size="sm" onClick={() => setEdit(m)}>EDIT</Btn><Btn size="sm" onClick={() => pin(m)}>{m.pinned ? 'UNPIN' : 'PIN'}</Btn><Btn size="sm" tone="danger" onClick={() => setRemove(m)}>DELETE</Btn></div>
            </div>
          ))}
        </div>
      )}
      <Modal open={!!edit} onClose={() => setEdit(null)} title={edit?.id ? `edit ${edit.id}` : 'add_memory'}>
        {edit && <div className="space-y-3">
          <Select label="type" value={edit.type} onChange={(e) => setEdit({ ...edit, type: e.target.value as MemoryType })}>{MEMORY_TYPES.map((t) => <option key={t}>{t}</option>)}</Select>
          <TextArea label="content" rows={6} value={edit.content ?? ''} onChange={(e) => setEdit({ ...edit, content: e.target.value })} autoFocus />
          <label className="flex items-center gap-2 text-[11px] text-fg-2"><input type="checkbox" className="accent-[#00ff66]" checked={!!edit.pinned} onChange={(e) => setEdit({ ...edit, pinned: e.target.checked })} />pin (PROJECT_CONTEXT pins are sent to every agent)</label>
          <div className="flex justify-end gap-2"><Btn onClick={() => setEdit(null)}>cancel</Btn><Btn tone="primary" loading={busy} onClick={save}>[ SAVE ]</Btn></div>
        </div>}
      </Modal>
      <ConfirmModal open={!!remove} onClose={() => setRemove(null)} onConfirm={doRemove} title="delete_memory" danger loading={busy} body={<p>Delete <b className="text-fg-1">{remove?.id}</b>?</p>} />
      <Toast msg={toast?.msg ?? null} tone={toast?.tone} />
    </div>
  )
}
