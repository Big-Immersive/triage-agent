import { createRootRouteWithContext, Outlet, Link } from '@tanstack/react-router'
import type { QueryClient } from '@tanstack/react-query'

export const Route = createRootRouteWithContext<{ queryClient: QueryClient }>()({
  component: () => <Outlet />,
  notFoundComponent: () => (
    <div className="flex h-full items-center justify-center">
      <div className="panel px-6 py-6 text-center">
        <div className="text-fg-3"><span className="text-neon">$</span> cd {location.pathname}</div>
        <div className="mt-2 text-fg-2">No such file or directory.</div>
        <Link to="/dashboard" className="mt-4 inline-block text-neon">[ RETURN TO CONTROL_CENTER ]</Link>
      </div>
    </div>
  ),
})
