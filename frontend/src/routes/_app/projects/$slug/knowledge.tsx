import { createFileRoute } from '@tanstack/react-router'
import { useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Btn, ConfirmModal, PromptHeader, Toast, useToast } from '@/components/ui'
import { KnowledgeList, KnowledgeUploader } from '@/components/features/KnowledgeUploader'
import { useActiveProject } from '@/components/layout/ProjectShell'
import { del, post } from '@/api/client'
import { qk, useKnowledge } from '@/api/queries'
import type { KnowledgeItem } from '@/api/types'

export const Route = createFileRoute('/_app/projects/$slug/knowledge')({ component: Knowledge })

function Knowledge() {
  const p = useActiveProject()
  const { data } = useKnowledge(p.id)
  const qc = useQueryClient()
  const { toast, show, error } = useToast()
  const [remove, setRemove] = useState<KnowledgeItem | null>(null)
  const [busy, setBusy] = useState(false)
  const [showUploader, setShowUploader] = useState(true)
  const refresh = () => qc.invalidateQueries({ queryKey: qk.knowledge(p.id) })
  async function reindex(k: KnowledgeItem) { try { await post(`/api/projects/${p.id}/knowledge/${k.id}/reindex`); show(`reindexing ${k.name}`); refresh() } catch (e) { error(e) } }
  async function doRemove() { if (!remove) return; setBusy(true); try { await del(`/api/projects/${p.id}/knowledge/${remove.id}`); setRemove(null); refresh() } catch (e) { error(e) } finally { setBusy(false) } }
  const ready = data?.filter((k) => k.status === 'ready').length ?? 0
  return (
    <div>
      <PromptHeader title="knowledge_base" subtitle={`${data?.length ?? 0} sources · ${ready} ready. Structured sources (tracker, crash log, releases, CODEOWNERS) power the agents' tools; documents are searchable via search_knowledge.`} right={<Btn onClick={() => setShowUploader((s) => !s)}>{showUploader ? 'hide uploader' : '* ADD SOURCES'}</Btn>} />
      {showUploader && <div className="mb-4"><KnowledgeUploader projectId={p.id} compact /></div>}
      <div className="panel"><KnowledgeList projectId={p.id} items={data ?? []} onDelete={setRemove} onReindex={reindex} /></div>
      <ConfirmModal open={!!remove} onClose={() => setRemove(null)} onConfirm={doRemove} title="remove_knowledge" danger loading={busy} body={<p>Remove <b className="text-fg-1">{remove?.name}</b> from the knowledge base? Its embeddings are deleted; the uploaded file stays under /files.</p>} />
      <Toast msg={toast?.msg ?? null} tone={toast?.tone} />
    </div>
  )
}
