import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { renderWithProviders } from '../test/renderWithProviders'
import { ApprovalsScreen } from './ApprovalsScreen'

function findItem(name: string): HTMLElement | undefined {
  return screen
    .getAllByRole('listitem')
    .find((li) => li.textContent?.includes(name))
}

describe('ApprovalsScreen', () => {
  it('lists pending approvals oldest-first with kind and context', async () => {
    renderWithProviders(<ApprovalsScreen />)
    await screen.findByText(/Overtime/)
    const items = screen.getAllByRole('listitem')
    const texts = items.map((li) => li.textContent ?? '')
    expect(texts.findIndex((t) => t.includes('Bruno T.')))
      .toBeLessThan(texts.findIndex((t) => t.includes('Sonia P.')))
    expect(screen.getByText(/exceed contracted 30h weekly hours/)).toBeInTheDocument()
    expect(screen.getByText(/Can cover from 19:00 to 22:00/)).toBeInTheDocument()
  })

  it('removes an approval from the inbox after approving it', async () => {
    const user = userEvent.setup()
    renderWithProviders(<ApprovalsScreen />)
    await screen.findByText(/Bruno T\./)
    const item = findItem('Bruno T.')
    await user.click(within(item!).getByRole('button', { name: 'Approve' }))
    expect(screen.queryByText(/Bruno T\./)).not.toBeInTheDocument()
    expect(screen.getByText(/Sonia P\./)).toBeInTheDocument()
  })

  it('removes an approval from the inbox after rejecting it', async () => {
    const user = userEvent.setup()
    renderWithProviders(<ApprovalsScreen />)
    await screen.findByText(/Sonia P\./)
    const item = findItem('Sonia P.')
    await user.click(within(item!).getByRole('button', { name: 'Reject' }))
    expect(await screen.findByText('No pending approvals')).toBeInTheDocument()
  })

  it('renders the empty state when nothing is pending', async () => {
    const { dataSource } = await import('../services/hooks')
    const { vi } = await import('vitest')
    vi.spyOn(dataSource, 'getPendingApprovals').mockResolvedValue([])
    renderWithProviders(<ApprovalsScreen />)
    expect(await screen.findByText('No pending approvals')).toBeInTheDocument()
  })
})
