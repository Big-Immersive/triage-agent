import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { createMemoryHistory, createRootRoute, createRouter, RouterProvider } from '@tanstack/react-router'
import { PathBar } from '@/components/layout/PathBar'

function withRouter(el: React.ReactNode) {
  const root = createRootRoute({ component: () => el })
  const router = createRouter({ routeTree: root, history: createMemoryHistory({ initialEntries: ['/'] }) })
  return <RouterProvider router={router as never} />
}

describe('PathBar', () => {
  it('renders a terminal path with clickable ancestors', async () => {
    render(withRouter(<PathBar path="/projects/payments-platform/runs/RUN_8FA21" />))
    expect(await screen.findByText('~')).toBeInTheDocument()
    expect(screen.getByText('RUN_8FA21')).toBeInTheDocument()
    expect(screen.getByText('payments-platform').closest('a')).toHaveAttribute('href', '/projects/payments-platform')
  })
})
