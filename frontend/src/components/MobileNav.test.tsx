import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { renderWithProviders } from '../test/renderWithProviders'
import { AppHeader } from './AppHeader'

/**
 * Phone navigation contract (DESIGN.md §8: hamburger drawer below the tablet
 * breakpoint). jsdom evaluates no media queries, so these tests pin the class
 * and interaction contract of the drawer; the parent verifies the visual
 * result at 360px / 768px / 1440px.
 */
describe('AppHeader mobile drawer', () => {
  it('is closed by default and wires the menu button for assistive tech', () => {
    renderHeader()
    const menu = screen.getByRole('button', { name: 'Open menu' })
    expect(menu).toHaveAttribute('aria-expanded', 'false')
    expect(menu).toHaveAttribute('aria-controls', 'mobile-nav-panel')
    // lg, not md: the operator nav only appears at lg, so the drawer has to
    // cover the tablet range (768-1023px) or those destinations are unreachable.
    expect(menu).toHaveClass('lg:hidden')
    expect(screen.queryByRole('navigation', { name: 'Menu' })).not.toBeInTheDocument()
  })

  it('opens a panel listing every destination from both nav groups', async () => {
    const user = userEvent.setup()
    renderHeader()
    await user.click(screen.getByRole('button', { name: 'Open menu' }))

    const panel = within(screen.getByRole('navigation', { name: 'Menu' }))
    for (const label of [
      'Today',
      'Approvals',
      'Conversations',
      'Operations', // main group
      'Ops',
      'Agent decisions',
      'Evals', // operator group
    ]) {
      expect(panel.getByRole('button', { name: label })).toBeInTheDocument()
    }
  })

  it('marks the active destination with the gold indicator', async () => {
    const user = userEvent.setup()
    renderHeader({ currentView: 'evals' })
    await user.click(screen.getByRole('button', { name: 'Open menu' }))

    const panel = within(screen.getByRole('navigation', { name: 'Menu' }))
    const active = panel.getByRole('button', { name: 'Evals' })
    expect(active).toHaveClass('text-white')
    expect(active.querySelector('.bg-gold')).toBeInTheDocument()

    const inactive = panel.getByRole('button', { name: 'Today' })
    expect(inactive.querySelector('.bg-gold')).not.toBeInTheDocument()
  })

  it('closes on Escape', async () => {
    const user = userEvent.setup()
    renderHeader()
    await user.click(screen.getByRole('button', { name: 'Open menu' }))
    expect(screen.getByRole('navigation', { name: 'Menu' })).toBeInTheDocument()

    await user.keyboard('{Escape}')

    expect(screen.queryByRole('navigation', { name: 'Menu' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Open menu' })).toHaveAttribute(
      'aria-expanded',
      'false',
    )
  })

  it('closes when a destination is chosen and navigates to it', async () => {
    const onNavigate = vi.fn()
    const user = userEvent.setup()
    renderHeader({ onNavigate })
    await user.click(screen.getByRole('button', { name: 'Open menu' }))

    const panel = within(screen.getByRole('navigation', { name: 'Menu' }))
    await user.click(panel.getByRole('button', { name: 'Approvals' }))

    expect(onNavigate).toHaveBeenCalledWith('approvals')
    expect(screen.queryByRole('navigation', { name: 'Menu' })).not.toBeInTheDocument()
  })

  it('keeps the signed-in manager and the logout action reachable from the panel', async () => {
    const onLogout = vi.fn()
    const user = userEvent.setup()
    renderHeader({ onLogout, managerName: 'Demo Manager', managerRole: 'manager' })
    await user.click(screen.getByRole('button', { name: 'Open menu' }))

    const panel = within(screen.getByRole('navigation', { name: 'Menu' }))
    expect(panel.getByText('Demo Manager · manager')).toBeInTheDocument()
    await user.click(panel.getByRole('button', { name: 'Log out' }))
    expect(onLogout).toHaveBeenCalledTimes(1)
  })

  it('gives the menu button and every drawer item the 44px touch-target class', async () => {
    const user = userEvent.setup()
    renderHeader()
    await user.click(screen.getByRole('button', { name: 'Open menu' }))

    // size-11 = 44px for the square hamburger; min-h-11 = 44px for items.
    expect(screen.getByRole('button', { name: 'Close menu' })).toHaveClass('size-11')
    const panel = within(screen.getByRole('navigation', { name: 'Menu' }))
    for (const item of panel.getAllByRole('button')) {
      expect(item).toHaveClass('min-h-11')
    }
  })
})

function renderHeader(
  props: {
    onNavigate?: (v: any) => void
    currentView?: any
    managerName?: string
    managerRole?: string
    onLogout?: () => void
  } = {},
) {
  return renderWithProviders(
    <AppHeader
      currentView={props.currentView ?? 'today'}
      onNavigate={props.onNavigate ?? (() => {})}
      pendingApprovals={0}
      managerName={props.managerName}
      managerRole={props.managerRole}
      onLogout={props.onLogout}
    />,
  )
}
