import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { renderWithProviders } from './test/renderWithProviders'
import { describe, expect, it } from 'vitest'
import { App } from './App'

// Matches the mock data moment so countdowns are deterministic.
const NOW = new Date('2026-10-03T06:45:48+02:00')

describe('App shell', () => {
  it('renders the dark-green header band with the wordmark', () => {
    renderWithProviders(<App now={NOW} />)
    expect(screen.getByRole('banner')).toHaveTextContent('Shift Rescue')
  })

  it('renders the main content on the warm cream canvas', () => {
    const { container } = renderWithProviders(<App now={NOW} />)
    expect(container.querySelector('.bg-canvas')).toBeInTheDocument()
  })

  it('renders the floating action button', () => {
    renderWithProviders(<App now={NOW} />)
    expect(screen.getByRole('button', { name: 'Report absence' })).toBeInTheDocument()
  })

  it('shows the Today heading by default', async () => {
    renderWithProviders(<App now={NOW} />)
    expect(await screen.findByRole('heading', { level: 1, name: 'Today' })).toBeInTheDocument()
  })

  it('navigates between Today and Approvals from the header', async () => {
    const user = userEvent.setup()
    renderWithProviders(<App now={NOW} />)
    await screen.findByRole('heading', { level: 1, name: 'Today' })
    await user.click(screen.getByRole('button', { name: /Approvals/ }))
    expect(await screen.findByRole('heading', { level: 1, name: 'Approvals' })).toBeInTheDocument()
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
})
