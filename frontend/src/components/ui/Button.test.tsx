import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { Button } from './Button'

describe('Button (DESIGN.md pill button)', () => {
  it('renders a full-pill button with tight tracking', () => {
    render(<Button>Explore our afternoon menu</Button>)
    const button = screen.getByRole('button', { name: 'Explore our afternoon menu' })
    expect(button).toHaveClass('rounded-pill')
    expect(button).toHaveClass('tracking-tight')
  })

  it('primary variant uses the Green Accent fill with white text', () => {
    render(<Button variant="primary">Primary</Button>)
    const button = screen.getByRole('button', { name: 'Primary' })
    expect(button).toHaveClass('bg-green-accent')
    expect(button).toHaveClass('text-white')
  })

  it('secondary variant is outlined in Green Accent on a transparent surface', () => {
    render(<Button variant="secondary">Sign in</Button>)
    const button = screen.getByRole('button', { name: 'Sign in' })
    expect(button).toHaveClass('border-green-accent')
    expect(button).toHaveClass('text-green-accent')
  })

  it('dark variant is a black filled pill with white text', () => {
    render(<Button variant="dark">Join now</Button>)
    const button = screen.getByRole('button', { name: 'Join now' })
    expect(button).toHaveClass('bg-black')
    expect(button).toHaveClass('text-white')
  })

  it('applies the signature scale(0.95) active press micro-interaction', () => {
    render(<Button>Press me</Button>)
    const button = screen.getByRole('button', { name: 'Press me' })
    expect(button).toHaveClass('active:scale-95')
  })

  it('supports the on-dark pairing for House Green feature bands', () => {
    render(<Button variant="onDark">Learn more</Button>)
    const button = screen.getByRole('button', { name: 'Learn more' })
    expect(button).toHaveClass('border-white')
    expect(button).toHaveClass('text-white')
  })

  // Touch-target regression (DESIGN.md §8: pills must reach 44px on touch
  // surfaces without changing the desktop look). jsdom evaluates no media
  // queries, so this pins the pointer-coarse variant class instead.
  it('meets the 44px touch-target floor on touch surfaces only', () => {
    render(<Button>Touch</Button>)
    const button = screen.getByRole('button', { name: 'Touch' })
    expect(button).toHaveClass('pointer-coarse:min-h-11')
    expect(button).not.toHaveClass('min-h-11')
  })

  it('handles clicks and can be disabled', async () => {
    const onClick = vi.fn()
    render(
      <Button onClick={onClick} disabled>
        Click
      </Button>,
    )
    const button = screen.getByRole('button', { name: 'Click' })
    await userEvent.click(button)
    expect(onClick).not.toHaveBeenCalled()
    expect(button).toBeDisabled()
  })
})
