import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { App } from './App'

describe('App shell (DESIGN.md themed)', () => {
  it('renders the product header', () => {
    render(<App />)
    expect(screen.getByRole('banner')).toHaveTextContent('Shift Rescue')
  })

  it('renders on the warm cream canvas, not pure white', () => {
    const { container } = render(<App />)
    expect(container.firstElementChild).toHaveClass('bg-canvas')
  })

  it('shows the placeholder dashboard entry point', () => {
    render(<App />)
    expect(screen.getByRole('main')).toBeInTheDocument()
    expect(screen.getByRole('heading', { level: 1 })).toBeInTheDocument()
  })
})
