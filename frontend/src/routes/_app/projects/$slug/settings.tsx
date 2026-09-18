import { createFileRoute, useNavigate } from '@tanstack/react-router'
import { useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { clsx } from 'clsx'
import { Btn, ConfirmModal, Input, Panel, PromptHeader, Select, TextArea, Toast, useToast } from '@/components/ui'
import { useActiveProject } from '@/components/layout/ProjectShell'
import { del, patch, post } from '@/api/client'
import { qk } from '@/api/queries'

export const Route = createFileRoute('/_app/projects/$slug/settings')({ component: Settings })
const SECTIONS = ['project.config', 'agent.config', 'memory.config', 'approval.config', 'integrations.config', 'security', 'danger_zone'] as const

function Settings() {
  const p = useActiveProject()
  const nav = useNavigate()
  const qc = useQueryClient()
  const { toast, show, error } = useToast()
  const [sec, setSec] = useState<(typeof SECTIONS)[number]>('project.config')
  const [name, setName] = useState(p.name)
  const [description, setDescription] = useState(p.description)
  const [instructions, setInstructions] = useState(p.instructions)
  const [icon, setIcon] = useState(p.icon)
  const cfg = (p.config ?? {}) as Record<string, string | number | boolean>
  const [config, setConfig] = useState<Record<string, string | number | boolean>>({ gate_severity: 'high', gate_min_confidence: 0.7, default_auto_approve: false, auto_run: true, memory_auto_write: true, memory_pin_context: true, ...cfg })
  const [intakeKey, setIntakeKey] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [remove, setRemove] = useState(false)

  async function save(extra: Record<string, unknown> = {}) {
    setBusy(true)
    try { await patch(`/api/projects/${p.id}`, { name, description, instructions, icon, config, ...extra }); show('saved'); qc.invalidateQueries({ queryKey: qk.project(p.slug) }); qc.invalidateQueries({ queryKey: qk.project(p.id) }); qc.invalidateQueries({ queryKey: qk.projects }) } catch (e) { error(e) } finally { setBusy(false) }
  }
  async function archive() { try { await post(`/api/projects/${p.id}/${p.status === 'archived' ? 'activate' : 'archive'}`); qc.invalidateQueries({ queryKey: qk.projects }); nav({ to: '/projects' }) } catch (e) { error(e) } }
  async function doDelete() { setBusy(true); try { await del(`/api/projects/${p.id}`); qc.invalidateQueries({ queryKey: qk.projects }); nav({ to: '/projects' }) } catch (e) { error(e); setBusy(false) } }

  return (
    <div>
      <PromptHeader title="settings" subtitle={`Configuration for ${p.slug}. Changes apply to future runs.`} />
      <div className="grid gap-4 md:grid-cols-[180px_1fr]">
        <nav className="space-y-0.5">{SECTIONS.map((s) => <button key={s} onClick={() => setSec(s)} className={clsx('block w-full px-2 py-1.5 text-left text-[12px]', sec === s ? 'text-neon bg-neon/5 border-l-2 border-neon' : s === 'danger_zone' ? 'text-danger/80 hover:text-danger' : 'text-fg-2 hover:text-fg-1')}><span className="text-fg-3">&gt;</span> {s}</button>)}</nav>
        <Panel title={sec}>
          <div className="space-y-4 p-4">
            {sec === 'project.config' && <>
              <div className="grid gap-3 md:grid-cols-[1fr_120px]"><Input label="name" value={name} onChange={(e) => setName(e.target.value)} /><Input label="icon" value={icon} onChange={(e) => setIcon(e.target.value)} maxLength={2} /></div>
              <Input label="description" value={description} onChange={(e) => setDescription(e.target.value)} />
              <TextArea label="project instructions" rows={8} value={instructions} onChange={(e) => setInstructions(e.target.value)} hint="Sent to every agent as PROJECT CONTEXT on every run." />
              <div className="flex justify-end"><Btn tone="primary" loading={busy} onClick={() => save()}>[ SAVE ]</Btn></div>
            </>}
            {sec === 'agent.config' && <>
              <div className="text-[12px] text-fg-2 font-sans">Agents are managed on the agents page (name, role, instructions, model, tools, permissions, handoffs). Project-wide defaults:</div>
              <Select label="auto-run new tasks" value={String(config.auto_run)} onChange={(e) => setConfig({ ...config, auto_run: e.target.value === 'true' })}><option value="true">yes — every created / imported / pushed task starts a run immediately</option><option value="false">no — tasks wait for RUN</option></Select>
              <Select label="default run mode" value={String(config.default_auto_approve)} onChange={(e) => setConfig({ ...config, default_auto_approve: e.target.value === 'true' })}><option value="false">pause at the human gate</option><option value="true">auto-approve everything</option></Select>
              <div className="flex justify-end"><Btn tone="primary" loading={busy} onClick={() => save()}>[ SAVE ]</Btn></div>
            </>}
            {sec === 'memory.config' && <>
              <Select label="write memories after each run" value={String(config.memory_auto_write)} onChange={(e) => setConfig({ ...config, memory_auto_write: e.target.value === 'true' })}><option value="true">yes — COMPLETED_WORK, DECISIONS, AGENT_NOTES</option><option value="false">no</option></Select>
              <Select label="inject pinned PROJECT_CONTEXT" value={String(config.memory_pin_context)} onChange={(e) => setConfig({ ...config, memory_pin_context: e.target.value === 'true' })}><option value="true">yes</option><option value="false">no</option></Select>
              <div className="text-[11px] text-fg-3 font-sans">Cross-project memory access is not possible by design.</div>
              <div className="flex justify-end"><Btn tone="primary" loading={busy} onClick={() => save()}>[ SAVE ]</Btn></div>
            </>}
            {sec === 'approval.config' && <>
              <Select label="require approval from severity" value={String(config.gate_severity)} onChange={(e) => setConfig({ ...config, gate_severity: e.target.value })}><option value="critical">critical only</option><option value="high">high and critical (default)</option><option value="medium">medium and above</option></Select>
              <Input label="minimum confidence before auto-proceeding" type="number" step="0.05" min={0} max={1} value={String(config.gate_min_confidence)} onChange={(e) => setConfig({ ...config, gate_min_confidence: Number(e.target.value) })} hint="Below this, create_ticket pauses for a human regardless of severity." />
              <div className="flex justify-end"><Btn tone="primary" loading={busy} onClick={() => save()}>[ SAVE ]</Btn></div>
            </>}
            {sec === 'integrations.config' && <div className="text-[12px] text-fg-2 font-sans">Connections are configured on the <button className="text-neon" onClick={() => nav({ to: '/projects/$slug/integrations', params: { slug: p.slug } })}>integrations page</button>. Secrets are stored per project and never returned to the browser in full.</div>}
            {sec === 'security' && <div className="space-y-2 text-[12px] text-fg-2 font-sans">
              <div>▸ Every record in this project carries its project id; agents can only read records where <code className="text-fg-1">project_id == {p.id.slice(0, 8)}…</code>.</div>
              <div>▸ LLM keys belong to your user account (settings › llm.config) and are encrypted at rest.</div>
              <div>▸ Runs execute on isolated workers; the writer agent's <code className="text-fg-1">create_ticket</code> is the only tool that pauses for a human.</div>
              <div>▸ Project id: <code className="text-fg-1">{p.id}</code></div>
              <div className="mt-4 border-t border-line pt-3 font-mono">
                <div className="label mb-1">intake endpoint (push feedback in from anywhere)</div>
                <div className="text-fg-2 font-sans">External systems send feedback here with a per-project key; with auto-run on, each item is triaged immediately. The key is shown once.</div>
                <div className="mt-2 flex flex-wrap items-center gap-2">
                  <Btn size="sm" tone="primary" onClick={async () => { try { const r = await post<{ key: string }>(`/api/projects/${p.id}/intake-key`); setIntakeKey(r.key); qc.invalidateQueries({ queryKey: ['project'] }) } catch (e) { error(e) } }}>{cfg.intake_key_hint ? 'ROTATE KEY' : 'GENERATE KEY'}</Btn>
                  {cfg.intake_key_hint && <Btn size="sm" tone="danger" onClick={async () => { try { await del(`/api/projects/${p.id}/intake-key`); setIntakeKey(null); show('intake key revoked'); qc.invalidateQueries({ queryKey: ['project'] }) } catch (e) { error(e) } }}>REVOKE</Btn>}
                  {cfg.intake_key_hint && !intakeKey && <span className="text-[11px] text-fg-3">active key {String(cfg.intake_key_hint)}</span>}
                </div>
                {intakeKey && <div className="mt-2 border border-neon/40 bg-neon/5 p-2 text-[11px]"><div className="text-warn">copy it now — it will not be shown again</div><code className="block break-all text-neon">{intakeKey}</code></div>}
                <pre className="mt-2 overflow-x-auto border border-line bg-bg-0 p-2 text-[11px] text-fg-2">{`curl -X POST ${window.location.origin.replace(':5173', ':8000')}/api/intake/${p.id} \\
  -H "X-Intake-Key: ${intakeKey ?? '<your key>'}" -H "content-type: application/json" \\
  -d '{"items":[{"id":"APP-101","source":"app_store","author":"user_42","rating":1,
        "text":"Crashes every time I open the shop","metadata":{"app_version":"2.4.1","device":"Pixel 8"}}]}'`}</pre>
              </div>
            </div>}
            {sec === 'danger_zone' && <div className="space-y-3">
              <div className="flex items-center justify-between border border-line p-3"><div><div className="text-fg-1">{p.status === 'archived' ? 'Restore project' : 'Archive project'}</div><div className="text-[11px] text-fg-3 font-sans">Hidden from lists; nothing is deleted.</div></div><Btn onClick={archive}>{p.status === 'archived' ? 'RESTORE' : 'ARCHIVE'}</Btn></div>
              <div className="flex items-center justify-between border border-danger/40 p-3"><div><div className="text-danger">Delete project</div><div className="text-[11px] text-fg-3 font-sans">Agents, runs, memory, knowledge, files and approvals are removed permanently.</div></div><Btn tone="danger" onClick={() => setRemove(true)}>DELETE</Btn></div>
            </div>}
          </div>
        </Panel>
      </div>
      <ConfirmModal open={remove} onClose={() => setRemove(false)} onConfirm={doDelete} title="delete_project" danger loading={busy} typed={p.slug} confirmText="[ DELETE PERMANENTLY ]" body={<p>This permanently deletes <b className="text-fg-1">{p.slug}</b> and everything in it.</p>} />
      <Toast msg={toast?.msg ?? null} tone={toast?.tone} />
    </div>
  )
}
