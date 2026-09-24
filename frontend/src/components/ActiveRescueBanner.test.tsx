import { screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { renderWithProviders } from '../test/renderWithProviders'
import type { RescueCase } from '../domain/types'
import { ActiveRescueBanner } from './ActiveRescueBanner'

const rescue: RescueCase = {
  id: 'rescue_001',
  shiftId: 'shift_floor_01',
  absentEmployeeName: 'Lucía F.',
  status: 'OFFERING',
  deadlineAt: '2026-10-03T06:50:00+02:00',
}

describe('ActiveRescueBanner', () => {
  it('shows who is absent and the countdown to the deadline', () => {
    renderWithProviders(
      <ActiveRescueBanner rescue={rescue} now={new Date('2026-10-03T06:30:00+02:00')} />,
    )
    expect(screen.getByText(/Lucía F\./)).toBeInTheDocument()
    expect(screen.getByText('20m left')).toBeInTheDocument()
    expect(screen.getByRole('alert')).toBeInTheDocument()
  })

  it('renders on the dark House Green band with white text', () => {
    renderWithProviders(
      <ActiveRescueBanner rescue={rescue} now={new Date('2026-10-03T06:30:00+02:00')} />,
    )
    const banner = screen.getByRole('alert')
    expect(banner).toHaveClass('bg-green-house')
    expect(banner).toHaveClass('text-white')
  })

  it('flags the countdown as urgent inside 5 minutes', () => {
    renderWithProviders(
      <ActiveRescueBanner rescue={rescue} now={new Date('2026-10-03T06:47:00+02:00')} />,
    )
    expect(screen.getByText('3m left')).toHaveClass('text-warning')
  })

  it('marks an overdue deadline', () => {
    renderWithProviders(
      <ActiveRescueBanner rescue={rescue} now={new Date('2026-10-03T06:55:00+02:00')} />,
    )
    expect(screen.getByText('Overdue')).toBeInTheDocument()
  })
})
