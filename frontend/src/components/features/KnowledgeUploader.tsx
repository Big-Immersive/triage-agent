import { useRef, useState } from 'react'
import { clsx } from 'clsx'
import { Btn, Input, ProgressBar, Select, StatusDot, TextArea, useToast, Toast } from '@/components/ui'
import { post, upload } from '@/api/client'
import { useQueryClient } from '@tanstack/react-query'
import { qk, useKnowledge, useProjectEvents } from '@/api/queries'
import { ago, bytes } from '@/utils/format'
import type { KnowledgeItem } from '@/api/types'

export function KnowledgeList({ projectId, items, onDelete, onReindex }: { projectId: string; items: KnowledgeItem[]; onDelete?: (k: KnowledgeItem) => void; onReindex?: (k: KnowledgeItem) => void }) {
  if (!items.length) return <div className="px-3 py-4 text-fg-3">no knowledge items</div>
  return (
    <div className="divide-y divide-line">
      {items.map((k) => (
        <div key={k.id} className="grid grid-cols-[1fr_auto] items-center gap-3 px-3 py-2 text-[12px] md:grid-cols-[minmax(0,2fr)_130px_90px_150px_140px_auto]">
          <div className="min-w-0"><div className="truncate-1 text-fg-1">{k.name}</div><div className="text-[10px] text-fg-3 md:hidden">TYPE {k.kind} · {bytes(k.size_bytes)}</div></div>
          <div className="hidden whitespace-nowrap md:block"><span className="label">TYPE </span><span className="text-fg-2">{k.kind}</span></div>
          <div className="hidden whitespace-nowrap md:block"><span className="label">SIZE </span><span className="text-fg-2">{bytes(k.size_bytes)}</span></div>
          <div className="whitespace-nowrap">{k.status === 'indexing' ? <span className="text-[11px]">INDEXING <ProgressBar pct={k.progress} width={9} indeterminate={k.progress === 0} /></span> : <StatusDot status={k.status === 'ready' ? 'running' : k.status} label={k.status === 'ready' ? 'READY' : 'FAILED'} />}</div>
          <div className="hidden whitespace-nowrap text-fg-3 md:block">{k.indexed_at ? <><span className="label">INDEXED </span>{ago(k.indexed_at)}</> : k.error ? <span className="text-danger" title={k.error}>{k.error.slice(0, 40)}</span> : ''}</div>
          <div className="flex gap-1">{onReindex && <Btn size="sm" onClick={() => onReindex(k)} disabled={k.status === 'indexing'}>reindex</Btn>}{onDelete && <Btn size="sm" tone="danger" onClick={() => onDelete(k)}>delete</Btn>}</div>
          <div className="col-span-2 hidden" data-project={projectId} />
        </div>
      ))}
    </div>
  )
}

export function KnowledgeUploader({ projectId, compact }: { projectId: string; compact?: boolean }) {
  const qc = useQueryClient()
  const { data: items } = useKnowledge(projectId)
  useProjectEvents(projectId)   // live progress even outside the project shell (create wizard)
  const fileRef = useRef<HTMLInputElement>(null)
  const [drag, setDrag] = useState(false)
  const [kind, setKind] = useState('auto')
  const [url, setUrl] = useState('')
  const [noteName, setNoteName] = useState('')
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState<string | null>(null)
  const { toast, show, error } = useToast()
  const refresh = () => qc.invalidateQueries({ queryKey: qk.knowledge(projectId) })

  async function sendFiles(files: FileList | File[]) {
    const fd = new FormData()
    Array.from(files).forEach((f) => fd.append('files', f))
    fd.append('kind', kind)
    setBusy('upload')
    try { await upload(`/api/projects/${projectId}/knowledge/upload`, fd); show(`${files.length} file(s) queued for indexing`); refresh() } catch (e) { error(e) } finally { setBusy(null) }
  }
  async function addUrl() {
    if (!url) return
    setBusy('url')
    try { await post(`/api/projects/${projectId}/knowledge/url`, { url }); setUrl(''); show('URL fetched, indexing…'); refresh() } catch (e) { error(e) } finally { setBusy(null) }
  }
  async function addText() {
    if (!note.trim()) return
    setBusy('text')
    try { await post(`/api/projects/${projectId}/knowledge/text`, { name: noteName || 'note', text: note, kind: 'note' }); setNote(''); setNoteName(''); show('note added, indexing…'); refresh() } catch (e) { error(e) } finally { setBusy(null) }
  }
  async function loadSample() {
    setBusy('sample')
    try { const r = await post<{ knowledge: number; agents: number; tasks: number }>(`/api/projects/${projectId}/sample-data?agents=false&tasks=false`); show(r.knowledge ? `${r.knowledge} sample sources added` : 'sample sources already present'); refresh() } catch (e) { error(e) } finally { setBusy(null) }
  }

  return (
    <div className="space-y-3">
      <div onDragOver={(e) => { e.preventDefault(); setDrag(true) }} onDragLeave={() => setDrag(false)} onDrop={(e) => { e.preventDefault(); setDrag(false); if (e.dataTransfer.files.length) sendFiles(e.dataTransfer.files) }}
        className={clsx('panel-2 flex flex-col items-center justify-center gap-2 border-dashed px-4 py-6 text-center transition-colors', drag && 'border-neon glow-ring')}>
        <div className="text-fg-2"><span className="text-neon">$</span> upload documents · pdf · markdown · code · tracker export (json) · crash log (csv) · CODEOWNERS · releases.json</div>
        <div className="flex flex-wrap items-center justify-center gap-2">
          <input ref={fileRef} type="file" multiple className="hidden" onChange={(e) => { if (e.target.files?.length) sendFiles(e.target.files); e.target.value = '' }} />
          <Btn tone="primary" onClick={() => fileRef.current?.click()} loading={busy === 'upload'}>[ SELECT FILES ]</Btn>
          <Select value={kind} onChange={(e) => setKind(e.target.value)} className="w-auto!"><option value="auto">detect type</option><option value="document">document</option><option value="markdown">markdown</option><option value="code">code</option><option value="tracker">tracker (json)</option><option value="crashlog">crash log (csv)</option><option value="releases">releases (json)</option><option value="codeowners">CODEOWNERS</option></Select>
          <Btn onClick={loadSample} loading={busy === 'sample'} title="Adds the Orbit Run demo tracker, crash log, releases and CODEOWNERS">* LOAD SAMPLE DATASET</Btn>
        </div>
        <div className="text-[11px] text-fg-3 font-sans">or drop files here · tracker / crash log / releases / CODEOWNERS feed the agents' tools directly; everything else is embedded for search_knowledge</div>
      </div>
      {!compact && (
        <div className="grid gap-3 md:grid-cols-2">
          <div className="panel-2 p-3 space-y-2">
            <div className="label">add url</div>
            <div className="flex gap-2"><Input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://docs.example.com/architecture" /><Btn onClick={addUrl} loading={busy === 'url'}>fetch</Btn></div>
          </div>
          <div className="panel-2 p-3 space-y-2">
            <div className="label">paste text</div>
            <Input value={noteName} onChange={(e) => setNoteName(e.target.value)} placeholder="name, e.g. onboarding-notes" />
            <TextArea rows={3} value={note} onChange={(e) => setNote(e.target.value)} placeholder="Anything your agents should be able to look up." />
            <div className="flex justify-end"><Btn onClick={addText} loading={busy === 'text'}>add note</Btn></div>
          </div>
        </div>
      )}
      {!compact && <div className="panel"><KnowledgeList projectId={projectId} items={items ?? []} /></div>}
      <Toast msg={toast?.msg ?? null} tone={toast?.tone} />
    </div>
  )
}
