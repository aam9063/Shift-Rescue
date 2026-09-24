import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { renderWithProviders } from '../test/renderWithProviders'
import { AppHeader } from './AppHeader'

describe('AppHeader (dark-green band per user mockup)', () => {
  it('renders the wordmark, location selector and report-absence CTA', () => {
    renderHeader()
    expect(screen.getByText('Shift Rescue')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /La Terraza del Puerto/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Report absence/ })).toBeInTheDocument()
  })

  it('renders on the House Green band with white text', () => {
    const { container } = renderHeader()
    expect(container.firstElementChild).toHaveClass('bg-green-house')
  })

  it('navigates to Today and Approvals from the header', async () => {
    const onNavigate = vi.fn()
    const user = userEvent.setup()
    renderHeader({ onNavigate })
    await user.click(screen.getByRole('button', { name: 'Today' }))
    expect(onNavigate).toHaveBeenCalledWith('today')
    await user.click(screen.getByRole('button', { name: /Approvals/ }))
    expect(onNavigate).toHaveBeenCalledWith('approvals')
  })

  it('shows the pending approval count next to the Approvals nav', () => {
    renderHeader({ pendingApprovals: 2 })
    expect(screen.getByText('2')).toBeInTheDocument()
  })
})

function renderHeader(
  props: { onNavigate?: (v: 'today' | 'approvals') => void; pendingApprovals?: number } = {},
) {
  return renderWithProviders(
    <AppHeader
      currentView="today"
      onNavigate={props.onNavigate ?? (() => {})}
      pendingApprovals={props.pendingApprovals ?? 0}
    />,
  )
}
