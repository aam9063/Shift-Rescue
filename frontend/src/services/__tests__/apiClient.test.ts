import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError, apiBaseUrl, apiFetch, NetworkError } from '../apiClient'
import { clearSession, getSession, setSession } from '../auth'

const JSON_HEADERS = { 'Content-Type': 'application/json' }

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: JSON_HEADERS })
}

describe('apiClient', () => {
  afterEach(() => {
    clearSession()
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
    delete (import.meta.env as Record<string, string | undefined>).VITE_API_BASE_URL
  })

  it('attaches the bearer token when a session exists', async () => {
    setSession({
      accessToken: 'token-123',
      manager: { id: 'mgr_1', name: 'Manager', email: 'm@x.demo', role: 'manager', locationIds: [] },
    })
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ ok: true }))
    vi.stubGlobal('fetch', fetchMock)

    await apiFetch('/api/locations')

    expect(fetchMock).toHaveBeenCalledOnce()
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    const headers = init.headers as Record<string, string>
    expect(headers.Authorization).toBe('Bearer token-123')
  })

  it('sends no Authorization header without a session', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ ok: true }))
    vi.stubGlobal('fetch', fetchMock)

    await apiFetch('/api/status')

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    const headers = init.headers as Record<string, string>
    expect(headers.Authorization).toBeUndefined()
  })

  it('parses the JSON body on success', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({ value: 42 })))
    await expect(apiFetch<{ value: number }>('/api/anything')).resolves.toEqual({ value: 42 })
  })

  it('raises ApiError with the status and safe detail on 4xx/5xx', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({ detail: 'Location not found' }, 404)))
    const promise = apiFetch('/api/locations/nope')
    await expect(promise).rejects.toBeInstanceOf(ApiError)
    await promise.catch((error: ApiError) => {
      expect(error.status).toBe(404)
      expect(error.message).toBe('Location not found')
    })
  })

  it('falls back to a generic message when the error body is not JSON', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(new Response('gateway exploded', { status: 502 })),
    )
    await expect(apiFetch('/api/anything')).rejects.toMatchObject({
      name: 'ApiError',
      status: 502,
      message: 'Request failed with status 502',
    })
  })

  it('never swallows a 401: clears the session and notifies the app', async () => {
    setSession({
      accessToken: 'stale-token',
      manager: { id: 'mgr_1', name: 'Manager', email: 'm@x.demo', role: 'manager', locationIds: [] },
    })
    const listener = vi.fn()
    window.addEventListener('shift-rescue:session-expired', listener)
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({ detail: 'Invalid token' }, 401)))

    await expect(apiFetch('/api/locations')).rejects.toMatchObject({ status: 401 })

    expect(getSession()).toBeNull()
    expect(listener).toHaveBeenCalledOnce()
    window.removeEventListener('shift-rescue:session-expired', listener)
  })

  it('maps network failures to NetworkError so the UI can show offline', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))
    await expect(apiFetch('/api/locations')).rejects.toBeInstanceOf(NetworkError)
  })

  it('prefixes the base URL when VITE_API_BASE_URL is set', async () => {
    ;(import.meta.env as Record<string, string>).VITE_API_BASE_URL = 'https://api.example.com/'
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({}))
    vi.stubGlobal('fetch', fetchMock)

    await apiFetch('/api/status')

    expect(apiBaseUrl()).toBe('https://api.example.com')
    expect(fetchMock.mock.calls[0][0]).toBe('https://api.example.com/api/status')
  })
})

describe('auth session storage', () => {
  beforeEach(() => {
    clearSession()
  })

  afterEach(() => {
    clearSession()
  })

  it('stores and clears the session under one key', () => {
    expect(getSession()).toBeNull()
    setSession({
      accessToken: 'tok',
      manager: { id: 'mgr_1', name: 'M', email: 'm@x.demo', role: 'manager', locationIds: ['loc_1'] },
    })
    expect(getSession()?.accessToken).toBe('tok')
    clearSession()
    expect(getSession()).toBeNull()
  })

  it('tolerates a corrupted stored session', () => {
    localStorage.setItem('shift-rescue.session', 'not-json')
    expect(getSession()).toBeNull()
  })
})
