import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { renderWithProviders } from './test/renderWithProviders'
import { describe, expect, it } from 'vitest'
import { App } from './App'

describe('App shell', () => {
  it('renders the dark-green header band with the wordmark', () => {
    renderWithProviders(<App />)
    expect(screen.getByRole('banner')).toHaveTextContent('Shift Rescue')
  })

  it('renders the main content on the warm cream canvas', () => {
    const { container } = renderWithProviders(<App />)
    expect(container.querySelector('.bg-canvas')).toBeInTheDocument()
  })

  it('renders the floating action button', () => {
    renderWithProviders(<App />)
    expect(screen.getByRole('button', { name: 'Report absence' })).toBeInTheDocument()
  })

  it('shows the Today heading by default', async () => {
    renderWithProviders(<App />)
    expect(await screen.findByRole('heading', { level: 1, name: 'Today' })).toBeInTheDocument()
  })

  it('navigates between Today and Approvals from the header', async () => {
    const user = userEvent.setup()
    renderWithProviders(<App />)
    await screen.findByRole('heading', { level: 1, name: 'Today' })
    await user.click(screen.getByRole('button', { name: /Approvals/ }))
    expect(await screen.findByRole('heading', { level: 1, name: 'Approvals' })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Today' }))
    expect(await screen.findByRole('heading', { level: 1, name: 'Today' })).toBeInTheDocument()
  })

  it('navigates from the rescue banner to the rescue detail and back', async () => {
    const user = userEvent.setup()
    renderWithProviders(<App />)
    const banner = (await screen.findAllByRole('alert'))[0]
    await user.click(banner)
    expect(await screen.findByRole('button', { name: /Back to Today/ })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /Back to Today/ }))
    expect((await screen.findAllByRole('alert')).length).toBeGreaterThan(0)
  })
})
