import { useEffect } from 'react'
import { useQuery, useQueryClient, type QueryClient } from '@tanstack/react-query'
import { get } from './client'
import { wsClient, type WsEvent } from './ws'
import type { Activity, Agent, Approval, FileRow, Graph, Health, Integration, KnowledgeItem, LlmSettings, Memory, Overview, Project, Run, RunEvent, Task, ToolInfo, Usage } from './types'

export const qk = {
  projects: ['projects'] as const,
  project: (id: string) => ['project', id] as const,
  overview: (id: string) => ['overview', id] as const,
  graph: (id: string) => ['graph', id] as const,
  agents: (id: string) => ['agents', id] as const,
  agentDetail: (id: string, a: string) => ['agent-detail', id, a] as const,
  tasks: (id: string) => ['tasks', id] as const,
  runs: (id: string) => ['runs', id] as const,
  run: (id: string, r: string) => ['run', id, r] as const,
  runEvents: (id: string, r: string) => ['run-events', id, r] as const,
  approvals: (id: string) => ['approvals', id] as const,
  memories: (id: string, type: string, q: string) => ['memories', id, type, q] as const,
  knowledge: (id: string) => ['knowledge', id] as const,
  files: (id: string) => ['files', id] as const,
  activity: (id: string, cat: string) => ['activity', id, cat] as const,
  integrations: (id: string) => ['integrations', id] as const,
  dashboard: ['dashboard'] as const,
  globalActivity: ['global-activity'] as const,
  health: ['health'] as const,
  tools: ['tools'] as const,
  models: ['models'] as const,
  llm: ['llm'] as const,
  usage: ['usage'] as const,
}

const P = (id: string) => `/api/projects/${id}`

export const useProjects = (archived = false) => useQuery({ queryKey: [...qk.projects, archived], queryFn: () => get<Project[]>(`/api/projects${archived ? '?include_archived=true' : ''}`) })
export const useProject = (id: string) => useQuery({ queryKey: qk.project(id), queryFn: () => get<Project>(P(id)), enabled: !!id })
export const useOverview = (id: string) => useQuery({ queryKey: qk.overview(id), queryFn: () => get<Overview>(`${P(id)}/overview`), enabled: !!id, refetchInterval: 15000 })
export const useGraph = (id: string) => useQuery({ queryKey: qk.graph(id), queryFn: () => get<Graph>(`${P(id)}/graph`), enabled: !!id })
export const useAgents = (id: string) => useQuery({ queryKey: qk.agents(id), queryFn: () => get<Agent[]>(`${P(id)}/agents`), enabled: !!id })
export const useAgentDetail = (id: string, a: string) => useQuery({ queryKey: qk.agentDetail(id, a), queryFn: () => get<AgentDetail>(`${P(id)}/agents/${a}/detail`), enabled: !!id && !!a })
export const useTasks = (id: string) => useQuery({ queryKey: qk.tasks(id), queryFn: () => get<Task[]>(`${P(id)}/tasks`), enabled: !!id })
export const useRuns = (id: string) => useQuery({ queryKey: qk.runs(id), queryFn: () => get<Run[]>(`${P(id)}/runs`), enabled: !!id })
export const useRun = (id: string, r: string) => useQuery({ queryKey: qk.run(id, r), queryFn: () => get<Run>(`${P(id)}/runs/${r}`), enabled: !!id && !!r })
export const useRunEvents = (id: string, r: string) => useQuery({ queryKey: qk.runEvents(id, r), queryFn: () => get<RunEvent[]>(`${P(id)}/runs/${r}/events`), enabled: !!id && !!r })
export const useApprovals = (id: string, status?: string) => useQuery({ queryKey: [...qk.approvals(id), status ?? 'all'], queryFn: () => get<Approval[]>(`${P(id)}/approvals${status ? `?status=${status}` : ''}`), enabled: !!id })
export const useMemories = (id: string, type = 'ALL', q = '') => useQuery({ queryKey: qk.memories(id, type, q), queryFn: () => get<Memory[]>(`${P(id)}/memories?type=${type}&q=${encodeURIComponent(q)}`), enabled: !!id })
// Polls while anything is indexing, as a fallback for a dropped WebSocket.
export const useKnowledge = (id: string) => useQuery({ queryKey: qk.knowledge(id), queryFn: () => get<KnowledgeItem[]>(`${P(id)}/knowledge`), enabled: !!id, refetchInterval: (q) => (q.state.data?.some((k) => k.status === 'indexing') ? 3000 : false) })
export const useFiles = (id: string) => useQuery({ queryKey: qk.files(id), queryFn: () => get<FileRow[]>(`${P(id)}/files`), enabled: !!id })
export const useActivity = (id: string, cat = 'ALL') => useQuery({ queryKey: qk.activity(id, cat), queryFn: () => get<Activity[]>(`${P(id)}/activity?category=${cat}&limit=300`), enabled: !!id })
export const useIntegrations = (id: string) => useQuery({ queryKey: qk.integrations(id), queryFn: () => get<Integration[]>(`${P(id)}/integrations`), enabled: !!id })
export const useDashboard = () => useQuery({ queryKey: qk.dashboard, queryFn: () => get<Dashboard>('/api/dashboard'), refetchInterval: 20000 })
export const useGlobalActivity = () => useQuery({ queryKey: qk.globalActivity, queryFn: () => get<Activity[]>('/api/activity?limit=200') })
export const useHealth = () => useQuery({ queryKey: qk.health, queryFn: () => get<Health>('/api/system/health'), refetchInterval: 30000, retry: false })
export const useTools = () => useQuery({ queryKey: qk.tools, queryFn: () => get<ToolInfo[]>('/api/system/tools'), staleTime: Infinity })
export const useModels = () => useQuery({ queryKey: qk.models, queryFn: () => get<{ openrouter: string[]; ollama: string[] }>('/api/system/models'), staleTime: 300000 })
export const useLlm = () => useQuery({ queryKey: qk.llm, queryFn: () => get<LlmSettings>('/api/me/llm') })
export const useUsage = () => useQuery({ queryKey: qk.usage, queryFn: () => get<Usage>('/api/me/usage') })

export interface AgentDetail {
  agent: Agent
  run: { id: string; status: string; task_id: string | null; current_agent: string | null } | null
  events: RunEvent[]
  memory_used: string[]
  files_accessed: string[]
  tools_called: { tool: string; count: number }[]
  handoffs: { run_id: string; ts: string; from: string; to: string }[]
}
export interface Dashboard {
  metrics: { total_projects: number; active_agents: number; active_runs: number; waiting_approvals: number }
  recent_projects: { id: string; name: string; slug: string; icon: string; status: string; last_activity_at: string }[]
  approval_queue: { id: string; project_id: string; project_slug: string; project_name: string; agent_name: string; action: string; confidence: number | null; run_id: string; requested_at: string }[]
  activity: (Activity & { project_slug: string })[]
}

/** Map a bus event to the queries it makes stale. Live data (run events, agent status) is
 *  also patched into the cache directly by the components that care, this is the safety net. */
function invalidateFor(qc: QueryClient, ev: WsEvent) {
  const pid = ev.channel
  const p = ev.payload
  switch (ev.type) {
    case 'run.status':
      qc.invalidateQueries({ queryKey: qk.runs(pid) }); qc.invalidateQueries({ queryKey: qk.tasks(pid) }); qc.invalidateQueries({ queryKey: qk.overview(pid) })
      qc.invalidateQueries({ queryKey: ['project'] }); qc.invalidateQueries({ queryKey: qk.projects }); qc.invalidateQueries({ queryKey: qk.graph(pid) })
      if (p.run_id) qc.invalidateQueries({ queryKey: qk.run(pid, String(p.run_id)) })
      break
    case 'run.event':
      if (p.run_id) qc.setQueryData<RunEvent[]>(qk.runEvents(pid, String(p.run_id)), (old) => {
        if (!old) return old
        const e = p as unknown as RunEvent
        return old.some((x) => x.seq === e.seq) ? old : [...old, e]
      })
      break
    case 'agent.status':
      qc.setQueryData<Agent[]>(qk.agents(pid), (old) => old?.map((a) => a.id === p.agent_id ? { ...a, status: p.status as Agent['status'], current_process: (p.current_process as string) ?? null, last_active_at: (p.last_active_at as string) ?? a.last_active_at } : a))
      qc.invalidateQueries({ queryKey: qk.graph(pid) }); qc.invalidateQueries({ queryKey: qk.overview(pid) })
      break
    case 'agent.handoff':
      qc.invalidateQueries({ queryKey: qk.graph(pid) }); break
    case 'approval.requested':
    case 'approval.resolved':
      qc.invalidateQueries({ queryKey: qk.approvals(pid) }); qc.invalidateQueries({ queryKey: ['project'] }); qc.invalidateQueries({ queryKey: qk.projects }); qc.invalidateQueries({ queryKey: qk.dashboard }); break
    case 'memory.updated':
      qc.invalidateQueries({ queryKey: ['memories', pid] }); qc.invalidateQueries({ queryKey: qk.overview(pid) }); break
    case 'knowledge.progress':
      qc.setQueryData<KnowledgeItem[]>(qk.knowledge(pid), (old) => old?.map((k) => k.id === p.id ? { ...k, status: p.status as KnowledgeItem['status'], progress: Number(p.progress), error: (p.error as string) ?? null } : k))
      if (p.status !== 'indexing') { qc.invalidateQueries({ queryKey: qk.knowledge(pid) }); qc.invalidateQueries({ queryKey: qk.overview(pid) }); qc.invalidateQueries({ queryKey: ['project'] }) }
      break
    case 'integration.synced':
      qc.invalidateQueries({ queryKey: qk.integrations(pid) }); qc.invalidateQueries({ queryKey: qk.tasks(pid) }); qc.invalidateQueries({ queryKey: qk.knowledge(pid) }); break
    case 'activity':
      qc.setQueryData<Overview>(qk.overview(pid), (old) => old ? { ...old, activity: [...old.activity.slice(-199), p as unknown as Activity] } : old)
      qc.invalidateQueries({ queryKey: ['activity', pid] })
      if (String(p.category) === 'FILE') qc.invalidateQueries({ queryKey: qk.files(pid) })
      break
  }
  if (ev.channel.startsWith('global:')) { qc.invalidateQueries({ queryKey: qk.dashboard }); qc.invalidateQueries({ queryKey: qk.globalActivity }); qc.invalidateQueries({ queryKey: qk.projects }) }
}

/** Subscribe to a project's live channel for the lifetime of the component. */
export function useProjectEvents(projectId: string | undefined, onEvent?: (ev: WsEvent) => void) {
  const qc = useQueryClient()
  useEffect(() => {
    if (!projectId) return
    return wsClient.subscribe(projectId, (ev) => { invalidateFor(qc, ev); onEvent?.(ev) })
  }, [projectId, qc, onEvent])
}

export function useGlobalEvents(onEvent?: (ev: WsEvent) => void) {
  const qc = useQueryClient()
  useEffect(() => wsClient.subscribe('global', (ev) => { invalidateFor(qc, ev); onEvent?.(ev) }), [qc, onEvent])
}
