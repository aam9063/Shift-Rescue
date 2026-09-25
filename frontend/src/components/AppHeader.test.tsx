import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { renderWithProviders } from '../test/renderWithProviders'
import { AppHeader } from './AppHeader'

describe('AppHeader (dark-green band per user mockups)', () => {
  it('renders a clickable wordmark, location and demo simulator pill', () => {
    renderHeader()
    const wordmark = screen.getByRole('button', { name: 'Shift Rescue' })
    expect(wordmark).toHaveClass('cursor-pointer')
    expect(screen.getByText('La Terraza del Puerto')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Demo simulator/ })).toBeInTheDocument()
  })

  it('renders on the House Green band', () => {
    const { container } = renderHeader()
    expect(container.firstElementChild).toHaveClass('bg-green-house')
  })

  it('navigates to Today and Approvals', async () => {
    const onNavigate = vi.fn()
    const user = userEvent.setup()
    renderHeader({ onNavigate })
    await user.click(screen.getAllByRole('button', { name: 'Today' })[0])
    expect(onNavigate).toHaveBeenCalledWith('today')
    await user.click(screen.getAllByRole('button', { name: 'Approvals' })[0])
    expect(onNavigate).toHaveBeenCalledWith('approvals')
  })

  it('shows the pending approval count next to the nav', () => {
    renderHeader({ pendingApprovals: 2 })
    expect(screen.getByText('2')).toBeInTheDocument()
  })
})

function renderHeader(
  props: {
    onNavigate?: (v: any) => void
    pendingApprovals?: number
  } = {},
) {
  return renderWithProviders(
    <AppHeader
      currentView="today"
      onNavigate={props.onNavigate ?? (() => {})}
      pendingApprovals={props.pendingApprovals ?? 0}
    />,
  )
}
