import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { SourceTypeBadge } from './SourceTypeBadge'

describe('SourceTypeBadge', () => {
  it('renders the source type as its own text and a matching class', () => {
    render(<SourceTypeBadge sourceType="rpm" />)
    const badge = screen.getByText('rpm')
    expect(badge).toHaveClass('badge', 'badge-source', 'badge-source-rpm')
  })

  it('supports arbitrary source types, not just rpm/kubernetes', () => {
    render(<SourceTypeBadge sourceType="kubernetes" />)
    expect(screen.getByText('kubernetes')).toHaveClass('badge-source-kubernetes')
  })
})
