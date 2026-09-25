import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { renderWithProviders } from '../test/renderWithProviders'
import type { ApprovalRequest, RescueCase, Shift } from '../domain/types'
import { TodayScreen } from './TodayScreen'

// Matches the mock data moment: rescue_001 deadline 06:50:00 -> 04:12 left.
const NOW = new Date('2026-10-03T06:45:48+02:00')

describe('TodayScreen (dashboard table per demo-readiness T3)', () => {
  it('renders the serif heading with the long date and active-rescue pill', async () => {
    renderWithProviders(<TodayScreen now={NOW} />)
    const heading = await screen.findByRole('heading', { level: 1 })
    expect(heading).toHaveTextContent('Today')
    expect(heading).toHaveClass('font-serif')
    expect(screen.getByText(/3 October/)).toBeInTheDocument()
    expect(await screen.findByText(/active rescues/)).toBeInTheDocument()
  })

  it('renders both responsive variants: cards below md, table from md up', async () => {
    renderWithProviders(<TodayScreen now={NOW} />)
    const cards = await screen.findByTestId('today-cards')
    expect(cards).toHaveClass('md:hidden')
    const table = await screen.findByTestId('today-table')
    expect(table).toHaveClass('md:block')
    expect(table).toHaveClass('overflow-x-auto')
    // Same information lives in both variants.
    expect(within(table).getAllByText('Kitchen').length).toBeGreaterThan(0)
    expect(within(cards).getAllByText('Kitchen').length).toBeGreaterThan(0)
  })

  it('shows the table columns for role, window, employee, status and rescue', async () => {
    renderWithProviders(<TodayScreen now={NOW} />)
    const table = await screen.findByTestId('today-table')
    for (const header of ['Role', 'Window', 'Employee', 'Status', 'Rescue']) {
      expect(within(table).getByText(header)).toBeInTheDocument()
    }
    expect(within(table).getAllByText(/–/).length).toBeGreaterThan(0)
  })

  it('shows uncovered shifts as Unassigned rows with the Uncovered badge', async () => {
    renderWithProviders(<TodayScreen now={NOW} />)
    const table = await screen.findByTestId('today-table')
    const row = within(table).getByText('Unassigned').closest('tr')!
    expect(within(row).getByText('Kitchen')).toBeInTheDocument()
    expect(within(row).getByText('15:00 – 23:00')).toBeInTheDocument()
    expect(within(row).getByText('Uncovered')).toBeInTheDocument()
    expect(within(row).getByText('No candidates offered yet.')).toBeInTheDocument()
  })

  it('shows the searching row with badge, compact countdown, wave and absent employee', async () => {
    renderWithProviders(<TodayScreen now={NOW} />)
    const table = await screen.findByTestId('today-table')
    const row = within(table).getByText('Iker M. (absent)').closest('tr')!
    expect(within(row).getByText('Searching')).toBeInTheDocument()
    // rescue_001 deadline 06:50 at 06:45:48 -> 04:12 left, flagged urgent.
    expect(within(row).getByText('04:12')).toBeInTheDocument()
    expect(within(row).getByText(/wave 2 of 3/)).toBeInTheDocument()
    expect(within(row).getByText('Absent')).toBeInTheDocument()
  })

  it('shows the awaiting-approval row with the gold badge and approval countdown', async () => {
    renderWithProviders(<TodayScreen now={NOW} />)
    const table = await screen.findByTestId('today-table')
    const row = within(table).getByText('Needs approval').closest('tr')!
    // appr_001 expires 06:57 -> 11:12 left at 06:45:48.
    expect(within(row).getByText('11:12')).toBeInTheDocument()
    expect(within(row).getByText(/Partial coverage/)).toBeInTheDocument()
    expect(within(row).getByText('Sonia P.')).toBeInTheDocument()
  })

  it('shows covered shifts with who is on them', async () => {
    renderWithProviders(<TodayScreen now={NOW} />)
    const table = await screen.findByTestId('today-table')
    const row = within(table).getByText('Marta L.').closest('tr')!
    expect(within(row).getAllByText('Covered').length).toBeGreaterThan(0)
    expect(within(table).getByText('Pau S.')).toBeInTheDocument()
  })

  it('keeps the pending overtime approval reachable from its rescue row', async () => {
    const onOpenApprovals = vi.fn()
    const user = userEvent.setup()
    renderWithProviders(<TodayScreen now={NOW} onOpenApprovals={onOpenApprovals} />)
    const table = await screen.findByTestId('today-table')
    // Two pending approvals in the mock: overtime (rescue_001) and partial
    // coverage (rescue_002); each sits on its own row.
    const buttons = within(table).getAllByRole('button', { name: 'Review approval' })
    expect(buttons.length).toBe(2)
    await user.click(buttons[0])
    expect(onOpenApprovals).toHaveBeenCalled()
  })

  it('opens the rescue detail from the row action', async () => {
    const onOpenRescue = vi.fn()
    const user = userEvent.setup()
    renderWithProviders(<TodayScreen now={NOW} onOpenRescue={onOpenRescue} />)
    const table = await screen.findByTestId('today-table')
    const row = within(table).getByText('Iker M. (absent)').closest('tr')!
    await user.click(within(row).getByRole('button', { name: 'View detail' }))
    expect(onOpenRescue).toHaveBeenCalledWith('rescue_001')
  })

  it('keeps the 44px touch target on row action buttons', async () => {
    renderWithProviders(<TodayScreen now={NOW} />)
    const table = await screen.findByTestId('today-table')
    const button = within(table).getAllByRole('button', { name: 'View detail' })[0]
    expect(button).toHaveClass('pointer-coarse:min-h-11')
  })

  // --- escalated rescues (data injected through the query cache) ---------------

  const escalatedShift: Shift = {
    id: 'shift_escalated',
    locationId: 'loc',
    role: 'floor',
    startsAt: '2026-10-03T15:00:00+02:00',
    endsAt: '2026-10-03T23:00:00+02:00',
    assigneeName: 'Iker M.',
    status: 'absent',
  }
  const escalatedRescue: RescueCase = {
    id: 'rescue_escalated',
    shiftId: 'shift_escalated',
    absentEmployeeName: 'Iker M.',
    status: 'ESCALATED',
    deadlineAt: '2026-10-03T14:30:00+02:00',
  }

  function renderWithBoardData(
    data: {
      shifts: Shift[]
      rescues: RescueCase[]
      approvals?: ApprovalRequest[]
    },
    handlers: { onOpenRescue?: (rescueId: string) => void } = {},
  ) {
    // Own QueryClient with seeded cache: staleTime Infinity keeps the injected
    // data stable (the hooks would otherwise refetch the mock on mount).
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false, staleTime: Infinity } },
    })
    client.setQueryData(['shifts', NOW.toISOString().slice(0, 10)], data.shifts)
    client.setQueryData(['rescues', 'active'], data.rescues)
    client.setQueryData(['approvals', 'pending'], data.approvals ?? [])
    return render(
      <QueryClientProvider client={client}>
        <TodayScreen now={NOW} {...handlers} />
      </QueryClientProvider>,
    )
  }

  it('renders an escalated rescue with the Escalated badge, never as Uncovered', async () => {
    renderWithBoardData({ shifts: [escalatedShift], rescues: [escalatedRescue] })
    const table = await screen.findByTestId('today-table')
    const row = within(table).getByText('Iker M. (absent)').closest('tr')!

    expect(within(row).getByText('Escalated')).toBeInTheDocument()
    expect(within(row).queryByText('Uncovered')).not.toBeInTheDocument()
    expect(
      within(row).getByText('The manager was notified — nobody covered it in time.'),
    ).toBeInTheDocument()
  })

  it('offers View detail for a terminal (escalated) case so it can be inspected', async () => {
    const onOpenRescue = vi.fn()
    const user = userEvent.setup()
    renderWithBoardData(
      { shifts: [escalatedShift], rescues: [escalatedRescue] },
      { onOpenRescue },
    )
    const table = await screen.findByTestId('today-table')
    const row = within(table).getByText('Iker M. (absent)').closest('tr')!
    await user.click(within(row).getByRole('button', { name: 'View detail' }))
    expect(onOpenRescue).toHaveBeenCalledWith('rescue_escalated')
  })

  it('keeps a covered shift covered (and inspectable) when its case was escalated', async () => {
    const coveredAfterEscalation: Shift = {
      ...escalatedShift,
      status: 'covered',
      assigneeName: 'Marta L.',
    }
    renderWithBoardData({ shifts: [coveredAfterEscalation], rescues: [escalatedRescue] })
    const table = await screen.findByTestId('today-table')
    const row = within(table).getByText('Marta L.').closest('tr')!

    expect(within(row).getAllByText('Covered').length).toBeGreaterThan(0)
    expect(within(row).queryByText('Escalated')).not.toBeInTheDocument()
    // The case still exists: the Actions column offers its detail.
    expect(within(row).getByRole('button', { name: 'View detail' })).toBeInTheDocument()
  })
})
