import { createFileRoute, useNavigate } from '@tanstack/react-router'
import { useMemo } from 'react'
import { Background, Handle, Position, ReactFlow, type Edge, type Node, type NodeProps } from '@xyflow/react'
import dagre from '@dagrejs/dagre'
import '@xyflow/react/dist/style.css'
import { clsx } from 'clsx'
import { PromptHeader, StatusDot } from '@/components/ui'
import { useActiveProject } from '@/components/layout/ProjectShell'
import { useGraph } from '@/api/queries'
import type { AgentStatus } from '@/api/types'

export const Route = createFileRoute('/_app/projects/$slug/graph')({ component: GraphPage })

type AgentNodeData = { name: string; role: string; status: AgentStatus; process: string | null; active: boolean; agentId: string; slug: string }

function AgentNode({ data }: NodeProps<Node<AgentNodeData>>) {
  const active = ['thinking', 'running', 'tool_call', 'waiting', 'human_input'].includes(data.status)
  return (
    <div className={clsx('w-[190px] border bg-bg-1 px-3 py-2 text-[12px] transition-shadow', active ? 'border-neon/70 glow-ring' : data.status === 'disabled' ? 'border-line opacity-50' : 'border-line-strong')}>
      <Handle type="target" position={Position.Top} className="!h-1.5 !w-1.5 !border-0 !bg-neon/60" />
      <div className="flex items-center justify-between"><span className="text-fg-1">{data.name}</span></div>
      <div className="mt-0.5"><StatusDot status={data.status} /></div>
      {data.process && <div className="mt-1 truncate-1 text-[10px] text-neon">{data.process}</div>}
      {!data.process && data.role && <div className="mt-1 truncate-1 text-[10px] text-fg-3">{data.role}</div>}
      <Handle type="source" position={Position.Bottom} className="!h-1.5 !w-1.5 !border-0 !bg-neon/60" />
    </div>
  )
}
const nodeTypes = { agent: AgentNode }

function GraphPage() {
  const p = useActiveProject()
  const { data } = useGraph(p.id)
  const nav = useNavigate()
  const { nodes, edges } = useMemo(() => {
    if (!data) return { nodes: [] as Node<AgentNodeData>[], edges: [] as Edge[] }
    const g = new dagre.graphlib.Graph().setDefaultEdgeLabel(() => ({}))
    g.setGraph({ rankdir: 'TB', nodesep: 40, ranksep: 70 })
    data.nodes.forEach((n) => g.setNode(n.id, { width: 190, height: 72 }))
    data.edges.forEach((e) => g.setEdge(e.source, e.target))
    dagre.layout(g)
    const nodes: Node<AgentNodeData>[] = data.nodes.map((n) => {
      const pos = g.node(n.id)
      return { id: n.id, type: 'agent', position: { x: pos.x - 95, y: pos.y - 36 }, data: { name: n.name, role: n.role, status: n.status, process: n.current_process, active: n.id === data.active_agent, agentId: n.agent_id, slug: p.slug } }
    })
    const lh = data.last_handoff
    const edges: Edge[] = data.edges.map((e) => {
      const hot = !!lh && lh.from === e.source && lh.to === e.target && !!data.active_run
      return { id: e.id, source: e.source, target: e.target, type: 'smoothstep', animated: false, className: hot ? 'edge-active' : undefined, style: { stroke: hot ? '#00ff66' : 'rgba(0,255,102,0.35)', strokeWidth: 1.2 } }
    })
    return { nodes, edges }
  }, [data, p.slug])

  return (
    <div className="flex h-[calc(100vh-180px)] flex-col">
      <PromptHeader title="agent_graph" subtitle="Handoff network, built from each agent's can_handoff_to. Live status from the current run." right={data?.active_run ? <span className="text-[11px] text-neon anim-pulse">● {data.active_run} · {data.active_agent}</span> : <span className="text-[11px] text-fg-3">no active run</span>} />
      <div className="panel min-h-0 flex-1">
        {!data?.nodes.length ? <div className="p-6 text-fg-3">no agents to draw</div> : (
          <ReactFlow nodes={nodes} edges={edges} nodeTypes={nodeTypes} fitView fitViewOptions={{ padding: 0.3 }} proOptions={{ hideAttribution: true }} nodesDraggable={false} nodesConnectable={false} elementsSelectable={false}
            onNodeClick={(_, n) => nav({ to: '/projects/$slug/agents/$agentId', params: { slug: p.slug, agentId: (n.data as AgentNodeData).agentId } })} colorMode="dark" style={{ background: 'transparent' }}>
            <Background color="rgba(0,255,102,0.08)" gap={32} />
          </ReactFlow>
        )}
      </div>
    </div>
  )
}
