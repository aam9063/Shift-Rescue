import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { renderWithProviders } from './test/renderWithProviders'
import { describe, expect, it } from 'vitest'
import { App } from './App'

describe('App shell (DESIGN.md themed)', () => {
  it('renders the product header', () => {
    renderWithProviders(<App />)
    expect(screen.getByRole('banner')).toHaveTextContent('Shift Rescue')
  })

  it('renders on the warm cream canvas, not pure white', () => {
    const { container } = renderWithProviders(<App />)
    expect(container.firstElementChild).toHaveClass('bg-canvas')
  })

  it('shows the dashboard entry point with its heading', async () => {
    renderWithProviders(<App />)
    expect(await screen.findByRole('heading', { level: 1 })).toHaveTextContent('Today')
  })

  it('navigates between Today and Approvals from the header', async () => {
    const user = userEvent.setup()
    renderWithProviders(<App />)
    await screen.findByRole('heading', { level: 1, name: 'Today' })
    await user.click(screen.getByRole('button', { name: 'Approvals' }))
    expect(await screen.findByRole('heading', { level: 1, name: 'Approvals' })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Today' }))
    expect(await screen.findByRole('heading', { level: 1, name: 'Today' })).toBeInTheDocument()
  })

  it('navigates from the rescue banner to the rescue detail and back', async () => {
    const user = userEvent.setup()
    renderWithProviders(<App />)
    const banner = await screen.findByRole('alert')
    await user.click(banner)
    expect(await screen.findByRole('button', { name: /Back to Today/ })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /Back to Today/ }))
    expect(await screen.findByRole('alert')).toBeInTheDocument()
  })
})
