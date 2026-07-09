import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { deleteInstallation, diffEnvironments, listEnvironments, searchInstallations } from './api'

function jsonResponse(body: unknown, init: { ok?: boolean; status?: number; statusText?: string } = {}) {
  return {
    ok: init.ok ?? true,
    status: init.status ?? 200,
    statusText: init.statusText ?? 'OK',
    json: () => Promise.resolve(body),
  } as Response
}

describe('api', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn())
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  describe('searchInstallations', () => {
    it('builds the query string, only including optional params when set', async () => {
      vi.mocked(fetch).mockResolvedValue(jsonResponse({ items: [], total: 0, limit: 20, offset: 0 }))

      await searchInstallations({
        q: '',
        environment: '',
        sourceType: '',
        includeRemoved: false,
        sortBy: 'last_seen_at',
        sortDir: 'desc',
        limit: 20,
        offset: 0,
      })

      const url = new URL(vi.mocked(fetch).mock.calls[0][0] as string, 'http://x')
      expect(url.pathname).toBe('/api/v1/installations')
      expect(url.searchParams.get('q')).toBeNull()
      expect(url.searchParams.get('environment')).toBeNull()
      expect(url.searchParams.get('source_type')).toBeNull()
      expect(url.searchParams.get('include_removed')).toBeNull()
      expect(url.searchParams.get('sort_by')).toBe('last_seen_at')
      expect(url.searchParams.get('sort_dir')).toBe('desc')
      expect(url.searchParams.get('limit')).toBe('20')
      expect(url.searchParams.get('offset')).toBe('0')
    })

    it('includes q, environment, source_type and include_removed when set', async () => {
      vi.mocked(fetch).mockResolvedValue(jsonResponse({ items: [], total: 0, limit: 20, offset: 0 }))

      await searchInstallations({
        q: 'nginx',
        environment: 'proj1',
        sourceType: 'kubernetes',
        includeRemoved: true,
        sortBy: 'artifact_name',
        sortDir: 'asc',
        limit: 20,
        offset: 40,
      })

      const url = new URL(vi.mocked(fetch).mock.calls[0][0] as string, 'http://x')
      expect(url.searchParams.get('q')).toBe('nginx')
      expect(url.searchParams.get('environment')).toBe('proj1')
      expect(url.searchParams.get('source_type')).toBe('kubernetes')
      expect(url.searchParams.get('include_removed')).toBe('true')
      expect(url.searchParams.get('offset')).toBe('40')
    })

    it('throws with status and statusText on a non-ok response', async () => {
      vi.mocked(fetch).mockResolvedValue(jsonResponse(null, { ok: false, status: 500, statusText: 'Internal Server Error' }))

      await expect(
        searchInstallations({
          q: '',
          environment: '',
          sourceType: '',
          includeRemoved: false,
          sortBy: 'last_seen_at',
          sortDir: 'desc',
          limit: 20,
          offset: 0,
        }),
      ).rejects.toThrow('500 Internal Server Error')
    })
  })

  describe('listEnvironments', () => {
    it('fetches the environments endpoint with a high limit', async () => {
      vi.mocked(fetch).mockResolvedValue(jsonResponse({ items: [], total: 0, limit: 200, offset: 0 }))
      await listEnvironments()
      expect(fetch).toHaveBeenCalledWith('/api/v1/environments?limit=200', { signal: undefined })
    })
  })

  describe('diffEnvironments', () => {
    it('builds the left/right/source_type query', async () => {
      vi.mocked(fetch).mockResolvedValue(
        jsonResponse({ left: {}, right: {}, items: [], summary: {} }),
      )
      await diffEnvironments({ left: 'proj1', right: 'proj2', sourceType: 'rpm' })
      const url = new URL(vi.mocked(fetch).mock.calls[0][0] as string, 'http://x')
      expect(url.pathname).toBe('/api/v1/environments/diff')
      expect(url.searchParams.get('left')).toBe('proj1')
      expect(url.searchParams.get('right')).toBe('proj2')
      expect(url.searchParams.get('source_type')).toBe('rpm')
    })
  })

  describe('deleteInstallation', () => {
    it('sends a DELETE with the API key header', async () => {
      vi.mocked(fetch).mockResolvedValue(jsonResponse(null))
      await deleteInstallation('abc-123', 'my-key')
      expect(fetch).toHaveBeenCalledWith('/api/v1/installations/abc-123', {
        method: 'DELETE',
        headers: { 'X-API-Key': 'my-key' },
      })
    })

    it('throws the backend-provided detail message on failure', async () => {
      vi.mocked(fetch).mockResolvedValue(
        jsonResponse({ detail: 'unauthorized' }, { ok: false, status: 401, statusText: 'Unauthorized' }),
      )
      await expect(deleteInstallation('abc-123', 'bad-key')).rejects.toThrow('unauthorized')
    })

    it('falls back to status/statusText when the error body is not JSON', async () => {
      vi.mocked(fetch).mockResolvedValue({
        ok: false,
        status: 500,
        statusText: 'Internal Server Error',
        json: () => Promise.reject(new Error('not json')),
      } as unknown as Response)
      await expect(deleteInstallation('abc-123', 'my-key')).rejects.toThrow('500 Internal Server Error')
    })
  })
})
