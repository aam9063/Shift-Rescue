/**
 * Manager action: mark an absence from the dashboard (spec §7.5).
 *
 * The dialog lists today's still-scheduled shifts and posts the chosen one. The
 * endpoint enqueues the work, so the copy must not claim the rescue is already
 * open; a refusal (409) has to reach the screen with the server's reason.
 */

import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { ReportAbsenceDialog } from './ReportAbsenceDialog'
import { renderWithProviders } from '../test/renderWithProviders'
import { ApiError } from '../services/apiClient'

const markShiftAbsence = vi.fn()
vi.mock('../services/api', () => ({
  markShiftAbsence: (shiftId: string) => markShiftAbsence(shiftId),
}))

const DAY = '2026-10-03'

afterEach(() => {
  markShiftAbsence.mockReset()
})

describe('ReportAbsenceDialog', () => {
  it('lists the shifts still scheduled and marks the chosen one absent', async () => {
    markShiftAbsence.mockResolvedValue({ status: 'accepted', id: 'shift_x' })
    const user = userEvent.setup()
    renderWithProviders(<ReportAbsenceDialog dayIso={DAY} onClose={() => {}} />)

    const list = await screen.findByRole('list', { name: "Today's shifts" })
    const markButtons = await within(list).findAllByRole('button', { name: 'Mark absent' })
    expect(markButtons.length).toBeGreaterThan(0)

    await user.click(markButtons[0])

    await waitFor(() => expect(markShiftAbsence).toHaveBeenCalledTimes(1))
    // The copy is honest about the 202: the worker applies it in a moment.
    expect(
      await screen.findByText(/the rescue is opening/i),
    ).toBeInTheDocument()
  })

  it('shows the server refusal when the shift already has a rescue', async () => {
    markShiftAbsence.mockRejectedValue(
      new ApiError(409, 'That shift already has a rescue running.'),
    )
    const user = userEvent.setup()
    renderWithProviders(<ReportAbsenceDialog dayIso={DAY} onClose={() => {}} />)

    const list = await screen.findByRole('list', { name: "Today's shifts" })
    const [first] = await within(list).findAllByRole('button', { name: 'Mark absent' })
    await user.click(first)

    expect(await screen.findByRole('alert')).toHaveTextContent(/already has a rescue/i)
  })

  it('explains a shift that is not available', async () => {
    markShiftAbsence.mockRejectedValue(new ApiError(404, 'Shift not found'))
    const user = userEvent.setup()
    renderWithProviders(<ReportAbsenceDialog dayIso={DAY} onClose={() => {}} />)

    const list = await screen.findByRole('list', { name: "Today's shifts" })
    const [first] = await within(list).findAllByRole('button', { name: 'Mark absent' })
    await user.click(first)

    expect(await screen.findByRole('alert')).toHaveTextContent(/not available for this location/i)
  })
})
