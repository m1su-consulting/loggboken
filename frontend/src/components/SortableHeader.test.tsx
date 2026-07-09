import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { SortableHeader } from './SortableHeader'

function renderHeader(props: Partial<React.ComponentProps<typeof SortableHeader>> = {}) {
  const onSort = vi.fn()
  render(
    <table>
      <thead>
        <tr>
          <SortableHeader
            field="artifact_name"
            label="Artefakt"
            currentSortBy="last_seen_at"
            currentSortDir="desc"
            onSort={onSort}
            {...props}
          />
        </tr>
      </thead>
    </table>,
  )
  return { onSort }
}

describe('SortableHeader', () => {
  it('calls onSort with its field when clicked', async () => {
    const user = userEvent.setup()
    const { onSort } = renderHeader()
    await user.click(screen.getByText('Artefakt'))
    expect(onSort).toHaveBeenCalledWith('artifact_name')
  })

  it('is not marked active or sorted when it is not the current sort field', () => {
    renderHeader({ currentSortBy: 'last_seen_at' })
    const th = screen.getByRole('columnheader')
    expect(th).not.toHaveClass('active')
    expect(th).toHaveAttribute('aria-sort', 'none')
  })

  it('shows an ascending indicator when active and sorted ascending', () => {
    renderHeader({ currentSortBy: 'artifact_name', currentSortDir: 'asc' })
    const th = screen.getByRole('columnheader')
    expect(th).toHaveClass('active')
    expect(th).toHaveAttribute('aria-sort', 'ascending')
    expect(th).toHaveTextContent('▲')
  })

  it('shows a descending indicator when active and sorted descending', () => {
    renderHeader({ currentSortBy: 'artifact_name', currentSortDir: 'desc' })
    const th = screen.getByRole('columnheader')
    expect(th).toHaveAttribute('aria-sort', 'descending')
    expect(th).toHaveTextContent('▼')
  })
})
