import { createFileRoute } from '@tanstack/react-router'
import { useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { clsx } from 'clsx'
import { Btn, Input, Modal, PromptHeader, StatusDot, TextArea, Toast, useToast } from '@/components/ui'
import { useActiveProject } from '@/components/layout/ProjectShell'
import { post, put } from '@/api/client'
import { qk, useIntegrations } from '@/api/queries'
import { ago } from '@/utils/format'
import type { Integration } from '@/api/types'

export const Route = createFileRoute('/_app/projects/$slug/integrations')({ component: Integrations })

function Integrations() {
  const p = useActiveProject()
  const { data } = useIntegrations(p.id)
  const qc = useQueryClient()
  const { toast, show, error } = useToast()
  const [edit, setEdit] = useState<Integration | null>(null)
  const [guide, setGuide] = useState<Integration | null>(null)
  const [cfg, setCfg] = useState<Record<string, string>>({})
  const [busy, setBusy] = useState<string | null>(null)
  const [testResult, setTestResult] = useState<{ ok: boolean; message: string } | null>(null)
  const [syncing, setSyncing] = useState<string | null>(null)
  async function syncNow(i: Integration) {
    setSyncing(i.provider)
    try { const r = await post<{ result: string }>(`/api/projects/${p.id}/integrations/${i.provider}/sync`); show(`${i.label}: ${r.result}`); qc.invalidateQueries({ queryKey: qk.integrations(p.id) }) } catch (e) { error(e) } finally { setSyncing(null) }
  }
  function copy(text: string) { navigator.clipboard?.writeText(text).then(() => show('copied')).catch(() => show(text, 'amber')) }

  function open(i: Integration) { setEdit(i); setTestResult(null); setCfg(Object.fromEntries([...i.fields, ...i.inbound.fields].map((f) => [f, i.secret_fields.includes(f) ? '' : String(i.config[f] ?? '')]))) }
  async function save(status: 'connected' | 'not_connected') {
    if (!edit) return
    setBusy('save')
    try { await put(`/api/projects/${p.id}/integrations/${edit.provider}`, { status, config: cfg }); show(`${edit.label} ${status.replace('_', ' ')}`); setEdit(null); qc.invalidateQueries({ queryKey: qk.integrations(p.id) }) } catch (e) { error(e) } finally { setBusy(null) }
  }
  async function test() {
    if (!edit) return
    setBusy('test'); setTestResult(null)
    try { setTestResult(await post(`/api/projects/${p.id}/integrations/${edit.provider}/test`, { status: 'connected', config: cfg })) } catch (e) { error(e) } finally { setBusy(null) }
  }
  const groups = ['issue tracker', 'notifications', 'automation', 'telemetry', 'knowledge', 'tools']

  return (
    <div>
      <PromptHeader title="integrations" subtitle="External systems this project talks to. Each card explains what the integration does and exactly how to set it up. Credentials are stored per project, encrypted." />
      {groups.map((g) => {
        const items = (data ?? []).filter((i) => i.category === g)
        if (!items.length) return null
        return (
          <section key={g} className="mb-5">
            <div className="label mb-2">{g}</div>
            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
              {items.map((i) => {
                const lastErr = i.config._last_error as string | undefined
                return (
                  <div key={i.provider} className={clsx('panel hover-neon flex flex-col p-3', i.status === 'connected' && 'border-neon/30', i.status === 'error' && 'border-danger/40')}>
                    <div className="mb-2 flex items-center justify-between">
                      <span className="text-[13px] tracking-wider text-fg-1">{i.label}</span>
                      <span className={clsx('border px-1 text-[9px] tracking-wider', i.adapter === 'live' ? 'border-neon/40 text-neon' : 'border-line text-fg-3')}>{i.adapter === 'live' ? 'LIVE' : 'PLANNED'}</span>
                    </div>
                    <div className="grid grid-cols-[90px_1fr] gap-y-0.5 text-[12px]">
                      <span className="label">STATUS</span><StatusDot status={i.status} label={i.status === 'connected' ? 'CONNECTED' : i.status === 'error' ? 'ERROR' : 'NOT CONNECTED'} />
                      {i.fields.filter((f) => !i.secret_fields.includes(f)).slice(0, 2).map((f) => <span key={f} className="contents"><span className="label">{f.toUpperCase()}</span><span className="truncate-1 text-fg-2">{i.config[f] ? String(i.config[f]) : <span className="text-fg-3">—</span>}</span></span>)}
                      {i.events.length > 0 && <><span className="label">EVENTS</span><span className="truncate-1 text-fg-3">{i.events.join(', ')}</span></>}
                    </div>
                    <p className="mt-2 flex-1 text-[11px] text-fg-2 font-sans">{i.summary}</p>
                    <div className="mt-2 border-t border-line pt-2 text-[11px]">
                      <div className="flex items-center justify-between">
                        <span className="label">inbound · {i.inbound.mode === 'both' ? 'push + poll' : i.inbound.mode}</span>
                        <span className="text-fg-3">{i.inbound.count > 0 ? <span className="text-neon">{i.inbound.count} received</span> : 'nothing received yet'}</span>
                      </div>
                      {i.status !== 'not_connected' && i.inbound.url && (i.inbound.mode !== 'poll') && (
                        <div className="mt-1 flex items-center gap-1">
                          <code className="truncate-1 flex-1 border border-line bg-bg-0 px-1.5 py-0.5 text-[10px] text-fg-2" title={i.inbound.url}>{i.inbound.url}</code>
                          <Btn size="sm" onClick={() => copy(i.inbound.url!)}>copy</Btn>
                          {i.provider === 'slack' && <span className={i.inbound.verified ? 'text-neon' : 'text-warn'}>{i.inbound.verified ? '● VERIFIED' : '○ awaiting Slack challenge'}</span>}
                        </div>
                      )}
                      {i.status !== 'not_connected' && i.inbound.mode !== 'push' && (
                        <div className="mt-1 flex items-center justify-between gap-2">
                          <span className="truncate-1 text-fg-3" title={i.inbound.last_sync_result ?? ''}>{i.inbound.last_sync_at ? `synced ${ago(i.inbound.last_sync_at)} · ${i.inbound.last_sync_result ?? ''}` : 'first sync pending'}{i.inbound.next_sync_at && <span> · next {ago(i.inbound.next_sync_at).replace(' ago', '')}</span>}</span>
                          <Btn size="sm" loading={syncing === i.provider} onClick={() => syncNow(i)}>SYNC NOW</Btn>
                        </div>
                      )}
                      {i.status === 'not_connected' && <div className="mt-1 text-fg-3 font-sans">{i.inbound.summary}</div>}
                    </div>
                    {lastErr && <div className="mt-2 border border-danger/30 bg-danger/5 px-2 py-1 text-[10px] text-danger">last delivery failed: {lastErr}</div>}
                    {i.connected_at && <div className="mt-1 text-[10px] text-fg-3">connected {ago(i.connected_at)}</div>}
                    <div className="mt-3 flex gap-2">
                      <Btn size="sm" tone={i.status === 'connected' ? 'ghost' : 'primary'} onClick={() => open(i)}>[ {i.status === 'connected' ? 'CONFIGURE' : 'CONNECT'} ]</Btn>
                      <Btn size="sm" onClick={() => setGuide(i)}>how it works</Btn>
                    </div>
                  </div>
                )
              })}
            </div>
          </section>
        )
      })}

      <Modal open={!!guide} onClose={() => setGuide(null)} title={`${guide?.provider} — how it works`} wide>
        {guide && (
          <div className="max-h-[70vh] overflow-y-auto">
            <div className="mb-3 flex items-center justify-between">
              <span className="text-[13px] text-fg-1 font-sans">{guide.summary}</span>
              <Btn size="sm" tone="primary" onClick={() => { const g = guide; setGuide(null); open(g) }}>[ {guide.status === 'connected' ? 'CONFIGURE' : 'CONNECT'} ]</Btn>
            </div>
            <Guide i={guide} full />
          </div>
        )}
      </Modal>
      <Modal open={!!edit} onClose={() => setEdit(null)} title={`${edit?.provider}.config`} wide>
        {edit && (
          <div className="grid gap-5 md:grid-cols-[1fr_1fr]">
            <div className="space-y-3">
              <div className="label">credentials</div>
              {edit.fields.map((f) => {
                const meta = edit.field_meta[f]
                const secret = edit.secret_fields.includes(f)
                const stored = secret && !!edit.config[f]
                const long = f === 'service_account_json'
                return long ? (
                  <TextArea key={f} label={meta.label} rows={5} value={cfg[f] ?? ''} onChange={(e) => setCfg({ ...cfg, [f]: e.target.value })} placeholder={stored ? 'stored — leave blank to keep' : meta.help} />
                ) : (
                  <Input key={f} label={meta.label + (stored ? `  · saved ${String(edit.config[f])}` : '')} type={secret ? 'password' : 'text'} value={cfg[f] ?? ''} onChange={(e) => setCfg({ ...cfg, [f]: e.target.value })} placeholder={stored ? 'leave blank to keep the saved value' : meta.help} hint={!stored ? meta.help : undefined} autoComplete="off" spellCheck={false} />
                )
              })}
              {edit.inbound.fields.length > 0 && <>
                <div className="label pt-2">inbound ({edit.inbound.mode === 'both' ? 'push + poll' : edit.inbound.mode})</div>
                {edit.inbound.fields.map((f) => {
                  const meta = edit.inbound.field_meta[f]
                  const secret = edit.secret_fields.includes(f)
                  const stored = secret && !!edit.config[f]
                  return <Input key={f} label={meta.label + (stored ? `  · saved ${String(edit.config[f])}` : '')} type={secret ? 'password' : 'text'} value={cfg[f] ?? ''} onChange={(e) => setCfg({ ...cfg, [f]: e.target.value })} placeholder={stored ? 'leave blank to keep the saved value' : meta.help} hint={!stored ? meta.help : undefined} autoComplete="off" spellCheck={false} />
                })}
              </>}
              {edit.inbound.url && edit.inbound.mode !== 'poll' && <div className="text-[11px]"><span className="label">inbound url </span><code className="break-all text-fg-2">{edit.inbound.url}</code> <Btn size="sm" onClick={() => copy(edit.inbound.url!)}>copy</Btn></div>}
              {!edit.inbound.url && edit.inbound.mode !== 'poll' && <div className="text-[11px] text-fg-3 font-sans">The inbound URL is generated when you CONNECT.</div>}
              <div className="flex flex-wrap items-center gap-2 border-t border-line pt-3">
                <Btn onClick={test} loading={busy === 'test'}>TEST</Btn>
                <span className="text-[10px] text-fg-3 font-sans">{edit.test}</span>
              </div>
              {testResult && <div className={clsx('border px-2 py-1.5 text-[11px] whitespace-pre-wrap', testResult.ok ? 'border-neon/40 text-neon' : 'border-danger/40 text-danger')}>{testResult.ok ? '● ' : '✖ '}{testResult.message}</div>}
              <div className="flex justify-between gap-2 pt-1">
                <Btn tone="danger" onClick={() => save('not_connected')} loading={busy === 'save'}>disconnect</Btn>
                <span className="flex gap-2"><Btn onClick={() => setEdit(null)}>cancel</Btn><Btn tone="primary" onClick={() => save('connected')} loading={busy === 'save'}>[ CONNECT ]</Btn></span>
              </div>
            </div>
            <div className="max-h-[70vh] overflow-y-auto border-l border-line pl-5"><Guide i={edit} full /></div>
          </div>
        )}
      </Modal>
      <Toast msg={toast?.msg ?? null} tone={toast?.tone} />
    </div>
  )
}

function Guide({ i, full }: { i: Integration; full?: boolean }) {
  return (
    <div className={clsx('space-y-4 font-sans', full ? 'text-[12px]' : 'text-[11px] mt-3 border-t border-line pt-3')}>
      {i.adapter === 'planned' && <div className="border border-warn/40 bg-warn/5 px-2 py-1 text-warn">Adapter planned: settings are stored and validated by TEST, but nothing is sent or imported yet. The guide explains the interim workflow.</div>}
      <div>
        <div className="label mb-1">how it works</div>
        <ul className="list-disc space-y-1 pl-4 text-fg-2">{i.how_it_works.map((h, k) => <li key={k}>{h}</li>)}</ul>
      </div>
      <div>
        <div className="label mb-1">setup — step by step</div>
        <ol className="list-decimal space-y-1 pl-4 text-fg-1">{i.steps.map((s, k) => <li key={k}>{s}</li>)}</ol>
      </div>
      <div>
        <div className="label mb-1">fields</div>
        <ul className="space-y-0.5 text-fg-2">{i.fields.map((f) => <li key={f}><code className="text-fg-1">{f}</code> — {i.field_meta[f].label}{i.field_meta[f].help ? `: ${i.field_meta[f].help}` : ''}{i.secret_fields.includes(f) && <span className="text-fg-3"> (secret, encrypted at rest)</span>}</li>)}</ul>
      </div>
      <div className="border-t border-line pt-3">
        <div className="label mb-1">inbound — how triage reads from {i.label.toLowerCase()} ({i.inbound.mode === 'both' ? 'push + poll' : i.inbound.mode === 'push' ? 'push: instant, event-driven' : 'poll: read on a schedule'})</div>
        <p className="mb-2 text-fg-2">{i.inbound.summary}</p>
        <ol className="list-decimal space-y-1 pl-4 text-fg-1">{i.inbound.steps.map((s, k) => <li key={k}>{s}</li>)}</ol>
        {i.inbound.fields.length > 0 && <ul className="mt-2 space-y-0.5 text-fg-2">{i.inbound.fields.map((f) => <li key={f}><code className="text-fg-1">{f}</code> — {i.inbound.field_meta[f].label}{i.inbound.field_meta[f].help ? `: ${i.inbound.field_meta[f].help}` : ''}</li>)}</ul>}
      </div>
      <div><span className="label">permissions </span><span className="text-fg-2">{i.permissions.join('; ')}</span></div>
      {i.events.length > 0 && <div><span className="label">events sent </span><span className="text-fg-2">{i.events.join(', ')}</span></div>}
      <div><span className="label">test button </span><span className="text-fg-2">{i.test}</span></div>
    </div>
  )
}
