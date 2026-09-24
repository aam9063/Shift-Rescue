import { screen } from '@testing-library/react'
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
})
