import { useNavigate } from '@tanstack/react-router'
import { useEffect, useMemo, useState } from 'react'
import { clsx } from 'clsx'
import { Modal, StatusDot } from '@/components/ui'
import { useProjects } from '@/api/queries'
import { useUi } from '@/stores/ui'

export function ProjectSwitcher() {
  const { switcherOpen, setSwitcher } = useUi()
  const { data } = useProjects()
  const [q, setQ] = useState('')
  const [i, setI] = useState(0)
  const nav = useNavigate()
  const list = useMemo(() => (data ?? []).filter((p) => p.name.toLowerCase().includes(q.toLowerCase()) || p.slug.includes(q.toLowerCase())), [data, q])
  useEffect(() => { if (switcherOpen) { setQ(''); setI(0) } }, [switcherOpen])
  function go(slug: string) { setSwitcher(false); nav({ to: '/projects/$slug', params: { slug } }) }
  return (
    <Modal open={switcherOpen} onClose={() => setSwitcher(false)} title="switch_project">
      <input autoFocus value={q} onChange={(e) => { setQ(e.target.value); setI(0) }}
        onKeyDown={(e) => { if (e.key === 'ArrowDown') setI((x) => Math.min(x + 1, list.length - 1)); if (e.key === 'ArrowUp') setI((x) => Math.max(x - 1, 0)); if (e.key === 'Enter' && list[i]) go(list[i].slug) }}
        placeholder="$ cd ~/projects/" className="h-9 w-full border border-line bg-bg-0 px-3 text-fg-1 placeholder:text-fg-3" />
      <div className="mt-2 max-h-80 overflow-y-auto">
        {list.map((p, idx) => (
          <button key={p.id} onMouseEnter={() => setI(idx)} onClick={() => go(p.slug)} className={clsx('flex w-full items-center justify-between px-3 py-2 text-left text-[12px]', idx === i ? 'bg-neon/10 text-neon' : 'text-fg-2')}>
            <span>{p.icon} {p.slug}</span>
            <StatusDot status={p.status === 'active' ? 'running' : p.status} label={p.status.toUpperCase()} />
          </button>
        ))}
        {!list.length && <div className="px-3 py-4 text-fg-3">no projects match</div>}
      </div>
      <div className="mt-2 text-[10px] text-fg-3">↑↓ navigate · enter open · esc close</div>
    </Modal>
  )
}
