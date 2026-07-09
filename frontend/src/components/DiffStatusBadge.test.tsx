import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { DiffStatus } from '../types'
import { DiffStatusBadge } from './DiffStatusBadge'

describe('DiffStatusBadge', () => {
  const cases: [DiffStatus, string][] = [
    ['same', 'Samma'],
    ['different', 'Olika version'],
    ['left_only', 'Bara vänster'],
    ['right_only', 'Bara höger'],
  ]

  it.each(cases)('renders %s as "%s"', (status, label) => {
    render(<DiffStatusBadge status={status} />)
    const badge = screen.getByText(label)
    expect(badge).toHaveClass(`badge-diff-${status}`)
  })
})
