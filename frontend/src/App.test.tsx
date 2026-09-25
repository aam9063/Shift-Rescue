import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { renderWithProviders } from './test/renderWithProviders'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { App } from './App'
import { clearSession, setSession } from './services/auth'

// Matches the mock data moment so countdowns are deterministic.
const NOW = new Date('2026-10-03T06:45:48+02:00')

// The app is behind RequireAuth: seed a session (no network) for these tests.
beforeEach(() => {
  setSession({
    accessToken: 'test-token',
    manager: {
      id: 'mgr_1',
      name: 'Demo Manager',
      email: 'manager@laterraza.demo',
      role: 'manager',
      locationIds: ['loc_la_terraza'],
    },
  })
})

afterEach(() => {
  clearSession()
  window.location.hash = ''
})

describe('App shell', () => {
  it('renders the dark-green header band with the wordmark', () => {
    renderWithProviders(<App now={NOW} />)
    expect(screen.getByRole('banner')).toHaveTextContent('Shift Rescue')
  })

  it('renders the main content on the warm cream canvas', () => {
    const { container } = renderWithProviders(<App now={NOW} />)
    expect(container.querySelector('.bg-canvas')).toBeInTheDocument()
  })

  it('shows the Today heading by default', async () => {
    renderWithProviders(<App now={NOW} />)
    expect(await screen.findByRole('heading', { level: 1, name: 'Today' })).toBeInTheDocument()
  })

  it('navigates between views from the header', async () => {
    const user = userEvent.setup()
    renderWithProviders(<App now={NOW} />)
    await screen.findByRole('heading', { level: 1, name: 'Today' })

    await user.click(screen.getByRole('button', { name: 'Approvals' }))
    expect(await screen.findByRole('heading', { level: 1, name: 'Approvals' })).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Conversations' }))
    expect(await screen.findByRole('heading', { level: 1, name: 'Conversations' })).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Operations' }))
    expect(await screen.findByRole('heading', { level: 1, name: 'Operations' })).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Agent decisions' }))
    expect(
      await screen.findByRole('heading', { level: 1, name: 'Agent decisions' }),
    ).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Evals' }))
    expect(await screen.findByRole('heading', { level: 1, name: 'Evals' })).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Today' }))
    expect(await screen.findByRole('heading', { level: 1, name: 'Today' })).toBeInTheDocument()
  })

  it('navigates from the seeking kanban card to the rescue detail and back', async () => {
    const user = userEvent.setup()
    renderWithProviders(<App now={NOW} />)
    const countdown = (await screen.findAllByText('04:12'))[0]
    await user.click(countdown)
    expect(await screen.findByRole('button', { name: /Back to Today/ })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /Back to Today/ }))
    expect(await screen.findByRole('heading', { level: 1, name: 'Today' })).toBeInTheDocument()
  })

  it('returns to the login screen after logging out', async () => {
    const user = userEvent.setup()
    renderWithProviders(<App now={NOW} />)
    await screen.findByRole('heading', { level: 1, name: 'Today' })

    await user.click(screen.getByRole('button', { name: 'Log out' }))

    expect(
      await screen.findByRole('heading', { level: 1, name: 'Manager sign in' }),
    ).toBeInTheDocument()
    expect(localStorage.getItem('shift-rescue.session')).toBeNull()
  })

  it('notes on the Evals screen that the data is not live yet', async () => {
    const user = userEvent.setup()
    renderWithProviders(<App now={NOW} />)

    await user.click(screen.getByRole('button', { name: 'Evals' }))

    expect(await screen.findByText(/not live yet/)).toBeInTheDocument()
  })
})
