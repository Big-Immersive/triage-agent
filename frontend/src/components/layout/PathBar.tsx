import { Link } from '@tanstack/react-router'
import { Fragment } from 'react'

/** `~/projects/payments-platform/runs/RUN_8FA21` — a terminal path that works as breadcrumbs. */
export function PathBar({ path }: { path: string }) {
  const parts = path.split('/').filter(Boolean)
  const crumbs = parts.map((p, i) => ({ label: p, to: '/' + parts.slice(0, i + 1).join('/') }))
  return (
    <div className="flex min-w-0 items-center gap-1 text-[11px] text-fg-3 overflow-x-auto whitespace-nowrap">
      <span className="text-neon">~</span>
      {crumbs.map((c, i) => (
        <Fragment key={c.to}>
          <span>/</span>
          {i === crumbs.length - 1 ? <span className="text-fg-1">{c.label}</span> : <Link to={c.to} className="hover:text-fg-1">{c.label}</Link>}
        </Fragment>
      ))}
      {crumbs.length === 0 && <span>/</span>}
    </div>
  )
}
