import { Link } from '@tanstack/react-router'
import { useState } from 'react'
import { clsx } from 'clsx'
import { Btn, Field, Select, StatusDot } from '@/components/ui'
import { ago } from '@/utils/format'
import type { Approval } from '@/api/types'

export function ApprovalCard({ a, slug, onDecide, busy }: { a: Approval; slug: string; onDecide?: (id: string, action: 'approve' | 'reject' | 'modify', severity?: string) => void; busy?: boolean }) {
  const [modify, setModify] = useState(false)
  const [sev, setSev] = useState<string>((a.details.severity as string) ?? 'high')
  const pending = a.status === 'pending'
  return (
    <div className={clsx('panel p-3 anim-fade', pending && 'border-warn/50 glow-amber')}>
      <div className="mb-2 flex items-center justify-between">
        <span className={clsx('font-medium tracking-wider', pending ? 'text-warn' : 'text-fg-2')}>{a.id}</span>
        <StatusDot status={a.status} size="md" />
      </div>
      <Field k="AGENT" v={a.agent_name} />
      <Field k="ACTION" v={a.action} mono={false} />
      <Field k="REASON" v={a.reason} />
      {a.confidence != null && <Field k="CONFIDENCE" v={<span className={a.confidence < 0.7 ? 'text-warn' : ''}>{a.confidence.toFixed(2)}</span>} />}
      {a.details.component != null && <Field k="COMPONENT" v={`${a.details.component} · owner ${a.details.owner ?? '—'}`} />}
      {a.details.evidence != null && <Field k="EVIDENCE" v={String(a.details.evidence)} mono={false} />}
      <Field k="RUN" v={<Link to="/projects/$slug/runs/$runId" params={{ slug, runId: a.run_id }} className="text-neon hover:underline">{a.run_id}</Link>} />
      <Field k="REQUESTED" v={ago(a.requested_at)} />
      {pending && onDecide && (
        <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-line pt-3">
          <Btn tone="primary" loading={busy} onClick={() => onDecide(a.id, 'approve')}>[ APPROVE ]</Btn>
          {!modify ? <Btn tone="amber" onClick={() => setModify(true)}>[ MODIFY ]</Btn> : (
            <span className="flex items-center gap-2"><Select value={sev} onChange={(e) => setSev(e.target.value)} className="h-8! w-auto!"><option>low</option><option>medium</option><option>high</option><option>critical</option></Select><Btn tone="amber" loading={busy} onClick={() => onDecide(a.id, 'modify', sev)}>apply severity</Btn></span>
          )}
          <Btn tone="danger" loading={busy} onClick={() => onDecide(a.id, 'reject')}>[ REJECT ]</Btn>
        </div>
      )}
      {!pending && a.response && <div className="mt-2 flex items-center justify-between text-[11px] text-fg-3"><span>answer: {String(a.response.answer)} · {ago(a.resolved_at)}</span>{a.ticket_id && <Link to="/projects/$slug/tickets" params={{ slug }} className="text-neon hover:underline">→ ticket {a.ticket_id}</Link>}</div>}
    </div>
  )
}
