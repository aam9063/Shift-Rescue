/**
 * Manager action: mark a shift absent and open the rescue (spec §7.5
 * `POST /api/shifts/{id}/absence`).
 *
 * The manager is the authority, so the absence needs no WhatsApp confirmation:
 * the rescue opens and the first wave goes out. The endpoint enqueues the work
 * (202), so the copy says the change applies in a moment instead of pretending
 * it is instantaneous — and the live channel is what makes the board move.
 */

import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'

import { markShiftAbsence } from '../services/api'
import { ApiError } from '../services/apiClient'
import { useTodayShifts } from '../services/hooks'
import { Button } from './ui/Button'

function describeShift(shift: { role: string; startsAt: string; endsAt: string; assigneeName: string | null }): string {
  const time = (iso: string) =>
    new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false })
  const who = shift.assigneeName ?? 'Unassigned'
  return `${shift.role} · ${time(shift.startsAt)}–${time(shift.endsAt)} · ${who}`
}

function absenceError(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 409) {
      return error.message
    }
    if (error.status === 404) {
      return 'That shift is not available for this location.'
    }
    return 'The absence could not be marked. Try again.'
  }
  return 'Cannot reach the server. Check your connection and try again.'
}

export function ReportAbsenceDialog({ dayIso, onClose }: { dayIso: string; onClose: () => void }) {
  const { shifts } = useTodayShifts(dayIso)
  const queryClient = useQueryClient()
  const [queued, setQueued] = useState<string | null>(null)

  const mutation = useMutation({
    mutationFn: (shiftId: string) => markShiftAbsence(shiftId),
    onSuccess: (_accepted, shiftId) => {
      setQueued(shiftId)
      // The worker opens the rescue: refetch the board, and let the live channel
      // deliver whatever else changes.
      void queryClient.invalidateQueries({ queryKey: ['shifts'] })
      void queryClient.invalidateQueries({ queryKey: ['rescues'] })
    },
  })

  const open = (shifts ?? []).filter((shift) => shift.status === 'scheduled')
  const busy = mutation.isPending

  return (
    <div
      role="dialog"
      aria-label="Report absence"
      className="fixed inset-0 z-30 flex items-end justify-center bg-black/40 p-4 md:items-center"
    >
      <div className="w-full max-w-xl rounded-card bg-surface p-5 shadow-card">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 className="font-serif text-2xl font-semibold tracking-tight text-green-starbucks">
              Report absence
            </h2>
            <p className="mt-1 text-sm tracking-tight text-text-secondary">
              The rescue opens right away and the first wave of offers goes out. No
              confirmation is needed from the employee.
            </p>
          </div>
          <Button variant="secondary" onClick={onClose}>
            Close
          </Button>
        </div>

        {queued !== null ? (
          <p role="status" className="mt-4 rounded-card bg-green-light px-4 py-3 text-sm tracking-tight">
            Absence accepted: the rescue is opening. The board updates in a moment
            (the worker applies it).
          </p>
        ) : null}

        {mutation.isError ? (
          <p role="alert" className="mt-4 rounded-card bg-error/10 px-4 py-3 text-sm tracking-tight text-error">
            {absenceError(mutation.error)}
          </p>
        ) : null}

        <ul aria-label="Today's shifts" className="mt-4 divide-y divide-black/5">
          {open.map((shift) => (
            <li key={shift.id} className="flex flex-wrap items-center justify-between gap-3 py-3">
              <span className="text-sm tracking-tight text-text-primary">{describeShift(shift)}</span>
              <Button
                variant="secondary"
                disabled={busy}
                onClick={() => mutation.mutate(shift.id)}
                className="pointer-coarse:min-h-11"
              >
                Mark absent
              </Button>
            </li>
          ))}
        </ul>
        {open.length === 0 ? (
          <p className="mt-4 text-sm tracking-tight text-text-secondary">
            No shift of today is still scheduled: everything is already absent,
            covered or open.
          </p>
        ) : null}
      </div>
    </div>
  )
}
