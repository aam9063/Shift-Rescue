/**
 * Frontend domain types for the manager dashboard.
 * Mirrors the backend entities from spec §4.1 (RescueCase, Shift, Employee).
 * Kept minimal per slice; extended as screens land.
 */

export const SHIFT_ROLES = ['kitchen', 'floor', 'bar', 'cleaning', 'supervisor'] as const

export type ShiftRole = (typeof SHIFT_ROLES)[number]

/** Canonical display order for the Today screen: kitchen first. */
export const RoleOrder: readonly ShiftRole[] = SHIFT_ROLES

export type ShiftStatus = 'scheduled' | 'absent' | 'open' | 'covered'

export interface Shift {
  id: string
  locationId: string
  role: ShiftRole
  startsAt: string
  endsAt: string
  /** Display name of the assigned employee; null when the shift is open. */
  assigneeName: string | null
  status: ShiftStatus
}

export type RescueStatus = 'OPEN' | 'OFFERING' | 'AWAITING_APPROVAL' | 'COVERED' | 'ESCALATED'

export interface RescueCase {
  id: string
  shiftId: string
  /** Display name of the absent employee; health details never reach the dashboard (spec §10). */
  absentEmployeeName: string
  status: RescueStatus
  deadlineAt: string
}
