import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { StatTile } from './StatTile'

describe('StatTile', () => {
  it('renders the label and value', () => {
    render(<StatTile label="Aktiva installationer" value={42} />)
    expect(screen.getByText('42')).toBeInTheDocument()
    expect(screen.getByText('Aktiva installationer')).toBeInTheDocument()
  })

  it('accepts a string value (e.g. for empty states)', () => {
    render(<StatTile label="Borttagna" value="—" />)
    expect(screen.getByText('—')).toBeInTheDocument()
  })

  it('sets the --stat-accent CSS variable when accent is given', () => {
    const { container } = render(<StatTile label="RPM" value={1} accent="var(--color-rpm)" />)
    const tile = container.querySelector('.stat-tile') as HTMLElement
    expect(tile.style.getPropertyValue('--stat-accent')).toBe('var(--color-rpm)')
  })

  it('does not set the accent variable when none is given', () => {
    const { container } = render(<StatTile label="RPM" value={1} />)
    const tile = container.querySelector('.stat-tile') as HTMLElement
    expect(tile.getAttribute('style')).toBeNull()
  })
})
