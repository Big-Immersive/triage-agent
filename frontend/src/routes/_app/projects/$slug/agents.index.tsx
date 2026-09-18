import { Link, createFileRoute } from '@tanstack/react-router'
import { useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { clsx } from 'clsx'
import { Btn, ConfirmModal, Field, Modal, PromptHeader, StatusDot, ThinkingBars, Toast, useToast } from '@/components/ui'
import { AgentEditor, emptyAgent, type AgentDraft } from '@/components/features/AgentEditor'
import { useActiveProject } from '@/components/layout/ProjectShell'
import { del, patch, post } from '@/api/client'
import { qk, useAgents } from '@/api/queries'
import { ago, pad2 } from '@/utils/format'
import type { Agent } from '@/api/types'

export const Route = createFileRoute('/_app/projects/$slug/agents/')({ component: Agents })

function Agents() {
  const p = useActiveProject()
  const { data: agents } = useAgents(p.id)
  const qc = useQueryClient()
  const { toast, show, error } = useToast()
  const [editing, setEditing] = useState<AgentDraft | null>(null)
  const [remove, setRemove] = useState<Agent | null>(null)
  const [busy, setBusy] = useState(false)
  const refresh = () => { qc.invalidateQueries({ queryKey: qk.agents(p.id) }); qc.invalidateQueries({ queryKey: qk.project(p.id) }) }

  async function save(a: AgentDraft) {
    setBusy(true)
    try { if (a.id) await patch(`/api/projects/${p.id}/agents/${a.id}`, a); else await post(`/api/projects/${p.id}/agents`, a); show('agent saved'); setEditing(null); refresh() } catch (e) { error(e) } finally { setBusy(false) }
  }
  async function toggle(a: Agent) { try { await patch(`/api/projects/${p.id}/agents/${a.id}`, { enabled: !a.enabled }); refresh() } catch (e) { error(e) } }
  async function doRemove() { if (!remove) return; setBusy(true); try { await del(`/api/projects/${p.id}/agents/${remove.id}`); setRemove(null); refresh() } catch (e) { error(e) } finally { setBusy(false) } }
  async function loadTemplate() { setBusy(true); try { const r = await post<{ agents: number }>(`/api/projects/${p.id}/sample-data?knowledge_items=false&tasks=false`); show(r.agents ? `${r.agents} template agents added` : 'template already present'); refresh() } catch (e) { error(e) } finally { setBusy(false) } }

  return (
    <div>
      <PromptHeader title="agents" subtitle={`${agents?.length ?? 0} agents assigned to ${p.slug}.`} right={<><Btn onClick={loadTemplate} loading={busy}>load bug-triage template</Btn><Link to="/projects/$slug/graph" params={{ slug: p.slug }}><Btn>view graph</Btn></Link><Btn tone="primary" onClick={() => setEditing(emptyAgent(agents?.length ?? 0))}>* ADD AGENT</Btn></>} />
      {!agents?.length ? <div className="panel px-4 py-8 text-center text-fg-3"><span className="text-neon">$</span> agent list<br />No agents deployed. Add one or load the template.</div> : (
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {agents.map((a) => {
            const active = ['thinking', 'running', 'tool_call', 'waiting', 'human_input'].includes(a.status)
            return (
              <div key={a.id} className={clsx('panel hover-neon p-3 anim-fade', active && 'glow-ring', !a.enabled && 'opacity-60')}>
                <Field k="AGENT" v={<Link to="/projects/$slug/agents/$agentId" params={{ slug: p.slug, agentId: a.id }} className="text-fg-1 hover:text-neon">{a.name}</Link>} />
                <Field k="ROLE" v={a.role || '—'} mono={false} />
                <Field k="STATUS" v={<span className="flex items-center gap-2"><StatusDot status={a.enabled ? a.status : 'disabled'} />{a.status === 'thinking' && <ThinkingBars />}</span>} />
                <Field k="MODEL" v={a.model || <span className="text-fg-3">default</span>} />
                <Field k="CURRENT PROCESS" v={a.current_process ? <span className="text-neon">{a.current_process}</span> : <span className="text-fg-3">—</span>} />
                <Field k="TOOLS" v={pad2(a.tools.length)} />
                <Field k="LAST ACTIVE" v={ago(a.last_active_at)} />
                <div className="mt-2 flex flex-wrap gap-1 border-t border-line pt-2">
                  <Btn size="sm" onClick={() => setEditing({ ...a })}>edit</Btn>
                  <Btn size="sm" onClick={() => setEditing({ ...emptyAgent(agents.length), name: `${a.name}_copy`, role: a.role, description: a.description, instructions: a.instructions, model: a.model, tools: [...a.tools], can_handoff_to: [...a.can_handoff_to], permissions: { ...a.permissions } })}>duplicate</Btn>
                  <Btn size="sm" onClick={() => toggle(a)}>{a.enabled ? 'disable' : 'enable'}</Btn>
                  <Btn size="sm" tone="danger" onClick={() => setRemove(a)}>delete</Btn>
                </div>
              </div>
            )
          })}
        </div>
      )}
      <Modal open={!!editing} onClose={() => setEditing(null)} title={editing?.id ? `edit_agent ${editing.name}` : 'new_agent'} wide>
        {editing && <AgentEditor value={editing} others={(agents ?? []).map((a) => a.name)} onSave={save} onCancel={() => setEditing(null)} saving={busy} />}
      </Modal>
      <ConfirmModal open={!!remove} onClose={() => setRemove(null)} onConfirm={doRemove} title="delete_agent" danger loading={busy} body={<p>Remove <b className="text-fg-1">{remove?.name}</b> from this project? Other agents that hand off to it will no longer be able to.</p>} />
      <Toast msg={toast?.msg ?? null} tone={toast?.tone} />
    </div>
  )
}
