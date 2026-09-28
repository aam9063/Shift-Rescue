import { screen } from '@testing-library/react'
import { fireEvent } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { renderWithProviders } from '../test/renderWithProviders'
import { RequireAuth } from './RequireAuth'
import { clearSession, SESSION_EXPIRED_EVENT, setSession } from '../services/auth'

function renderChildren() {
  return renderWithProviders(
    <RequireAuth>
      <p>Dashboard content</p>
    </RequireAuth>,
  )
}

afterEach(() => {
  clearSession()
})

describe('RequireAuth', () => {
  it('lands an unauthenticated visitor on the login screen', () => {
    renderChildren()
    expect(screen.getByRole('heading', { name: 'Manager sign in' })).toBeInTheDocument()
    expect(screen.queryByText('Dashboard content')).not.toBeInTheDocument()
  })

  it('renders the children for an authenticated session', () => {
    setSession({
      accessToken: 'tok',
      manager: { id: 'mgr_1', name: 'M', email: 'm@x.demo', role: 'manager', locationIds: [] },
    })
    renderChildren()
    expect(screen.getByText('Dashboard content')).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Manager sign in' })).not.toBeInTheDocument()
  })

  it('returns to the login screen when any API call answers 401', () => {
    setSession({
      accessToken: 'tok',
      manager: { id: 'mgr_1', name: 'M', email: 'm@x.demo', role: 'manager', locationIds: [] },
    })
    renderChildren()
    expect(screen.getByText('Dashboard content')).toBeInTheDocument()

    fireEvent(window, new Event(SESSION_EXPIRED_EVENT))

    expect(screen.getByRole('heading', { name: 'Manager sign in' })).toBeInTheDocument()
    expect(screen.queryByText('Dashboard content')).not.toBeInTheDocument()
  })
})
