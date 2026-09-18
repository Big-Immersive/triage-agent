import { createFileRoute, useNavigate } from '@tanstack/react-router'
import { useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { MoreHorizontal } from 'lucide-react'
import { Btn, ConfirmModal, Empty, Input, Modal, PromptHeader, StatusDot, Toast, useToast } from '@/components/ui'
import { del, patch, post } from '@/api/client'
import { qk, useProjects } from '@/api/queries'
import { ago, pad2 } from '@/utils/format'
import type { Project } from '@/api/types'

export const Route = createFileRoute('/_app/projects/')({ component: Projects })

function Projects() {
  const [archived, setArchived] = useState(false)
  const { data, isLoading } = useProjects(archived)
  const nav = useNavigate()
  const qc = useQueryClient()
  const { toast, show, error } = useToast()
  const [menu, setMenu] = useState<string | null>(null)
  const [rename, setRename] = useState<Project | null>(null)
  const [name, setName] = useState('')
  const [remove, setRemove] = useState<Project | null>(null)
  const [busy, setBusy] = useState(false)
  const refresh = () => qc.invalidateQueries({ queryKey: qk.projects })

  async function doRename() {
    if (!rename) return
    setBusy(true)
    try { await patch(`/api/projects/${rename.id}`, { name }); show('renamed'); setRename(null); refresh() } catch (e) { error(e) } finally { setBusy(false) }
  }
  async function doArchive(p: Project) {
    try { await post(`/api/projects/${p.id}/${p.status === 'archived' ? 'activate' : 'archive'}`); show(p.status === 'archived' ? 'restored' : 'archived'); refresh() } catch (e) { error(e) }
  }
  async function doDelete() {
    if (!remove) return
    setBusy(true)
    try { await del(`/api/projects/${remove.id}`); show(`${remove.slug} deleted`); setRemove(null); refresh() } catch (e) { error(e) } finally { setBusy(false) }
  }

  return (
    <div className="p-4 md:p-6" onClick={() => setMenu(null)}>
      <PromptHeader title="projects" subtitle="Manage isolated AI workspaces." right={<>
        <label className="flex items-center gap-1.5 text-[11px] text-fg-3"><input type="checkbox" className="accent-[#00ff66]" checked={archived} onChange={(e) => setArchived(e.target.checked)} />show archived</label>
        <Btn tone="primary" onClick={() => nav({ to: '/projects/new' })}>* INITIALIZE PROJECT</Btn>
      </>} />
      {isLoading ? <div className="text-fg-3">$ project list …</div> : !data?.length ? (
        <Empty command="project list" lines={['No projects detected.', 'Initialize a workspace to begin.']} action={<Btn tone="primary" onClick={() => nav({ to: '/projects/new' })}>[ INITIALIZE PROJECT ]</Btn>} />
      ) : (
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {data.map((p, i) => (
            <div key={p.id} role="link" tabIndex={0} onClick={() => nav({ to: '/projects/$slug', params: { slug: p.slug } })} onKeyDown={(e) => { if (e.key === 'Enter') nav({ to: '/projects/$slug', params: { slug: p.slug } }) }}
              className={`panel hover-neon relative cursor-pointer p-3 anim-fade ${p.status === 'archived' ? 'opacity-60' : ''}`}>
              <div className="flex items-start justify-between">
                <div className="min-w-0">
                  <div className="label">PROJECT_{pad2(i + 1)}</div>
                  <div className="mt-0.5 truncate-1 text-[14px] text-fg-1"><span className="mr-1.5 text-neon">{p.icon}</span>{p.slug}</div>
                  <div className="mt-0.5 truncate-1 text-[11px] text-fg-3 font-sans">{p.description || 'no description'}</div>
                </div>
                <button onClick={(e) => { e.stopPropagation(); setMenu(menu === p.id ? null : p.id) }} className="text-fg-3 hover:text-fg-1" aria-label="project menu"><MoreHorizontal size={16} /></button>
              </div>
              <div className="mt-3 grid grid-cols-4 gap-2 text-[11px]">
                <div><div className="label">STATUS</div><StatusDot status={p.status === 'active' ? 'running' : p.status} label={p.status.toUpperCase()} /></div>
                <div><div className="label">AGENTS</div><div className="text-fg-1">{p.agents_total} <span className={p.agents_online ? 'text-neon' : 'text-fg-3'}>{p.agents_online ? `${p.agents_online} ONLINE` : 'IDLE'}</span></div></div>
                <div><div className="label">RUNS</div><div className="text-fg-1">{pad2(p.runs_active)} <span className={p.runs_active ? 'text-neon' : 'text-fg-3'}>ACTIVE</span></div></div>
                <div><div className="label">LAST ACTIVITY</div><div className="text-fg-1">{ago(p.last_activity_at)}</div></div>
              </div>
              {p.approvals_pending > 0 && <div className="mt-2 text-[11px] text-warn">● {p.approvals_pending} awaiting approval</div>}
              <div className="mt-2 text-[10px] text-fg-3">updated {ago(p.updated_at)}</div>
              {menu === p.id && (
                <div className="absolute right-3 top-9 z-20 panel glow-ring w-40 py-1 text-[11px] tracking-wider" onClick={(e) => e.stopPropagation()}>
                  <button className="block w-full px-3 py-1.5 text-left text-fg-1 hover:bg-bg-2" onClick={() => nav({ to: '/projects/$slug', params: { slug: p.slug } })}>OPEN</button>
                  <button className="block w-full px-3 py-1.5 text-left text-fg-1 hover:bg-bg-2" onClick={() => { setRename(p); setName(p.name); setMenu(null) }}>RENAME</button>
                  <button className="block w-full px-3 py-1.5 text-left text-fg-1 hover:bg-bg-2" onClick={() => nav({ to: '/projects/$slug/settings', params: { slug: p.slug } })}>SETTINGS</button>
                  <button className="block w-full px-3 py-1.5 text-left text-fg-1 hover:bg-bg-2" onClick={() => { doArchive(p); setMenu(null) }}>{p.status === 'archived' ? 'RESTORE' : 'ARCHIVE'}</button>
                  <button className="block w-full px-3 py-1.5 text-left text-danger hover:bg-bg-2" onClick={() => { setRemove(p); setMenu(null) }}>DELETE</button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
      <Modal open={!!rename} onClose={() => setRename(null)} title="rename_project">
        <Input label="project name" value={name} onChange={(e) => setName(e.target.value)} autoFocus onKeyDown={(e) => e.key === 'Enter' && doRename()} />
        <div className="mt-4 flex justify-end gap-2"><Btn onClick={() => setRename(null)}>cancel</Btn><Btn tone="primary" loading={busy} onClick={doRename}>[ RENAME ]</Btn></div>
      </Modal>
      <ConfirmModal open={!!remove} onClose={() => setRemove(null)} onConfirm={doDelete} title="delete_project" danger loading={busy} typed={remove?.slug} confirmText="[ DELETE PERMANENTLY ]"
        body={<><p>This removes <b className="text-fg-1">{remove?.slug}</b> with all of its agents, runs, memory, knowledge, files and approvals. Active runs are cancelled.</p><p>There is no undo.</p></>} />
      <Toast msg={toast?.msg ?? null} tone={toast?.tone} />
    </div>
  )
}
