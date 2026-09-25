import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { renderWithProviders } from '../test/renderWithProviders'
import { TodayScreen } from './TodayScreen'

// Matches the mock data moment: rescue_001 deadline 06:50:00 -> 04:12 left.
const NOW = new Date('2026-10-03T06:45:48+02:00')

describe('TodayScreen (kanban per user mockup)', () => {
  it('renders the serif heading with the long date and active-rescue pill', async () => {
    renderWithProviders(<TodayScreen now={NOW} />)
    const heading = await screen.findByRole('heading', { level: 1 })
    expect(heading).toHaveTextContent('Today')
    expect(heading).toHaveClass('font-serif')
    expect(screen.getByText(/3 October/)).toBeInTheDocument()
    expect(await screen.findByText(/active rescues/)).toBeInTheDocument()
  })

  it('renders the four kanban columns with counts', async () => {
    renderWithProviders(<TodayScreen now={NOW} />)
    await screen.findByText('Uncovered')
    expect(screen.getByText('Searching')).toBeInTheDocument()
    expect(screen.getByText('Needs your approval')).toBeInTheDocument()
    expect(screen.getByText('Covered today')).toBeInTheDocument()
    // Corrected board: the covered column counts the 2 covered plus the 4
    // scheduled mock shifts (6); the approvals badge keeps its own count.
    const coveredColumn = screen.getByRole('region', { name: 'Covered today' })
    expect(within(coveredColumn).getByText('6')).toBeInTheDocument()
  })

  it('shows uncovered shifts with their role and time', async () => {
    renderWithProviders(<TodayScreen now={NOW} />)
    expect(await screen.findByText('Kitchen')).toBeInTheDocument()
    expect(screen.getByText('No candidates offered yet.')).toBeInTheDocument()
  })

  it('shows the seeking card with shift join, big countdown, wave and offer previews', async () => {
    renderWithProviders(<TodayScreen now={NOW} />)
    await screen.findByText('Floor')
    expect(screen.getAllByText('04:12').length).toBeGreaterThan(0)
    expect(screen.getByText(/Absent: Iker M\./)).toBeInTheDocument()
    expect(screen.getByText(/wave 2 of 3/)).toBeInTheDocument()
    expect(screen.getByText('Marta L.')).toBeInTheDocument()
    expect(screen.getByText('Ivan R.')).toBeInTheDocument()
    expect(screen.getByText('declined')).toBeInTheDocument()
  })

  it('opens the rescue detail when a seeking card is clicked', async () => {
    const onOpenRescue = vi.fn()
    const user = userEvent.setup()
    renderWithProviders(<TodayScreen now={NOW} onOpenRescue={onOpenRescue} />)
    await screen.findByText('Floor')
    await user.click(screen.getAllByText('04:12')[0])
    expect(onOpenRescue).toHaveBeenCalledWith('rescue_001')
  })

  it('shows approval cards with a gold review button that opens Approvals', async () => {
    const onOpenApprovals = vi.fn()
    const user = userEvent.setup()
    renderWithProviders(<TodayScreen now={NOW} onOpenApprovals={onOpenApprovals} />)
    await screen.findAllByText(/Sonia P\./)
    expect(screen.getByText('Partial coverage')).toBeInTheDocument()
    await user.click(screen.getAllByRole('button', { name: 'Review approval' })[0])
    expect(onOpenApprovals).toHaveBeenCalled()
  })

  it('shows covered shifts with who covered them', async () => {
    renderWithProviders(<TodayScreen now={NOW} />)
    expect(await screen.findByText(/Covered by Marta L\./)).toBeInTheDocument()
    expect(screen.getByText(/Covered by Pau S\./)).toBeInTheDocument()
  })
})
