import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { renderWithProviders } from '../test/renderWithProviders'
import { dataSource } from '../services/dataSource'
import type { RescueDetail } from '../domain/types'
import { RescueDetailScreen } from './RescueDetailScreen'

const NOW = new Date('2026-10-03T06:45:48+02:00')

/** Seeds the query cache directly (like the Today screen tests) so terminal
 * or escalated cases can be exercised without adding mock data. */
function renderWithCache(detail: RescueDetail) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Infinity } },
  })
  client.setQueryData(['rescues', detail.rescue.id], detail)
  client.setQueryData(['approvals', 'pending'], [])
  return render(
    <QueryClientProvider client={client}>
      <RescueDetailScreen rescueId={detail.rescue.id} now={NOW} onBack={vi.fn()} />
    </QueryClientProvider>,
  )
}

describe('RescueDetailScreen (redesign per user mockup)', () => {
  it('renders the green hero band with back link, serif title and wave pill', async () => {
    const { container } = renderWithProviders(
      <RescueDetailScreen rescueId="rescue_001" now={NOW} onBack={vi.fn()} />,
    )
    await screen.findByText(/Iker M\./)
    const hero = container.querySelector('.bg-green-house')
    expect(hero).not.toBeNull()
    expect(screen.getByRole('button', { name: /Back to Today/ })).toBeInTheDocument()
    const title = screen.getByRole('heading', { level: 1 })
    expect(title).toHaveClass('font-serif')
    expect(title).toHaveTextContent('Floor · 15:00 – 23:00')
    expect(screen.getByText(/wave 2 of 3/)).toBeInTheDocument()
  })

  it('renders the giant MM:SS countdown with its caption in the hero', async () => {
    renderWithProviders(<RescueDetailScreen rescueId="rescue_001" now={NOW} onBack={vi.fn()} />)
    await screen.findByText('04:12')
    expect(screen.getByText(/minutes left/)).toBeInTheDocument()
  })

  it('renders the agent timeline chronologically with colored dots and AI badge', async () => {
    renderWithProviders(<RescueDetailScreen rescueId="rescue_001" now={NOW} onBack={vi.fn()} />)
    const timeline = await screen.findByRole('list', { name: 'Agent timeline' })
    const items = [...timeline.querySelectorAll('li')]
    const texts = items.map((li) => li.textContent ?? '')
    expect(texts.findIndex((t) => t.includes('Rescue opened')))
      .toBeLessThan(texts.findIndex((t) => t.includes('Offer declined')))
    expect(texts.findIndex((t) => t.includes('Offer declined')))
      .toBeLessThan(texts.findLastIndex((t) => t.includes('Offer sent')))
    // AI badge on the LLM-interpreted event
    expect(within(items[3]).getByText('AI')).toBeInTheDocument()
  })

  it('renders candidate cards with score and per-offer status, then excluded rows', async () => {
    renderWithProviders(<RescueDetailScreen rescueId="rescue_001" now={NOW} onBack={vi.fn()} />)
    await screen.findByText('Marta L.')
    expect(screen.getByText(/Score 0\.82/)).toBeInTheDocument()
    expect(screen.getAllByText(/no overtime/).length).toBeGreaterThan(0)
    expect(screen.getByText('declined')).toBeInTheDocument()
    expect(screen.getByText('Excluded')).toBeInTheDocument()
    expect(screen.getByText('MAX_WEEKLY_HOURS')).toBeInTheDocument()
    expect(screen.getByText('REST_VIOLATION')).toBeInTheDocument()
  })

  it('goes back to Today when the back button is pressed', async () => {
    const onBack = vi.fn()
    const user = userEvent.setup()
    renderWithProviders(<RescueDetailScreen rescueId="rescue_001" now={NOW} onBack={onBack} />)
    await screen.findByText(/Iker M\./)
    await user.click(screen.getByRole('button', { name: /Back to Today/ }))
    expect(onBack).toHaveBeenCalledOnce()
  })

  // --- manager actions (feature manager-can-act T2) ---------------------------

  it('closes the case through the confirmed Close case action', async () => {
    const closeRescue = vi.spyOn(dataSource, 'closeRescue').mockResolvedValue(undefined)
    const user = userEvent.setup()
    renderWithProviders(<RescueDetailScreen rescueId="rescue_001" now={NOW} onBack={vi.fn()} />)
    await screen.findByText(/Iker M\./)

    // A confirmation step guards the close.
    await user.click(screen.getByRole('button', { name: 'Close case' }))
    expect(closeRescue).not.toHaveBeenCalled()
    await user.click(screen.getByRole('button', { name: 'Confirm close' }))

    expect(closeRescue).toHaveBeenCalledWith('rescue_001')
    // 202 semantics: the UI says the change is queued, not that it happened.
    expect(
      screen.getByText(/Applies in a moment: writes are queued and the worker applies them/),
    ).toBeInTheDocument()
    closeRescue.mockRestore()
  })

  it('offers approve and reject inline for an awaiting-approval case', async () => {
    const decideApproval = vi
      .spyOn(dataSource, 'decideApproval')
      .mockResolvedValue(undefined)
    const user = userEvent.setup()
    // rescue_002 is AWAITING_APPROVAL; appr_001 is its pending approval.
    renderWithProviders(<RescueDetailScreen rescueId="rescue_002" now={NOW} onBack={vi.fn()} />)
    await screen.findByText(/Nerea V\./)

    expect(await screen.findByText(/Partial coverage/)).toBeInTheDocument()
    expect(screen.getByText('Sonia P.')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Approve' }))

    expect(decideApproval).toHaveBeenCalledWith('appr_001', 'approved', 'manager_01')
    decideApproval.mockRestore()
  })

  it('tells the escalated manager what to do and keeps the close action', async () => {
    renderWithCache({
      rescue: {
        id: 'rescue_esc',
        shiftId: 'shift_1',
        absentEmployeeName: 'Iker M.',
        status: 'ESCALATED',
        deadlineAt: '2026-10-03T04:50:00+00:00',
        offerPreviews: [{ employeeName: 'Marta L.', status: 'pending' }],
      },
      shift: {
        id: 'shift_1',
        locationId: 'loc',
        role: 'floor',
        startsAt: '2026-10-03T13:00:00+00:00',
        endsAt: '2026-10-03T21:00:00+00:00',
        assigneeName: 'Iker M.',
        status: 'absent',
      },
      timeline: [
        {
          id: 'evt_esc',
          rescueId: 'rescue_esc',
          type: 'ESCALATED',
          actor: 'system',
          createdAt: '2026-10-03T04:44:00+00:00',
        },
      ],
      candidates: [],
      offers: [],
    })

    expect(await screen.findByText('Escalated')).toBeInTheDocument()
    // The exact moment from the timeline, never a dead countdown.
    expect(screen.getByText('at 06:44')).toBeInTheDocument()
    expect(screen.queryByText(/minutes left/)).not.toBeInTheDocument()
    expect(screen.getByText(/Resolve it outside the system/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Close case' })).toBeInTheDocument()
  })

  it('offers no actions on a terminal covered case and says who covered it', async () => {
    renderWithCache({
      rescue: {
        id: 'rescue_cov',
        shiftId: 'shift_1',
        absentEmployeeName: 'Iker M.',
        status: 'COVERED',
        deadlineAt: '2026-10-03T04:50:00+00:00',
      },
      shift: {
        id: 'shift_1',
        locationId: 'loc',
        role: 'floor',
        startsAt: '2026-10-03T13:00:00+00:00',
        endsAt: '2026-10-03T21:00:00+00:00',
        assigneeName: 'Marta L.',
        status: 'covered',
      },
      timeline: [],
      candidates: [],
      offers: [
        {
          id: 'offer_1',
          rescueId: 'rescue_cov',
          employeeId: 'emp_marta',
          employeeName: 'Marta L.',
          waveNumber: 1,
          status: 'ACCEPTED',
          sentAt: '2026-10-03T04:41:00+00:00',
          expiresAt: '2026-10-03T04:51:00+00:00',
        },
      ],
    })

    // The hero status pill and the terminal outcome both say it.
    expect(screen.getAllByText('Covered').length).toBeGreaterThan(0)
    expect(screen.getByText('by Marta L.')).toBeInTheDocument()
    expect(screen.queryByText(/minutes left/)).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Close case' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Approve' })).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Manager actions')).not.toBeInTheDocument()
  })
})
