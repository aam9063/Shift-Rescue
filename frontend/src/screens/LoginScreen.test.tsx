import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { renderWithProviders } from '../test/renderWithProviders'
import { LoginScreen } from './LoginScreen'
import { clearSession, getSession } from '../services/auth'

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}

const MANAGER = {
  id: 'mgr_1',
  name: 'Demo Manager',
  email: 'manager@laterraza.demo',
  role: 'manager',
  locationIds: ['loc_la_terraza'],
}

describe('LoginScreen', () => {
  afterEach(() => {
    clearSession()
    vi.unstubAllGlobals()
  })

  it('submits credentials and stores the session on success', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(jsonResponse({ accessToken: 'token-abc', manager: MANAGER }))
    vi.stubGlobal('fetch', fetchMock)
    const onLogin = vi.fn()
    const user = userEvent.setup()

    renderWithProviders(<LoginScreen onLogin={onLogin} />)
    await user.type(screen.getByLabelText('Email'), 'manager@laterraza.demo')
    await user.type(screen.getByLabelText('Password'), 'laterraza-demo-2026')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))

    expect(await screen.findByRole('heading', { name: 'Manager sign in' })).toBeInTheDocument()
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('/api/auth/login')
    expect(init.method).toBe('POST')
    expect(JSON.parse(init.body as string)).toEqual({
      email: 'manager@laterraza.demo',
      password: 'laterraza-demo-2026',
    })
    expect(getSession()?.accessToken).toBe('token-abc')
    expect(getSession()?.manager.role).toBe('manager')
    expect(onLogin).toHaveBeenCalledOnce()
  })

  it('shows a clear error message on wrong credentials (401)', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({ detail: 'Invalid email or password' }, 401)))
    const user = userEvent.setup()

    renderWithProviders(<LoginScreen />)
    await user.type(screen.getByLabelText('Email'), 'manager@laterraza.demo')
    await user.type(screen.getByLabelText('Password'), 'wrong-password')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Invalid email or password.')
    expect(getSession()).toBeNull()
  })

  it('shows a distinct offline message when the server is unreachable', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))
    const user = userEvent.setup()

    renderWithProviders(<LoginScreen />)
    await user.type(screen.getByLabelText('Email'), 'manager@laterraza.demo')
    await user.type(screen.getByLabelText('Password'), 'laterraza-demo-2026')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Cannot reach the server. Check your connection and try again.',
    )
    expect(getSession()).toBeNull()
  })

  it('shows the demo credentials for the reviewer', () => {
    renderWithProviders(<LoginScreen />)
    expect(screen.getByText(/manager@laterraza\.demo/)).toBeInTheDocument()
    expect(screen.getByText(/laterraza-demo-2026/)).toBeInTheDocument()
  })
})
