import { useEffect, useState } from 'react'
import { clsx } from 'clsx'
import { Btn, Input, Select, TextArea } from '@/components/ui'
import { useModels, useTools } from '@/api/queries'

export interface AgentDraft {
  id?: string; name: string; role: string; description: string; instructions: string; model: string | null
  tools: string[]; permissions: Record<string, unknown>; can_handoff_to: string[]; enabled: boolean; position: number
}
export const emptyAgent = (position = 0): AgentDraft => ({ name: '', role: '', description: '', instructions: '', model: null, tools: [], permissions: {}, can_handoff_to: [], enabled: true, position })

export function AgentEditor({ value, others, onSave, onCancel, saving }: { value: AgentDraft; others: string[]; onSave: (a: AgentDraft) => void; onCancel: () => void; saving?: boolean }) {
  const [a, setA] = useState<AgentDraft>(value)
  useEffect(() => setA(value), [value])
  const { data: tools } = useTools()
  const { data: models } = useModels()
  const set = <K extends keyof AgentDraft>(k: K, v: AgentDraft[K]) => setA((x) => ({ ...x, [k]: v }))
  const toggle = (list: string[], v: string) => list.includes(v) ? list.filter((x) => x !== v) : [...list, v]
  const cats = ['intake', 'investigation', 'triage', 'output']
  return (
    <form onSubmit={(e) => { e.preventDefault(); onSave(a) }} className="space-y-4">
      <div className="grid gap-3 md:grid-cols-2">
        <Input label="agent name" required pattern="[a-z0-9_\-]+" value={a.name} onChange={(e) => set('name', e.target.value.toLowerCase())} placeholder="investigator" hint="lowercase, used in handoffs" />
        <Input label="role" value={a.role} onChange={(e) => set('role', e.target.value)} placeholder="Evidence Analysis" />
      </div>
      <Input label="description" value={a.description} onChange={(e) => set('description', e.target.value)} placeholder="What other agents see when deciding to hand off to this one" />
      <TextArea label="instructions" rows={8} value={a.instructions} onChange={(e) => set('instructions', e.target.value)} placeholder="System prompt: numbered steps, one job, an explicit 'call X, then hand off to Y' ending." />
      <div className="grid gap-3 md:grid-cols-2">
        <div>
          <Input label="model" list="model-suggestions" value={a.model ?? ''} onChange={(e) => set('model', e.target.value || null)} placeholder="default (from your llm.config)" hint="prefix with openrouter: or ollama: to pin a provider" />
          <datalist id="model-suggestions">
            {(models?.openrouter ?? []).map((m) => <option key={m} value={`openrouter:${m}`} />)}
            {(models?.ollama ?? []).map((m) => <option key={m} value={`ollama:${m}`} />)}
          </datalist>
        </div>
        <div>
          <span className="label mb-1 block">can hand off to</span>
          <div className="flex flex-wrap gap-1.5">
            {others.filter((o) => o !== a.name).map((o) => (
              <button type="button" key={o} onClick={() => set('can_handoff_to', toggle(a.can_handoff_to, o))} className={clsx('border px-2 py-1 text-[11px]', a.can_handoff_to.includes(o) ? 'border-neon/60 text-neon bg-neon/10' : 'border-line text-fg-3')}>→ {o}</button>
            ))}
            {others.filter((o) => o !== a.name).length === 0 && <span className="text-[11px] text-fg-3">no other agents yet</span>}
          </div>
        </div>
      </div>
      <div>
        <span className="label mb-1 block">tools</span>
        <div className="grid gap-2 sm:grid-cols-2">
          {cats.map((c) => (
            <div key={c} className="panel-2 p-2">
              <div className="label mb-1">{c}</div>
              {(tools ?? []).filter((t) => t.category === c).map((t) => (
                <label key={t.name} className="flex cursor-pointer items-start gap-2 py-0.5 text-[11px]">
                  <input type="checkbox" className="mt-0.5 accent-[#00ff66]" checked={a.tools.includes(t.name)} onChange={() => set('tools', toggle(a.tools, t.name))} />
                  <span><span className={a.tools.includes(t.name) ? 'text-fg-1' : 'text-fg-2'}>{t.name}</span>{t.gated && <span className="ml-1 text-warn">⏸ gated</span>}{t.side_effects && !t.gated && <span className="ml-1 text-fg-3">writes</span>}<div className="text-fg-3 font-sans">{t.summary}</div></span>
                </label>
              ))}
            </div>
          ))}
        </div>
      </div>
      <div className="grid gap-3 md:grid-cols-3">
        <Select label="permissions · side effects" value={String(a.permissions.side_effects ?? false)} onChange={(e) => set('permissions', { ...a.permissions, side_effects: e.target.value === 'true' })}><option value="false">read-only</option><option value="true">may write artifacts</option></Select>
        <Select label="permissions · approval" value={String(a.permissions.requires_approval ?? false)} onChange={(e) => set('permissions', { ...a.permissions, requires_approval: e.target.value === 'true' })}><option value="false">autonomous</option><option value="true">gated actions need a human</option></Select>
        <Select label="state" value={a.enabled ? 'on' : 'off'} onChange={(e) => set('enabled', e.target.value === 'on')}><option value="on">● ENABLED</option><option value="off">○ DISABLED</option></Select>
      </div>
      <div className="flex justify-end gap-2"><Btn type="button" onClick={onCancel}>cancel</Btn><Btn tone="primary" type="submit" loading={saving}>[ SAVE AGENT ]</Btn></div>
    </form>
  )
}
