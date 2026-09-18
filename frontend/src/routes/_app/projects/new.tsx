import { createFileRoute, useNavigate } from '@tanstack/react-router'
import { useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { clsx } from 'clsx'
import { Btn, Input, Modal, PromptHeader, TextArea, Toast, useToast } from '@/components/ui'
import { AgentEditor, emptyAgent, type AgentDraft } from '@/components/features/AgentEditor'
import { KnowledgeUploader } from '@/components/features/KnowledgeUploader'
import { del, patch, post } from '@/api/client'
import { qk, useAgents, useKnowledge, useProjectEvents } from '@/api/queries'
import type { Agent, Project } from '@/api/types'

export const Route = createFileRoute('/_app/projects/new')({ component: NewProject })

const STEPS = ['IDENTITY', 'KNOWLEDGE', 'AGENTS', 'REVIEW'] as const
const ICONS = ['▣', '◈', '◉', '⬡', '△', '◫', '⌘', '✦', '⚙', '⛁']

function NewProject() {
  const nav = useNavigate()
  const qc = useQueryClient()
  const { toast, show, error } = useToast()
  const [step, setStep] = useState(0)
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [icon, setIcon] = useState(ICONS[0])
  const [instructions, setInstructions] = useState('')
  const [project, setProject] = useState<Project | null>(null)
  const [busy, setBusy] = useState(false)
  const [editing, setEditing] = useState<AgentDraft | null>(null)
  const { data: agents } = useAgents(project?.id ?? '')
  const { data: knowledge } = useKnowledge(project?.id ?? '')
  useProjectEvents(project?.id)

  // A draft project is created when leaving step 1 so uploads / agents attach to a real id.
  async function ensureProject(): Promise<Project> {
    if (project) {
      const p = await patch<Project>(`/api/projects/${project.id}`, { name, description, icon, instructions })
      setProject(p); return p
    }
    const p = await post<Project>('/api/projects', { name, description, icon, instructions })
    setProject(p); return p
  }
  async function next() {
    if (step === 0) {
      if (!name.trim()) return
      setBusy(true)
      try { await ensureProject() } catch (e) { error(e); setBusy(false); return }
      setBusy(false)
    }
    setStep((s) => Math.min(s + 1, 3))
  }
  async function saveAgent(a: AgentDraft) {
    if (!project) return
    setBusy(true)
    try {
      if (a.id) await patch(`/api/projects/${project.id}/agents/${a.id}`, a)
      else await post(`/api/projects/${project.id}/agents`, a)
      qc.invalidateQueries({ queryKey: qk.agents(project.id) }); setEditing(null)
    } catch (e) { error(e) } finally { setBusy(false) }
  }
  async function loadTemplate() {
    if (!project) return
    setBusy(true)
    try { const r = await post<{ agents: number }>(`/api/projects/${project.id}/sample-data?knowledge_items=false&tasks=false`); show(r.agents ? `${r.agents} template agents added` : 'template agents already present'); qc.invalidateQueries({ queryKey: qk.agents(project.id) }) } catch (e) { error(e) } finally { setBusy(false) }
  }
  async function finish(withSampleTasks: boolean) {
    if (!project) return
    setBusy(true)
    try {
      await patch(`/api/projects/${project.id}`, { name, description, icon, instructions })
      if (withSampleTasks) await post(`/api/projects/${project.id}/sample-data?agents=false&knowledge_items=false`)
      const p = await post<Project>(`/api/projects/${project.id}/activate`)
      qc.invalidateQueries({ queryKey: qk.projects })
      nav({ to: '/projects/$slug', params: { slug: p.slug } })
    } catch (e) { error(e); setBusy(false) }
  }
  async function discard() {
    if (project) { try { await del(`/api/projects/${project.id}`) } catch { /* ignore */ } }
    qc.invalidateQueries({ queryKey: qk.projects }); nav({ to: '/projects' })
  }

  return (
    <div className="mx-auto max-w-4xl p-4 md:p-6">
      <PromptHeader title="initialize_project" subtitle="Four steps. Everything you configure here is scoped to this workspace only." />
      <ol className="mb-5 grid grid-cols-4 gap-1">
        {STEPS.map((s, i) => (
          <li key={s} className={clsx('border px-2 py-1.5 text-[10px] tracking-widest', i === step ? 'border-neon/60 text-neon glow-sm' : i < step ? 'border-line text-fg-2' : 'border-line text-fg-3')}>
            STEP {String(i + 1).padStart(2, '0')} — {s}
          </li>
        ))}
      </ol>

      {step === 0 && (
        <div className="panel space-y-4 p-4 anim-fade">
          <div className="grid gap-4 md:grid-cols-[1fr_auto]">
            <Input label="project name" value={name} onChange={(e) => setName(e.target.value)} placeholder="payments-platform" autoFocus required />
            <div><span className="label mb-1 block">project icon</span><div className="flex gap-1">{ICONS.map((ic) => <button key={ic} type="button" onClick={() => setIcon(ic)} className={clsx('h-8 w-8 border text-[14px]', icon === ic ? 'border-neon text-neon glow-sm' : 'border-line text-fg-3')}>{ic}</button>)}</div></div>
          </div>
          <Input label="description" value={description} onChange={(e) => setDescription(e.target.value)} placeholder="What this workspace is for" />
          <TextArea label="project instructions" rows={6} value={instructions} onChange={(e) => setInstructions(e.target.value)} placeholder="Provide the context your agents should always understand about this project." hint="Prepended to every agent's instructions on every run, together with pinned PROJECT_CONTEXT memories." />
        </div>
      )}

      {step === 1 && project && (
        <div className="anim-fade"><KnowledgeUploader projectId={project.id} /></div>
      )}

      {step === 2 && project && (
        <div className="space-y-3 anim-fade">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="text-fg-2 font-sans text-[12px]">Configure the agents for this project. Each one has its own instructions, tools, model and handoff targets; more can be added later from the agents page.</div>
            <div className="flex gap-2"><Btn onClick={loadTemplate} loading={busy}>load bug-triage template</Btn><Btn tone="primary" onClick={() => setEditing(emptyAgent(agents?.length ?? 0))}>* ADD AGENT</Btn></div>
          </div>
          {!agents?.length ? <div className="panel px-4 py-6 text-center text-fg-3"><span className="text-neon">$</span> agent list<br />No agents configured. Add one or load the template.</div> : (
            <div className="grid gap-2 md:grid-cols-2">
              {agents.map((a) => <AgentRow key={a.id} a={a} onEdit={() => setEditing({ ...a })} onDelete={async () => { await del(`/api/projects/${project.id}/agents/${a.id}`); qc.invalidateQueries({ queryKey: qk.agents(project.id) }) }} />)}
            </div>
          )}
        </div>
      )}

      {step === 3 && project && (
        <div className="panel p-4 anim-fade">
          <div className="grid gap-x-6 gap-y-2 text-[12px] md:grid-cols-[140px_1fr]">
            <span className="label">NAME</span><span className="text-fg-1">{icon} {name}</span>
            <span className="label">DESCRIPTION</span><span className="text-fg-2 font-sans">{description || '—'}</span>
            <span className="label">INSTRUCTIONS</span><span className="whitespace-pre-wrap text-fg-2 font-sans">{instructions || '—'}</span>
            <span className="label">KNOWLEDGE</span><span className="text-fg-1">{knowledge?.length ?? 0} items {knowledge?.some((k) => k.status === 'indexing') && <span className="text-warn">· still indexing (fine, continues in the background)</span>}</span>
            <span className="label">AGENTS</span><span className="text-fg-1">{agents?.length ?? 0} configured · {agents?.filter((a) => a.enabled).length ?? 0} enabled{agents?.length ? <div className="mt-1 text-fg-3">{agents.map((a) => `${a.name}${a.can_handoff_to.length ? ' → ' + a.can_handoff_to.join(', ') : ''}`).join(' · ')}</div> : null}</span>
            <span className="label">ISOLATION</span><span className="text-fg-2 font-sans">Agents in this project can only read this project's memory, knowledge, files and runs.</span>
          </div>
          <div className="mt-5 flex flex-wrap items-center justify-between gap-2 border-t border-line pt-4">
            <label className="flex items-center gap-2 text-[11px] text-fg-2"><input id="sample" type="checkbox" className="accent-[#00ff66]" defaultChecked={false} /> also load the 15 sample feedback items as tasks so you can press RUN immediately</label>
            <Btn tone="primary" loading={busy} onClick={() => finish((document.getElementById('sample') as HTMLInputElement)?.checked)}>[ INITIALIZE PROJECT ]</Btn>
          </div>
        </div>
      )}

      <div className="mt-4 flex items-center justify-between">
        <Btn onClick={discard} tone="danger" size="sm">{project ? 'discard draft' : 'cancel'}</Btn>
        <div className="flex gap-2">
          {step > 0 && <Btn onClick={() => setStep((s) => s - 1)}>← back</Btn>}
          {step < 3 && <Btn tone="primary" loading={busy} disabled={step === 0 && !name.trim()} onClick={next}>next →</Btn>}
        </div>
      </div>
      <Modal open={!!editing} onClose={() => setEditing(null)} title={editing?.id ? `edit_agent ${editing.name}` : 'new_agent'} wide>
        {editing && <AgentEditor value={editing} others={(agents ?? []).map((a) => a.name)} onSave={saveAgent} onCancel={() => setEditing(null)} saving={busy} />}
      </Modal>
      <Toast msg={toast?.msg ?? null} tone={toast?.tone} />
    </div>
  )
}

export function AgentRow({ a, onEdit, onDelete }: { a: Agent; onEdit: () => void; onDelete: () => void }) {
  return (
    <div className={clsx('panel-2 p-3', !a.enabled && 'opacity-60')}>
      <div className="flex items-center justify-between"><span className="text-fg-1">{a.name}</span><span className={clsx('text-[10px]', a.enabled ? 'text-neon' : 'text-fg-3')}>{a.enabled ? '● ENABLED' : '○ DISABLED'}</span></div>
      <div className="text-[11px] text-fg-2">{a.role || '—'} · {a.model || 'default model'}</div>
      <div className="mt-1 text-[10px] text-fg-3">tools {a.tools.length} · handoff → {a.can_handoff_to.join(', ') || 'none'}</div>
      <div className="mt-2 flex gap-1"><Btn size="sm" onClick={onEdit}>edit</Btn><Btn size="sm" tone="danger" onClick={onDelete}>remove</Btn></div>
    </div>
  )
}
