import { Link, createFileRoute } from '@tanstack/react-router'
import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { clsx } from 'clsx'
import { Btn, Field, Modal, PromptHeader, Tabs, TermTable } from '@/components/ui'
import { useActiveProject } from '@/components/layout/ProjectShell'
import { fileUrl, get } from '@/api/client'
import { useProjectEvents } from '@/api/queries'
import { ago } from '@/utils/format'

export const Route = createFileRoute('/_app/projects/$slug/tickets')({ component: Tickets })
const TABS = ['TICKETS', 'COMMENTS', 'REPLIES', 'DROPPED'] as const
type Tab = (typeof TABS)[number]
const KIND: Record<Tab, string> = { TICKETS: 'tickets', COMMENTS: 'comments', REPLIES: 'replies', DROPPED: 'dropped' }

interface Ticket { id: string; title: string; severity: string; component: string; owner: string; affected_versions: string[]; repro_steps: string[]; expected: string; actual: string; evidence: string; source_feedback: string[]; approved_by: string; external_links?: Record<string, string>; run_id: string | null; approval_state: string | null; _updated_at: string; _md_path: string; _file_id: string }
interface Other { ticket_id?: string; feedback_id: string; comment?: string; reply?: string; to?: string; category?: string; reason?: string; _updated_at: string; _md_path: string }

function Tickets() {
  const p = useActiveProject()
  const [tab, setTab] = useState<Tab>('TICKETS')
  const [open, setOpen] = useState<{ kind: string; name: string } | null>(null)
  const counts = useQuery({ queryKey: ['outputs-counts', p.id], queryFn: () => get<Record<string, number>>(`/api/projects/${p.id}/outputs/counts`) })
  const list = useQuery({ queryKey: ['outputs', p.id, tab], queryFn: () => get<(Ticket | Other)[]>(`/api/projects/${p.id}/outputs?kind=${KIND[tab]}`) })
  const detail = useQuery({ queryKey: ['output', p.id, open?.kind, open?.name], queryFn: () => get<{ data: Record<string, unknown>; markdown: string; md_file_id: string | null }>(`/api/projects/${p.id}/outputs/${open!.kind}/${open!.name}`), enabled: !!open })
  useProjectEvents(p.id, (ev) => { if (ev.type === 'run.status' || (ev.type === 'activity' && ev.payload.category === 'FILE')) { list.refetch(); counts.refetch() } })
  const c = counts.data ?? {}
  const sevTone = (s: string) => s === 'critical' ? 'text-danger' : s === 'high' ? 'text-warn' : s === 'medium' ? 'text-fg-1' : 'text-fg-2'

  return (
    <div>
      <PromptHeader title="tickets" subtitle="What the writer agent produced: new tickets (after approval when the gate applied), +1 comments on existing tickets, clarification replies, and items closed as not-a-bug." />
      <Tabs value={tab} onChange={setTab} options={TABS} counts={{ TICKETS: c.tickets, COMMENTS: c.comments, REPLIES: c.replies, DROPPED: c.dropped }} />
      <div className="panel mt-3">
        {tab === 'TICKETS' ? (
          <TermTable flexCol={1} cols={['TICKET', 'TITLE', 'SEVERITY', 'COMPONENT', 'OWNER', 'APPROVED BY', 'SOURCE', 'MIRRORED', 'RUN', 'CREATED']}
            keyOf={(i) => (list.data![i] as Ticket).id} onRowClick={(i) => setOpen({ kind: 'tickets', name: (list.data![i] as Ticket).id })}
            empty={<><span className="text-neon">$</span> ls /out/tickets — no tickets yet. Tickets appear here once a run creates one (and you approve it when the gate applies).</>}
            rows={((list.data ?? []) as Ticket[]).map((t) => [
              <span className="text-neon">{t.id}</span>, <span className="block truncate-1 font-sans text-fg-1" title={t.title}>{t.title}</span>,
              <span className={clsx('uppercase', sevTone(t.severity))}>{t.severity}</span>, t.component, t.owner,
              <span className={t.approved_by === 'human' ? 'text-warn' : 'text-fg-2'}>{t.approved_by === 'human' ? '● HUMAN' : 'auto'}</span>,
              t.source_feedback.join(', '),
              t.external_links && Object.keys(t.external_links).length ? <span className="flex gap-1">{Object.entries(t.external_links).map(([k, v]) => <a key={k} href={v} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()} className="text-neon hover:underline">{k} ↗</a>)}</span> : <span className="text-fg-3">—</span>,
              t.run_id ? <Link to="/projects/$slug/runs/$runId" params={{ slug: p.slug, runId: t.run_id }} onClick={(e) => e.stopPropagation()} className="text-fg-2 hover:text-neon">{t.run_id}</Link> : '—',
              ago(t._updated_at),
            ])} />
        ) : (
          <TermTable flexCol={2} cols={tab === 'COMMENTS' ? ['TICKET', 'FROM', 'COMMENT', 'CREATED'] : tab === 'REPLIES' ? ['FEEDBACK', 'TO', 'REPLY', 'CREATED'] : ['FEEDBACK', 'CATEGORY', 'REASON', 'CREATED']}
            keyOf={(i) => (list.data![i] as Other)._md_path} onRowClick={(i) => { const o = list.data![i] as Other; setOpen({ kind: KIND[tab], name: o._md_path.split('/').pop()!.replace(/\.md$/, '') }) }}
            empty={<><span className="text-neon">$</span> ls /out/{KIND[tab]} — nothing here yet</>}
            rows={((list.data ?? []) as Other[]).map((o) => tab === 'COMMENTS'
              ? [<span className="text-neon">{o.ticket_id}</span>, o.feedback_id, <span className="block truncate-1 font-sans text-fg-1">{o.comment}</span>, ago(o._updated_at)]
              : tab === 'REPLIES' ? [o.feedback_id, o.to ?? '—', <span className="block truncate-1 font-sans text-fg-1">{o.reply}</span>, ago(o._updated_at)]
              : [o.feedback_id, o.category ?? '—', <span className="block truncate-1 font-sans text-fg-1">{o.reason}</span>, ago(o._updated_at)])} />
        )}
      </div>
      <Modal open={!!open} onClose={() => setOpen(null)} title={open ? `${open.kind}/${open.name}` : ''} wide>
        {detail.data && (
          <div className="grid gap-4 md:grid-cols-[280px_1fr]">
            <div className="text-[12px]">
              {Object.entries(detail.data.data).filter(([k]) => !['repro_steps', 'expected', 'actual', 'evidence', 'external_links', 'comment', 'reply'].includes(k)).map(([k, v]) => <Field key={k} k={k.replace(/_/g, ' ').toUpperCase()} v={Array.isArray(v) ? v.join(', ') : String(v)} mono={false} />)}
              {detail.data.data.external_links != null && <Field k="MIRRORED" v={<span className="flex flex-col gap-0.5">{Object.entries(detail.data.data.external_links as Record<string, string>).map(([k, v]) => <a key={k} href={v} target="_blank" rel="noreferrer" className="text-neon hover:underline">{k} ↗ {v}</a>)}</span>} />}
              <div className="mt-3 flex gap-2">
                {detail.data.md_file_id && <a href={fileUrl(p.id, detail.data.md_file_id, true)}><Btn size="sm">download .md</Btn></a>}
                <Link to="/projects/$slug/files" params={{ slug: p.slug }}><Btn size="sm">open in files</Btn></Link>
              </div>
            </div>
            <pre className="max-h-[60vh] overflow-auto whitespace-pre-wrap border border-line bg-bg-0 p-3 text-[12px] leading-relaxed text-fg-2 font-sans">{detail.data.markdown}</pre>
          </div>
        )}
      </Modal>
    </div>
  )
}
