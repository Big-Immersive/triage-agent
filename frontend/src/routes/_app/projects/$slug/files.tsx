import { createFileRoute } from '@tanstack/react-router'
import { useQueryClient } from '@tanstack/react-query'
import { useMemo, useRef, useState } from 'react'
import { clsx } from 'clsx'
import { Btn, ConfirmModal, Input, Modal, Panel, PromptHeader, Toast, useToast } from '@/components/ui'
import { useActiveProject } from '@/components/layout/ProjectShell'
import { del, fileUrl, get, post, upload } from '@/api/client'
import { qk, useFiles } from '@/api/queries'
import { ago, bytes } from '@/utils/format'
import type { FileRow } from '@/api/types'

export const Route = createFileRoute('/_app/projects/$slug/files')({ component: Files })

interface TreeNode { row: FileRow; children: TreeNode[] }
function buildTree(rows: FileRow[]): TreeNode[] {
  const byPath = new Map<string, TreeNode>()
  rows.forEach((r) => byPath.set(r.path, { row: r, children: [] }))
  const roots: TreeNode[] = []
  rows.forEach((r) => {
    const parent = r.path.slice(0, r.path.lastIndexOf('/')) || ''
    const node = byPath.get(r.path)!
    if (parent && byPath.has(parent)) byPath.get(parent)!.children.push(node); else roots.push(node)
  })
  const sort = (n: TreeNode[]) => { n.sort((a, b) => (a.row.kind === b.row.kind ? a.row.name.localeCompare(b.row.name) : a.row.kind === 'dir' ? -1 : 1)); n.forEach((c) => sort(c.children)) }
  sort(roots)
  return roots
}

function Files() {
  const p = useActiveProject()
  const { data } = useFiles(p.id)
  const qc = useQueryClient()
  const { toast, show, error } = useToast()
  const [sel, setSel] = useState<FileRow | null>(null)
  const [preview, setPreview] = useState<{ text: string | null; mime: string; previewable: boolean } | null>(null)
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set())
  const [rename, setRename] = useState<FileRow | null>(null)
  const [newPath, setNewPath] = useState('')
  const [remove, setRemove] = useState<FileRow | null>(null)
  const [mkdir, setMkdir] = useState(false)
  const [folder, setFolder] = useState('/uploads')
  const [busy, setBusy] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)
  const tree = useMemo(() => buildTree(data ?? []), [data])
  const refresh = () => qc.invalidateQueries({ queryKey: qk.files(p.id) })

  async function select(r: FileRow) {
    setSel(r)
    if (r.kind === 'dir') { setPreview(null); setFolder(r.path); return }
    try { setPreview(await get(`/api/projects/${p.id}/files/${r.id}/preview`)) } catch (e) { error(e) }
  }
  async function doUpload(files: FileList) { const fd = new FormData(); Array.from(files).forEach((f) => fd.append('files', f)); fd.append('folder', folder); setBusy(true); try { await upload(`/api/projects/${p.id}/files/upload`, fd); show(`${files.length} uploaded to ${folder}`); refresh() } catch (e) { error(e) } finally { setBusy(false) } }
  async function doRename() { if (!rename) return; setBusy(true); try { await post(`/api/projects/${p.id}/files/${rename.id}/move`, { new_path: newPath }); setRename(null); show('moved'); refresh() } catch (e) { error(e) } finally { setBusy(false) } }
  async function doRemove() { if (!remove) return; setBusy(true); try { await del(`/api/projects/${p.id}/files/${remove.id}`); setRemove(null); if (sel?.id === remove.id) { setSel(null); setPreview(null) } refresh() } catch (e) { error(e) } finally { setBusy(false) } }
  async function doMkdir() { setBusy(true); try { await post(`/api/projects/${p.id}/files/mkdir`, { path: newPath }); setMkdir(false); refresh() } catch (e) { error(e) } finally { setBusy(false) } }

  const render = (nodes: TreeNode[], depth: number, prefix: string): React.ReactNode => nodes.map((n, i) => {
    const last = i === nodes.length - 1
    const branch = prefix + (last ? '└── ' : '├── ')
    const isCollapsed = collapsed.has(n.row.path)
    return (
      <div key={n.row.id}>
        <button onClick={() => { select(n.row); if (n.row.kind === 'dir') setCollapsed((s) => { const x = new Set(s); x.has(n.row.path) ? x.delete(n.row.path) : x.add(n.row.path); return x }) }}
          className={clsx('flex w-full items-center justify-between px-2 py-0.5 text-left text-[12px] hover:bg-bg-2', sel?.id === n.row.id && 'bg-neon/10 text-neon')}>
          <span className="whitespace-pre"><span className="text-fg-3">{branch}</span>{n.row.kind === 'dir' ? <span className="text-neon-2">{n.row.name}/</span> : <span className={sel?.id === n.row.id ? 'text-neon' : 'text-fg-1'}>{n.row.name}</span>}</span>
          {n.row.kind === 'file' && <span className="text-[10px] text-fg-3">{bytes(n.row.size_bytes)}</span>}
        </button>
        {n.row.kind === 'dir' && !isCollapsed && render(n.children, depth + 1, prefix + (last ? '    ' : '│   '))}
      </div>
    )
  })

  return (
    <div>
      <PromptHeader title="files" subtitle="Project file system. Uploads, knowledge sources and run artifacts (/out) live here." right={<>
        <input ref={fileRef} type="file" multiple className="hidden" onChange={(e) => { if (e.target.files?.length) doUpload(e.target.files); e.target.value = '' }} />
        <span className="text-[11px] text-fg-3">target {folder}</span>
        <Btn onClick={() => { setNewPath(folder + '/'); setMkdir(true) }}>mkdir</Btn>
        <Btn tone="primary" onClick={() => fileRef.current?.click()} loading={busy}>* UPLOAD</Btn>
      </>} />
      <div className="grid gap-4 lg:grid-cols-[minmax(260px,1fr)_2fr]">
        <Panel title="/"><div className="py-1">{tree.length ? render(tree, 0, '') : <div className="px-3 py-3 text-fg-3">empty</div>}</div></Panel>
        <Panel title={sel ? sel.path : 'PREVIEW'} right={sel && sel.kind === 'file' ? <>
          <a href={fileUrl(p.id, sel.id, true)} className="text-[11px] text-fg-3 hover:text-neon">download</a>
          <Btn size="sm" onClick={() => { setRename(sel); setNewPath(sel.path) }}>rename / move</Btn>
          <Btn size="sm" tone="danger" onClick={() => setRemove(sel)}>delete</Btn>
        </> : sel ? <><Btn size="sm" onClick={() => { setRename(sel); setNewPath(sel.path) }}>rename</Btn><Btn size="sm" tone="danger" onClick={() => setRemove(sel)}>delete</Btn></> : null}>
          {!sel ? <div className="p-4 text-fg-3">select a file to preview</div> : sel.kind === 'dir' ? <div className="p-4 text-fg-3">directory · {ago(sel.updated_at)}</div> : preview?.text != null ? (
            <pre className="max-h-[60vh] overflow-auto whitespace-pre-wrap p-3 text-[12px] text-fg-2">{preview.text}</pre>
          ) : preview?.mime === 'application/pdf' ? <iframe title="pdf" src={fileUrl(p.id, sel.id)} className="h-[60vh] w-full bg-white" /> : <div className="p-4 text-fg-3">{sel.mime} · no inline preview · <a href={fileUrl(p.id, sel.id, true)} className="text-neon">download</a></div>}
          {sel && sel.kind === 'file' && <div className="border-t border-line px-3 py-1.5 text-[10px] text-fg-3">{sel.mime} · {bytes(sel.size_bytes)} · updated {ago(sel.updated_at)}</div>}
        </Panel>
      </div>
      <Modal open={!!rename} onClose={() => setRename(null)} title="move_path"><Input label="new path" value={newPath} onChange={(e) => setNewPath(e.target.value)} autoFocus onKeyDown={(e) => e.key === 'Enter' && doRename()} /><div className="mt-4 flex justify-end gap-2"><Btn onClick={() => setRename(null)}>cancel</Btn><Btn tone="primary" loading={busy} onClick={doRename}>[ MOVE ]</Btn></div></Modal>
      <Modal open={mkdir} onClose={() => setMkdir(false)} title="mkdir"><Input label="directory path" value={newPath} onChange={(e) => setNewPath(e.target.value)} autoFocus onKeyDown={(e) => e.key === 'Enter' && doMkdir()} /><div className="mt-4 flex justify-end gap-2"><Btn onClick={() => setMkdir(false)}>cancel</Btn><Btn tone="primary" loading={busy} onClick={doMkdir}>[ CREATE ]</Btn></div></Modal>
      <ConfirmModal open={!!remove} onClose={() => setRemove(null)} onConfirm={doRemove} title="rm" danger loading={busy} body={<p>Delete <b className="text-fg-1">{remove?.path}</b>{remove?.kind === 'dir' ? ' and everything inside it' : ''}?</p>} />
      <Toast msg={toast?.msg ?? null} tone={toast?.tone} />
    </div>
  )
}
