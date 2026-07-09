import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import * as api from '../api'
import type { InstallationSearchItem, InstallationSearchResponse } from '../types'
import { InstallationsTable } from './InstallationsTable'

vi.mock('../api')

function item(overrides: Partial<InstallationSearchItem> = {}): InstallationSearchItem {
  return {
    id: 'inst-1',
    environment_id: 'env-1',
    environment_name: 'proj1',
    host_or_cluster: 'proj1.example.com',
    source_type: 'rpm',
    artifact_id: 'art-1',
    artifact_name: 'nginx',
    artifact_version: '1.2.3',
    status: 'active',
    first_seen_at: '2026-01-01T00:00:00Z',
    last_seen_at: '2026-01-02T00:00:00Z',
    removed_at: null,
    source_of_removal: null,
    ...overrides,
  }
}

function searchResponse(items: InstallationSearchItem[], total = items.length): InstallationSearchResponse {
  return { items, total, limit: 20, offset: 0 }
}

/** Mocks the 4 parallel KPI calls (limit=1, distinguished by sourceType/includeRemoved)
 * plus the main table call (limit=20), matching InstallationsTable's actual call shape. */
function mockApi({
  tableItems = [] as InstallationSearchItem[],
  tableTotal,
  active = 0,
  rpm = 0,
  kubernetes = 0,
  totalWithRemoved = active,
}: {
  tableItems?: InstallationSearchItem[]
  tableTotal?: number
  active?: number
  rpm?: number
  kubernetes?: number
  totalWithRemoved?: number
} = {}) {
  vi.mocked(api.listEnvironments).mockResolvedValue({ items: [], total: 0, limit: 200, offset: 0 })
  vi.mocked(api.searchInstallations).mockImplementation(async (params) => {
    if (params.limit === 1) {
      if (params.sourceType === 'rpm') return searchResponse([], rpm)
      if (params.sourceType === 'kubernetes') return searchResponse([], kubernetes)
      if (params.includeRemoved) return searchResponse([], totalWithRemoved)
      return searchResponse([], active)
    }
    return searchResponse(tableItems, tableTotal ?? tableItems.length)
  })
}

beforeEach(() => {
  localStorage.clear()
})

describe('InstallationsTable', () => {
  it('renders fetched installations with their badges', async () => {
    mockApi({
      tableItems: [
        item({ id: 'a', artifact_name: 'nginx', artifact_version: '1.2.3', source_type: 'rpm', status: 'active' }),
        item({ id: 'b', artifact_name: 'my-api', artifact_version: '2.0.0', source_type: 'kubernetes', status: 'removed' }),
      ],
      active: 2,
      rpm: 1,
      kubernetes: 1,
    })

    render(<InstallationsTable />)

    expect(await screen.findByText('nginx')).toBeInTheDocument()
    expect(screen.getByText('my-api')).toBeInTheDocument()
    expect(screen.getByText('1.2.3')).toBeInTheDocument()
    expect(screen.getByText('2.0.0')).toBeInTheDocument()
    expect(screen.getByText('Aktiv')).toBeInTheDocument()
    expect(screen.getByText('Borttagen')).toBeInTheDocument()
  })

  it('shows the empty state when there are no results', async () => {
    mockApi({ tableItems: [] })
    render(<InstallationsTable />)
    expect(await screen.findByText('Inga träffar.')).toBeInTheDocument()
  })

  it('shows an error message when the search request fails', async () => {
    vi.mocked(api.listEnvironments).mockResolvedValue({ items: [], total: 0, limit: 200, offset: 0 })
    vi.mocked(api.searchInstallations).mockImplementation(async (params) => {
      if (params.limit === 1) return searchResponse([], 0)
      throw new Error('500 Internal Server Error')
    })

    render(<InstallationsTable />)
    expect(await screen.findByText(/Kunde inte hämta data: 500 Internal Server Error/)).toBeInTheDocument()
  })

  it('renders KPI tiles with the counts per source type and removed', async () => {
    mockApi({ tableItems: [item()], active: 5, rpm: 3, kubernetes: 2, totalWithRemoved: 8 })
    const { container } = render(<InstallationsTable />)

    await screen.findByText('nginx')
    // scoped to the KPI row: "RPM"/"Kubernetes" also appear as <option> labels in the source-type filter
    const statRow = within(container.querySelector('.stat-row') as HTMLElement)
    expect(statRow.getByText('Aktiva installationer').previousSibling).toHaveTextContent('5')
    expect(statRow.getByText('RPM').previousSibling).toHaveTextContent('3')
    expect(statRow.getByText('Kubernetes').previousSibling).toHaveTextContent('2')
    // withRemoved.total (8) - active.total (5) = 3 removed
    expect(statRow.getByText('Borttagna').previousSibling).toHaveTextContent('3')
  })

  it('toggles sort direction and refetches when a header is clicked twice', async () => {
    const user = userEvent.setup()
    mockApi({ tableItems: [item()] })
    render(<InstallationsTable />)
    await screen.findByText('nginx')

    const header = screen.getByText('Artefakt')
    await user.click(header)

    await waitFor(() => {
      const lastCall = vi.mocked(api.searchInstallations).mock.calls.at(-1)![0]
      expect(lastCall.sortBy).toBe('artifact_name')
      expect(lastCall.sortDir).toBe('asc')
    })

    await user.click(header)

    await waitFor(() => {
      const lastCall = vi.mocked(api.searchInstallations).mock.calls.at(-1)![0]
      expect(lastCall.sortBy).toBe('artifact_name')
      expect(lastCall.sortDir).toBe('desc')
    })
  })

  it('requires an API key before allowing a delete', async () => {
    const user = userEvent.setup()
    mockApi({ tableItems: [item({ id: 'a', status: 'active' })] })
    render(<InstallationsTable />)
    await screen.findByText('nginx')

    await user.click(screen.getByLabelText('Markera nginx i proj1'))
    await user.click(screen.getByRole('button', { name: 'Verkställ' }))

    expect(await screen.findByText('Ange en API-nyckel för att kunna ta bort installationer.')).toBeInTheDocument()
    expect(api.deleteInstallation).not.toHaveBeenCalled()
  })

  it('deletes selected installations after confirmation when an API key is set', async () => {
    const user = userEvent.setup()
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    vi.mocked(api.deleteInstallation).mockResolvedValue(undefined)
    mockApi({ tableItems: [item({ id: 'a', status: 'active' })] })
    render(<InstallationsTable />)
    await screen.findByText('nginx')

    await user.type(screen.getByPlaceholderText('API-nyckel (för borttagning)'), 'secret-key')
    await user.click(screen.getByLabelText('Markera nginx i proj1'))
    await user.click(screen.getByRole('button', { name: 'Verkställ' }))

    await waitFor(() => {
      expect(api.deleteInstallation).toHaveBeenCalledWith('a', 'secret-key')
    })
    expect(localStorage.getItem('loggboken-api-key')).toBe('secret-key')
  })

  it('does not delete when the confirmation dialog is dismissed', async () => {
    const user = userEvent.setup()
    vi.spyOn(window, 'confirm').mockReturnValue(false)
    mockApi({ tableItems: [item({ id: 'a', status: 'active' })] })
    render(<InstallationsTable />)
    await screen.findByText('nginx')

    await user.type(screen.getByPlaceholderText('API-nyckel (för borttagning)'), 'secret-key')
    await user.click(screen.getByLabelText('Markera nginx i proj1'))
    await user.click(screen.getByRole('button', { name: 'Verkställ' }))

    expect(api.deleteInstallation).not.toHaveBeenCalled()
  })

  it('paginates using the Next/Previous buttons', async () => {
    const user = userEvent.setup()
    mockApi({ tableItems: [item()], tableTotal: 50 })
    render(<InstallationsTable />)
    await screen.findByText('nginx')

    const prevButton = screen.getByRole('button', { name: /Föregående/ })
    const nextButton = screen.getByRole('button', { name: /Nästa/ })
    expect(prevButton).toBeDisabled()
    expect(nextButton).not.toBeDisabled()

    await user.click(nextButton)

    await waitFor(() => {
      const lastCall = vi.mocked(api.searchInstallations).mock.calls.at(-1)![0]
      expect(lastCall.offset).toBe(20)
    })
  })
})
