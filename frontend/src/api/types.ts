export interface Project {
  id: string; name: string; slug: string; description: string; icon: string; instructions: string
  status: 'draft' | 'active' | 'archived'; config: Record<string, unknown>
  created_at: string; updated_at: string; last_activity_at: string
  agents_total: number; agents_online: number; runs_active: number; approvals_pending: number; memory_synced: boolean
}
export type AgentStatus = 'idle' | 'thinking' | 'running' | 'tool_call' | 'waiting' | 'human_input' | 'complete' | 'error' | 'disabled'
export interface Agent {
  id: string; project_id: string; name: string; role: string; description: string; instructions: string; model: string | null
  tools: string[]; permissions: Record<string, unknown>; can_handoff_to: string[]; enabled: boolean; position: number
  status: AgentStatus; current_process: string | null; last_active_at: string | null; created_at: string
}
export interface Task {
  id: string; project_id: string; external_id: string; source: string; author: string; title: string; text: string
  rating: number | null; received_at: string | null; meta: Record<string, string>; status: 'queued' | 'running' | 'done' | 'failed'
  result: RunResult | null; last_run_id: string | null; created_at: string; last_run_status?: string | null
}
export interface RunResult { outcome: string; category?: string; severity?: string | null; component?: string | null; ticket_id?: string | null; duplicate_of?: string | null; artifact?: string | null }
export type RunStatus = 'queued' | 'running' | 'waiting_approval' | 'complete' | 'error' | 'cancelled'
export interface Run {
  id: string; project_id: string; task_id: string | null; status: RunStatus; starting_agent: string | null; current_agent: string | null
  started_at: string; ended_at: string | null; duration_ms: number | null; tool_call_count: number; handoff_count: number
  approval_state: string; final_text: string | null; result: RunResult | null; error: string | null; auto_approve: boolean; task_external_id: string | null
}
export interface RunEvent {
  id: number; run_id: string; seq: number; ts: string; kind: string; actor: string; message: string
  input: Record<string, unknown> | null; output: { text?: string } | null; meta: Record<string, unknown>; duration_ms: number | null
}
export interface Approval {
  id: string; project_id: string; run_id: string; agent_name: string; action: string; reason: string; confidence: number | null
  details: Record<string, unknown>; status: 'pending' | 'approved' | 'modified' | 'rejected' | 'expired'; response: Record<string, unknown> | null
  requested_at: string; resolved_at: string | null; ticket_id?: string | null
}
export type MemoryType = 'PROJECT_CONTEXT' | 'DECISIONS' | 'REQUIREMENTS' | 'ARCHITECTURE' | 'KNOWN_ISSUES' | 'COMPLETED_WORK' | 'CURRENT_WORK' | 'AGENT_NOTES' | 'CUSTOM_MEMORY'
export const MEMORY_TYPES: MemoryType[] = ['PROJECT_CONTEXT', 'DECISIONS', 'REQUIREMENTS', 'ARCHITECTURE', 'KNOWN_ISSUES', 'COMPLETED_WORK', 'CURRENT_WORK', 'AGENT_NOTES', 'CUSTOM_MEMORY']
export interface Memory { id: string; project_id: string; type: MemoryType; source: string; content: string; related_run_id: string | null; pinned: boolean; created_at: string; updated_at: string }
export interface KnowledgeItem { id: string; project_id: string; name: string; kind: string; size_bytes: number; status: 'ready' | 'indexing' | 'failed'; progress: number; indexed_at: string | null; file_id: string | null; source_url: string | null; error: string | null; created_at: string }
export interface FileRow { id: string; project_id: string; path: string; name: string; kind: 'file' | 'dir'; size_bytes: number; mime: string; created_at: string; updated_at: string }
export interface Activity { id: number; project_id: string; ts: string; category: string; message: string; ref_type: string | null; ref_id: string | null; project_slug?: string; project_name?: string }
export interface Integration {
  provider: string; label: string; category: string; adapter: 'live' | 'planned'; functional: boolean; summary: string; note: string
  how_it_works: string[]; steps: string[]; fields: string[]; field_meta: Record<string, { label: string; help: string }>; secret_fields: string[]
  permissions: string[]; test: string; events: string[]
  status: 'connected' | 'not_connected' | 'error'; config: Record<string, unknown>; connected_at: string | null
  inbound: {
    mode: 'push' | 'poll' | 'both'; summary: string; steps: string[]; fields: string[]; field_meta: Record<string, { label: string; help: string }>; events: string[]
    url: string | null; verified: boolean; count: number; last_sync_at: string | null; last_sync_result: string | null; next_sync_at: string | null
  }
}
export interface ToolInfo { name: string; category: string; summary: string; side_effects: boolean; gated: boolean }
export interface LlmSettings {
  provider: 'openrouter' | 'ollama'; openrouter_key_masked: string | null; has_openrouter_key: boolean; ollama_url: string; default_model: string
  embed_provider: 'ollama' | 'openai_compatible'; embed_model: string; embed_base_url: string | null; embed_api_key_masked: string | null; has_embed_api_key: boolean; updated_at: string | null
}
export interface Overview {
  counts: Record<string, number>
  agents: { id: string; name: string; role: string; status: AgentStatus; current_process: string | null; enabled: boolean }[]
  activity: Activity[]
  recent_runs: { id: string; status: RunStatus; current_agent: string | null; started_at: string; duration_ms: number | null }[]
  memory_synced: boolean
}
export interface Health { online: boolean; replica: string; ws_clients: number; storage: string; run_workers: number; time: string; checks: Record<string, { ok: boolean; [k: string]: unknown }> }
export interface Graph {
  nodes: { id: string; agent_id: string; name: string; role: string; status: AgentStatus; current_process: string | null; enabled: boolean }[]
  edges: { id: string; source: string; target: string }[]
  active_run: string | null; active_agent: string | null; last_handoff: { from: string; to: string } | null
}
export interface Usage {
  total_cost_usd: number; total_prompt_tokens: number; total_completion_tokens: number
  projects: { project_id: string; name: string; slug: string; prompt_tokens: number; completion_tokens: number; cost_usd: number; runs: number; llm_calls: number }[]
  models: { provider: string; model: string; prompt_tokens: number; completion_tokens: number; cost_usd: number; llm_calls: number }[]
  recent: { id: number; ts: string; project_id: string; project_slug: string; run_id: string | null; agent_name: string; provider: string; model: string; prompt_tokens: number; completion_tokens: number; cost_usd: number; estimated: boolean }[]
}
