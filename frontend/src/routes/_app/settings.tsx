import { createFileRoute } from '@tanstack/react-router'
import { useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { clsx } from 'clsx'
import { Btn, Input, KeyField, Panel, PromptHeader, Select, StatTile, TermTable, Toast, useToast } from '@/components/ui'
import { useAuth } from '@/stores/auth'
import { post, put } from '@/api/client'
import { qk, useLlm, useUsage } from '@/api/queries'
import { hhmm, usd } from '@/utils/format'

export const Route = createFileRoute('/_app/settings')({ component: UserSettings })
const SECTIONS = ['llm.config', 'usage', 'profile'] as const

function UserSettings() {
  const { user } = useAuth()
  const { data: llm } = useLlm()
  const { data: usage } = useUsage()
  const qc = useQueryClient()
  const { toast, show, error } = useToast()
  const [sec, setSec] = useState<(typeof SECTIONS)[number]>('llm.config')
  const [provider, setProvider] = useState<'openrouter' | 'ollama'>('openrouter')
  const [key, setKey] = useState('')
  const [model, setModel] = useState('')
  const [ollamaUrl, setOllamaUrl] = useState('')
  const [embedProvider, setEmbedProvider] = useState<'ollama' | 'openai_compatible'>('ollama')
  const [embedModel, setEmbedModel] = useState('')
  const [embedBase, setEmbedBase] = useState('')
  const [embedKey, setEmbedKey] = useState('')
  const [busy, setBusy] = useState<string | null>(null)
  const [test, setTest] = useState<Record<string, unknown> | null>(null)
  useEffect(() => { if (llm) { setProvider(llm.provider); setModel(llm.default_model); setOllamaUrl(llm.ollama_url); setEmbedProvider(llm.embed_provider); setEmbedModel(llm.embed_model); setEmbedBase(llm.embed_base_url ?? '') } }, [llm])

  async function save() {
    setBusy('save')
    try {
      await put('/api/me/llm', { provider, openrouter_key: key || null, default_model: model, ollama_url: ollamaUrl, embed_provider: embedProvider, embed_model: embedModel, embed_base_url: embedBase, embed_api_key: embedKey || null })
      setKey(''); setEmbedKey(''); show('llm.config saved'); qc.invalidateQueries({ queryKey: qk.llm }); qc.invalidateQueries({ queryKey: qk.health })
    } catch (e) { error(e) } finally { setBusy(null) }
  }
  async function runTest() { setBusy('test'); try { setTest(await post('/api/me/llm/test')) } catch (e) { error(e) } finally { setBusy(null) } }

  return (
    <div className="p-4 md:p-6">
      <PromptHeader title="settings" subtitle="Your account. LLM keys are yours, encrypted at rest, and used by every project you own." />
      <div className="grid gap-4 md:grid-cols-[180px_1fr]">
        <nav className="space-y-0.5">{SECTIONS.map((s) => <button key={s} onClick={() => setSec(s)} className={clsx('block w-full px-2 py-1.5 text-left text-[12px]', sec === s ? 'text-neon bg-neon/5 border-l-2 border-neon' : 'text-fg-2 hover:text-fg-1')}><span className="text-fg-3">&gt;</span> {s}</button>)}</nav>
        {sec === 'llm.config' && (
          <Panel title="llm.config">
            <div className="space-y-5 p-4">
              <div className="grid gap-3 md:grid-cols-2">
                <Select label="chat provider" value={provider} onChange={(e) => setProvider(e.target.value as 'openrouter' | 'ollama')}><option value="openrouter">OpenRouter (hosted, any model)</option><option value="ollama">Ollama (local / self-hosted)</option></Select>
                <Input label="default model" value={model} onChange={(e) => setModel(e.target.value)} placeholder={provider === 'openrouter' ? 'z-ai/glm-5' : 'qwen2.5:7b'} hint="agents can override this per agent" />
              </div>
              {provider === 'openrouter' && <KeyField label="openrouter api key" masked={llm?.openrouter_key_masked ?? null} has={!!llm?.has_openrouter_key} value={key} onChange={setKey} hint="Stored encrypted. Spend shows up under usage and on openrouter.ai." />}
              <Input label="ollama url" value={ollamaUrl} onChange={(e) => setOllamaUrl(e.target.value)} placeholder="http://localhost:11434" hint="Used for local chat models and/or local embeddings." />
              <div className="border-t border-line pt-4">
                <div className="label mb-2">embeddings (knowledge search, tracker & batch memory)</div>
                <div className="grid gap-3 md:grid-cols-2">
                  <Select label="embedding provider" value={embedProvider} onChange={(e) => setEmbedProvider(e.target.value as 'ollama' | 'openai_compatible')}><option value="ollama">Ollama (nomic-embed-text)</option><option value="openai_compatible">OpenAI-compatible API (hosted)</option></Select>
                  <Input label="embedding model" value={embedModel} onChange={(e) => setEmbedModel(e.target.value)} placeholder={embedProvider === 'ollama' ? 'nomic-embed-text' : 'text-embedding-3-small'} />
                </div>
                {embedProvider === 'openai_compatible' && <div className="mt-3 grid gap-3 md:grid-cols-2">
                  <Input label="base url" value={embedBase} onChange={(e) => setEmbedBase(e.target.value)} placeholder="https://api.openai.com/v1" />
                  <KeyField label="embedding api key" masked={llm?.embed_api_key_masked ?? null} has={!!llm?.has_embed_api_key} value={embedKey} onChange={setEmbedKey} />
                </div>}
                <div className="mt-2 text-[11px] text-fg-3 font-sans">Hosted deployments have no local Ollama — pick an OpenAI-compatible endpoint there. Changing the embedding model starts fresh vector tables; re-index knowledge afterwards.</div>
              </div>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <Btn onClick={runTest} loading={busy === 'test'}>TEST CONNECTION</Btn>
                <Btn tone="primary" onClick={save} loading={busy === 'save'}>[ SAVE ]</Btn>
              </div>
              {test && <pre className={clsx('border p-2 text-[11px] whitespace-pre-wrap', test.ok ? 'border-neon/40 text-neon' : 'border-warn/40 text-warn')}>{JSON.stringify(test, null, 1)}</pre>}
            </div>
          </Panel>
        )}
        {sec === 'usage' && (
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
              <StatTile label="TOTAL SPEND" value={usd(usage?.total_cost_usd ?? 0)} sub="estimated from token counts" />
              <StatTile label="PROMPT TOKENS" value={(usage?.total_prompt_tokens ?? 0).toLocaleString()} />
              <StatTile label="COMPLETION TOKENS" value={(usage?.total_completion_tokens ?? 0).toLocaleString()} />
              <StatTile label="PROJECTS BILLED" value={usage?.projects.length ?? 0} />
            </div>
            <Panel title="SPEND BY PROJECT">
              <TermTable flexCol={0} cols={['PROJECT', 'RUNS', 'LLM CALLS', 'PROMPT', 'COMPLETION', 'COST']} empty="no usage recorded yet — run a task" rows={(usage?.projects ?? []).map((r) => [<span className="text-fg-1">{r.slug}</span>, r.runs, r.llm_calls, r.prompt_tokens.toLocaleString(), r.completion_tokens.toLocaleString(), <span className="text-neon">{usd(r.cost_usd)}</span>])} />
            </Panel>
            <Panel title="SPEND BY MODEL">
              <TermTable flexCol={1} cols={['PROVIDER', 'MODEL', 'LLM CALLS', 'PROMPT', 'COMPLETION', 'COST']} empty="—" rows={(usage?.models ?? []).map((r) => [r.provider, <span className="text-fg-1">{r.model}</span>, r.llm_calls, r.prompt_tokens.toLocaleString(), r.completion_tokens.toLocaleString(), <span className="text-neon">{usd(r.cost_usd)}</span>])} />
            </Panel>
            <Panel title="RECENT RUNS">
              <TermTable flexCol={4} cols={['TIME', 'PROJECT', 'RUN', 'AGENT', 'MODEL', 'TOKENS', 'COST']} empty="—" rows={(usage?.recent ?? []).map((r) => [hhmm(r.ts), r.project_slug, <span className="text-fg-1">{r.run_id ?? '—'}</span>, r.agent_name, r.model, `${r.prompt_tokens} / ${r.completion_tokens}`, <span className={r.estimated ? 'text-neon' : 'text-fg-1'}>{usd(r.cost_usd)}{r.estimated ? '' : ' ✓'}</span>])} />
            </Panel>
          </div>
        )}
        {sec === 'profile' && (
          <Panel title="profile"><div className="space-y-2 p-4 text-[12px]"><div><span className="label">NAME </span>{user?.name}</div><div><span className="label">EMAIL </span>{user?.email}</div><div><span className="label">USER ID </span><span className="text-fg-3">{user?.id}</span></div></div></Panel>
        )}
      </div>
      <Toast msg={toast?.msg ?? null} tone={toast?.tone} />
    </div>
  )
}
