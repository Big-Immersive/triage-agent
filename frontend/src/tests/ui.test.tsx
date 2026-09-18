import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { StatusDot, TermTable } from '@/components/ui'

describe('StatusDot', () => {
  it('maps agent statuses to spec labels', () => {
    render(<div><StatusDot status="tool_call" /><StatusDot status="human_input" /><StatusDot status="idle" /></div>)
    expect(screen.getByText('TOOL CALL')).toBeInTheDocument()
    expect(screen.getByText('HUMAN INPUT')).toBeInTheDocument()
    expect(screen.getByText('IDLE')).toBeInTheDocument()
  })
  it('amber for human input, red for error', () => {
    render(<div><StatusDot status="human_input" /><StatusDot status="error" /></div>)
    expect(screen.getByText('HUMAN INPUT').parentElement?.className).toContain('text-warn')
    expect(screen.getByText('ERROR').parentElement?.className).toContain('text-danger')
  })
})

describe('TermTable', () => {
  it('renders both the table and the stacked variant', () => {
    render(<TermTable cols={['A', 'B']} rows={[['x', 'y']]} />)
    expect(screen.getAllByText('x')).toHaveLength(2)   // table row + stacked card
    expect(screen.getAllByText('A')).toHaveLength(2)
  })
  it('shows the empty message', () => {
    render(<TermTable cols={['A']} rows={[]} empty="nothing" />)
    expect(screen.getByText('nothing')).toBeInTheDocument()
  })
})
