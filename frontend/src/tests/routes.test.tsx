import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { createMemoryHistory, createRouter, RouterProvider } from '@tanstack/react-router'
import { routeTree } from '@/routeTree.gen'

// Every route module loads (route tree import pulls them all in) and the login screen renders.
describe('routes', () => {
  it('route tree builds and /login renders', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({}), { status: 200, headers: { 'content-type': 'application/json' } })))
    const queryClient = new QueryClient()
    const router = createRouter({ routeTree, context: { queryClient }, history: createMemoryHistory({ initialEntries: ['/login'] }) })
    render(<QueryClientProvider client={queryClient}><RouterProvider router={router} /></QueryClientProvider>)
    expect(await screen.findByText('authenticate')).toBeInTheDocument()
    expect(screen.getByText('[ AUTHENTICATE ]')).toBeInTheDocument()
  })
  it('unauthenticated /projects redirects to /login', async () => {
    const queryClient = new QueryClient()
    const router = createRouter({ routeTree, context: { queryClient }, history: createMemoryHistory({ initialEntries: ['/projects'] }) })
    render(<QueryClientProvider client={queryClient}><RouterProvider router={router} /></QueryClientProvider>)
    expect(await screen.findByText('authenticate')).toBeInTheDocument()
  })
})
