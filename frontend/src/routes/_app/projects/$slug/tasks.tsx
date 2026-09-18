import { Link, createFileRoute } from '@tanstack/react-router'
import { useQueryClient } from '@tanstack/react-query'
import { useRef, useState } from 'react'
import { Btn, Input, Modal, PromptHeader, StatusDot, TermTable, TextArea, Toast, useToast } from '@/components/ui'
import { useActiveProject } from '@/components/layout/ProjectShell'
import { del, patch, post, upload } from '@/api/client'
import { qk, useTasks } from '@/api/queries'
import { ago } from '@/utils/format'

export const Route = createFileRoute('/_app/projects/$slug/tasks')({ component: Tasks })

function Tasks() {
  const p = useActiveProject()
  const { data: tasks } = useTasks(p.id)
  const qc = useQueryClient()
  const { toast, show, error } = useToast()
  const [open, setOpen] = useState(false)
  const [text, setText] = useState('')
  const [source, setSource] = useState('manual')
  const [author, setAuthor] = useState('')
  const [ext, setExt] = useState('')
  const [autoApprove, setAutoApprove] = useState(false)
  const [busy, setBusy] = useState<string | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)
  const refresh = () => { qc.invalidateQueries({ queryKey: qk.tasks(p.id) }); qc.invalidateQueries({ queryKey: qk.runs(p.id) }) }
  const autoRun = (p.config as { auto_run?: boolean }).auto_run !== false
  async function toggleAutoRun() {
    try { await patch(`/api/projects/${p.id}`, { config: { ...p.config, auto_run: !autoRun } }); show(`auto-run ${!autoRun ? 'on' : 'off'}`); qc.invalidateQueries({ queryKey: ['project'] }) } catch (e) { error(e) }
  }

  async function create() {
    setBusy('create')
    try { await post(`/api/projects/${p.id}/tasks`, { text, source, author, external_id: ext || null }); setOpen(false); setText(''); setExt(''); show('task created'); refresh() } catch (e) { error(e) } finally { setBusy(null) }
  }
  async function run(id: string) { setBusy(id); try { const r = await post<{ run_id: string }>(`/api/projects/${p.id}/tasks/${id}/run?auto_approve=${autoApprove}`); show(`queued ${r.run_id}`); refresh() } catch (e) { error(e) } finally { setBusy(null) } }
  async function runAll() { setBusy('all'); try { const r = await post<{ queued: number }>(`/api/projects/${p.id}/tasks/run-all?auto_approve=${autoApprove}`); show(`${r.queued} runs queued (processed in order)`); refresh() } catch (e) { error(e) } finally { setBusy(null) } }
  async function importFile(f: File) { const fd = new FormData(); fd.append('file', f); setBusy('import'); try { const r = await upload<{ created: number; skipped: number }>(`/api/projects/${p.id}/tasks/import`, fd); show(`imported ${r.created}, skipped ${r.skipped}`); refresh() } catch (e) { error(e) } finally { setBusy(null) } }
  async function sample() { setBusy('sample'); try { const r = await post<{ tasks: number }>(`/api/projects/${p.id}/sample-data?agents=false&knowledge_items=false`); show(r.tasks ? `${r.tasks} sample tasks loaded` : 'sample tasks already present'); refresh() } catch (e) { error(e) } finally { setBusy(null) } }
  async function remove(id: string) { try { await del(`/api/projects/${p.id}/tasks/${id}`); refresh() } catch (e) { error(e) } }
  async function cancel(t: { id: string; last_run_id: string | null }) {
    if (!t.last_run_id) return
    setBusy(t.id)
    try { await post(`/api/projects/${p.id}/runs/${t.last_run_id}/cancel`); show(`cancelling ${t.last_run_id}`); refresh() } catch (e) { error(e) } finally { setBusy(null) }
  }
  const isActive = (t: { status: string; last_run_id: string | null }) => (t.status === 'running' || t.status === 'queued') && !!t.last_run_id

  const list = tasks ?? []
  return (
    <div>
      <PromptHeader title="tasks" subtitle={autoRun ? 'Auto-run is on: every task that arrives (created here, imported, or pushed to the intake endpoint) starts immediately. Runs execute in order within the project.' : 'Auto-run is off: tasks wait until you press RUN or RUN ALL.'} right={<>
        <button onClick={toggleAutoRun} className={`flex items-center gap-1.5 border px-2 py-1 text-[10px] tracking-wider ${autoRun ? 'border-neon/60 text-neon glow-sm' : 'border-line text-fg-3'}`} title="Start a run automatically for every new task">{autoRun ? '● AUTO-RUN ON' : '○ AUTO-RUN OFF'}</button>
        <label className="flex items-center gap-1.5 text-[11px] text-fg-3" title="Skip the human gate for these runs"><input type="checkbox" className="accent-[#00ff66]" checked={autoApprove} onChange={(e) => setAutoApprove(e.target.checked)} />auto-approve</label>
        <input ref={fileRef} type="file" accept=".json,.csv" className="hidden" onChange={(e) => { if (e.target.files?.[0]) importFile(e.target.files[0]); e.target.value = '' }} />
        <Btn onClick={() => fileRef.current?.click()} loading={busy === 'import'} title="JSON array of items (id, source, author, text, metadata) or CSV with a text column">IMPORT FILE</Btn>
        <Btn onClick={sample} loading={busy === 'sample'}>* LOAD SAMPLE DATASET</Btn>
        <Btn onClick={runAll} loading={busy === 'all'} disabled={!list.some((t) => t.status === 'queued' || t.status === 'failed')}>RUN ALL QUEUED</Btn>
        <Btn tone="primary" onClick={() => setOpen(true)}>* NEW TASK</Btn>
      </>} />
      <div className="panel">
        <TermTable flexCol={3} cols={['ID', 'SOURCE', 'AUTHOR', 'TEXT', 'STATUS', 'RESULT', 'LAST RUN', 'ACTIONS']} keyOf={(i) => list[i].id} rowClass={(i) => isActive(list[i]) ? 'bg-neon/5' : ''}
          empty={<><span className="text-neon">$</span> task list — nothing queued. Create a task, import a file, or load the sample dataset.</>}
          rows={list.map((t) => [
            <span className="whitespace-nowrap text-fg-1">{t.external_id}</span>, <span className="whitespace-nowrap">{t.source}</span>, <span className="block max-w-[140px] truncate-1">{t.author || '—'}</span>,
            <span className="block truncate-1 text-fg-2 font-sans" title={t.text}>{t.text}</span>,
            <span className="whitespace-nowrap">{t.status === 'done' ? <StatusDot status="complete" /> : t.status === 'failed' ? <StatusDot status="error" /> : t.status === 'running' ? <StatusDot status={t.last_run_status === 'waiting_approval' ? 'waiting_approval' : 'running'} /> : t.last_run_id ? <StatusDot status="queued" /> : <StatusDot status="idle" label="NOT RUN" />}</span>,
            t.result ? <span className="whitespace-nowrap">{t.result.outcome}{t.result.ticket_id ? <span className="text-neon"> {t.result.ticket_id}</span> : t.result.duplicate_of ? <span className="text-neon"> ↔ {t.result.duplicate_of}</span> : ''}{t.result.severity ? <span className="text-fg-3"> · {t.result.severity}</span> : ''}</span> : <span className="text-fg-3">—</span>,
            t.last_run_id ? <Link to="/projects/$slug/runs/$runId" params={{ slug: p.slug, runId: t.last_run_id }} className="text-fg-2 hover:text-neon">{t.last_run_id}</Link> : <span className="text-fg-3">{ago(t.created_at)}</span>,
            <span className="flex gap-1 whitespace-nowrap">
              {isActive(t)
                ? <Btn size="sm" tone="danger" loading={busy === t.id} onClick={() => cancel(t)}>CANCEL</Btn>
                : <Btn size="sm" tone="primary" loading={busy === t.id} onClick={() => run(t.id)}>{t.status === 'done' || t.status === 'failed' ? 'RE-RUN' : 'RUN'}</Btn>}
              <Btn size="sm" tone="ghost" disabled={isActive(t)} title="delete task" onClick={() => remove(t.id)}>DEL</Btn>
            </span>,
          ])} />
      </div>
      <Modal open={open} onClose={() => setOpen(false)} title="new_task">
        <div className="space-y-3">
          <div className="grid gap-3 md:grid-cols-3"><Input label="id (optional)" value={ext} onChange={(e) => setExt(e.target.value)} placeholder="FB-016" /><Input label="source" value={source} onChange={(e) => setSource(e.target.value)} placeholder="discord" /><Input label="author" value={author} onChange={(e) => setAuthor(e.target.value)} placeholder="user_42" /></div>
          <TextArea label="feedback text" rows={6} value={text} onChange={(e) => setText(e.target.value)} placeholder="Paste the raw feedback exactly as the user wrote it." />
        </div>
        <div className="mt-4 flex justify-end gap-2"><Btn onClick={() => setOpen(false)}>cancel</Btn><Btn tone="primary" loading={busy === 'create'} disabled={!text.trim()} onClick={create}>[ CREATE TASK ]</Btn></div>
      </Modal>
      <Toast msg={toast?.msg ?? null} tone={toast?.tone} />
    </div>
  )
}
