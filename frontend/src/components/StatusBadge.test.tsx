import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { StatusBadge } from './StatusBadge'

describe('StatusBadge', () => {
  it('renders the Swedish label and status class for active', () => {
    render(<StatusBadge status="active" />)
    const badge = screen.getByText('Aktiv')
    expect(badge).toHaveClass('badge', 'badge-active')
  })

  it('renders the Swedish label and status class for removed', () => {
    render(<StatusBadge status="removed" />)
    const badge = screen.getByText('Borttagen')
    expect(badge).toHaveClass('badge', 'badge-removed')
  })
})
