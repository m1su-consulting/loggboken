import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import * as api from '../api'
import type { EnvironmentDiffResponse } from '../types'
import { EnvironmentDiff } from './EnvironmentDiff'

vi.mock('../api')

function diffResponse(overrides: Partial<EnvironmentDiffResponse> = {}): EnvironmentDiffResponse {
  return {
    left: { query: 'proj1', source_type: 'rpm', matched_environments: ['proj1'] },
    right: { query: 'proj2', source_type: 'rpm', matched_environments: ['proj2'] },
    items: [],
    summary: { same: 0, different: 0, left_only: 0, right_only: 0 },
    ...overrides,
  }
}

beforeEach(() => {
  vi.mocked(api.listEnvironments).mockResolvedValue({ items: [], total: 0, limit: 200, offset: 0 })
})

describe('EnvironmentDiff', () => {
  it('prompts for two environments before fetching anything', () => {
    render(<EnvironmentDiff />)
    expect(
      screen.getByText('Fyll i två miljöer att jämföra — RPM och Kubernetes visas samtidigt.'),
    ).toBeInTheDocument()
    expect(api.diffEnvironments).not.toHaveBeenCalled()
  })

  it('fetches both rpm and kubernetes diffs once both sides are filled in, and merges rows with a type badge', async () => {
    const user = userEvent.setup()
    vi.mocked(api.diffEnvironments).mockImplementation(async ({ sourceType }) => {
      if (sourceType === 'rpm') {
        return diffResponse({
          items: [
            {
              artifact_name: 'nginx',
              left: [{ environment_name: 'proj1', version: '1.2.3', host_or_cluster: null }],
              right: [{ environment_name: 'proj2', version: '1.2.3', host_or_cluster: null }],
              status: 'same',
            },
          ],
        })
      }
      return diffResponse({
        items: [
          {
            artifact_name: 'registry.example.com/shared/api',
            left: [{ environment_name: 'proj1-backend', version: '1.5.0', host_or_cluster: 'k811.system' }],
            right: [],
            status: 'left_only',
          },
        ],
      })
    })

    render(<EnvironmentDiff />)
    await user.type(screen.getByPlaceholderText('Vänster miljö (t.ex. proj1)'), 'proj1')
    await user.type(screen.getByPlaceholderText('Höger miljö (t.ex. proj2)'), 'proj2')

    await waitFor(() => {
      expect(api.diffEnvironments).toHaveBeenCalledWith(
        expect.objectContaining({ left: 'proj1', right: 'proj2', sourceType: 'rpm' }),
      )
      expect(api.diffEnvironments).toHaveBeenCalledWith(
        expect.objectContaining({ left: 'proj1', right: 'proj2', sourceType: 'kubernetes' }),
      )
    })

    expect(await screen.findByText('nginx')).toBeInTheDocument()
    expect(screen.getByText('registry.example.com/shared/api')).toBeInTheDocument()
    expect(screen.getByText('rpm')).toBeInTheDocument()
    expect(screen.getByText('kubernetes')).toBeInTheDocument()
    expect(screen.getByText('Samma')).toBeInTheDocument()
    expect(screen.getByText('Bara vänster')).toBeInTheDocument()
  })

  it('shows "Ej installerad" for the missing side of a left_only/right_only row', async () => {
    const user = userEvent.setup()
    vi.mocked(api.diffEnvironments).mockImplementation(async ({ sourceType }) => {
      if (sourceType === 'rpm') {
        return diffResponse({
          items: [
            {
              artifact_name: 'curl',
              left: [{ environment_name: 'proj1', version: '8.0.0', host_or_cluster: null }],
              right: [],
              status: 'left_only',
            },
          ],
        })
      }
      return diffResponse()
    })

    render(<EnvironmentDiff />)
    await user.type(screen.getByPlaceholderText('Vänster miljö (t.ex. proj1)'), 'proj1')
    await user.type(screen.getByPlaceholderText('Höger miljö (t.ex. proj2)'), 'proj2')

    expect(await screen.findByText('Ej installerad')).toBeInTheDocument()
  })

  it('shows an error when a diff request fails', async () => {
    const user = userEvent.setup()
    vi.mocked(api.diffEnvironments).mockImplementation(async ({ sourceType }) => {
      if (sourceType === 'rpm') throw new Error('500 Internal Server Error')
      return diffResponse()
    })

    render(<EnvironmentDiff />)
    await user.type(screen.getByPlaceholderText('Vänster miljö (t.ex. proj1)'), 'proj1')
    await user.type(screen.getByPlaceholderText('Höger miljö (t.ex. proj2)'), 'proj2')

    expect(await screen.findByText(/Kunde inte hämta diff: 500 Internal Server Error/)).toBeInTheDocument()
  })
})
