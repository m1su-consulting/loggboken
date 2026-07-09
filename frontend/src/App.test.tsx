import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import * as api from './api'

vi.mock('./api')

beforeEach(() => {
  vi.mocked(api.listEnvironments).mockResolvedValue({ items: [], total: 0, limit: 200, offset: 0 })
  vi.mocked(api.searchInstallations).mockResolvedValue({ items: [], total: 0, limit: 20, offset: 0 })
})

describe('App', () => {
  it('shows the installations tab by default', () => {
    render(<App />)
    expect(screen.getByRole('button', { name: 'Installationer' })).toHaveClass('active')
    expect(screen.getByPlaceholderText('Sök på miljö, host eller artefakt…')).toBeInTheDocument()
  })

  it('switches to the diff tab when clicked', async () => {
    const user = userEvent.setup()
    render(<App />)
    await user.click(screen.getByRole('button', { name: 'Jämför miljöer' }))
    expect(screen.getByRole('button', { name: 'Jämför miljöer' })).toHaveClass('active')
    expect(screen.getByPlaceholderText('Vänster miljö (t.ex. proj1)')).toBeInTheDocument()
  })
})
