import type { ApprovalRequest, RescueCase, Shift, ShiftRole } from './types'

/**
 * Pure helpers for the Today screen. No React, no I/O, no `Date.now()` —
 * the current time is always injected for deterministic tests.
 */

export interface ShiftGroup {
  role: ShiftRole
  shifts: Shift[]
}

export function groupShiftsByRole(shifts: Shift[], roleOrder: readonly ShiftRole[]): ShiftGroup[] {
  const byRole = new Map<ShiftRole, Shift[]>()
  for (const s of shifts) {
    const list = byRole.get(s.role) ?? []
    list.push(s)
    byRole.set(s.role, list)
  }
  return [...byRole.entries()]
    .sort(([a], [b]) => roleOrder.indexOf(a) - roleOrder.indexOf(b))
    .map(([role, list]) => ({
      role,
      shifts: [...list].sort((a, b) => a.startsAt.localeCompare(b.startsAt)),
    }))
}

const timeFormatterCache = new Map<string, Intl.DateTimeFormat>()

function formatTime(iso: string, timeZone: string): string {
  let formatter = timeFormatterCache.get(timeZone)
  if (!formatter) {
    formatter = new Intl.DateTimeFormat('en-GB', {
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
      timeZone,
    })
    timeFormatterCache.set(timeZone, formatter)
  }
  return formatter.format(new Date(iso))
}

export function formatShiftTime(shift: Shift, timeZone: string): string {
  return `${formatTime(shift.startsAt, timeZone)} – ${formatTime(shift.endsAt, timeZone)}`
}

export function minutesUntil(isoDeadline: string, now: Date): number {
  return Math.round((new Date(isoDeadline).getTime() - now.getTime()) / 60_000)
}

export interface RescueCountdown {
  minutes: number
  label: string
  /** True when at or past the urgency threshold (5 minutes). */
  urgent: boolean
}

const URGENT_THRESHOLD_MINUTES = 5

export function rescueCountdown(rescue: RescueCase, now: Date): RescueCountdown {
  const minutes = minutesUntil(rescue.deadlineAt, now)
  if (minutes <= 0) {
    return { minutes, label: 'Overdue', urgent: true }
  }
  return {
    minutes,
    label: `${minutes}m left`,
    urgent: minutes <= URGENT_THRESHOLD_MINUTES,
  }
}

/** MM:SS remaining until the deadline, clamped at 00:00 when overdue. */
export function formatCountdown(isoDeadline: string, now: Date): string {
  const totalSeconds = Math.max(0, Math.floor((new Date(isoDeadline).getTime() - now.getTime()) / 1000))
  const minutes = Math.floor(totalSeconds / 60)
  const seconds = totalSeconds % 60
  return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`
}

export interface TodayColumns {
  /** Open shifts with no active rescue yet. */
  uncovered: Shift[]
  /** Rescues actively offering to candidates. */
  seeking: RescueCase[]
  /** Pending manager approvals. */
  needsApproval: ApprovalRequest[]
  /** Shifts covered today. */
  covered: Shift[]
}

const ACTIVE_RESCUE_STATUSES = new Set(['OFFERING', 'AWAITING_APPROVAL'])

/** Derives the Today kanban columns (user mockup layout). Pure. */
export function buildTodayColumns(
  shifts: Shift[],
  rescues: RescueCase[],
  approvals: ApprovalRequest[],
): TodayColumns {
  const shiftsWithRescue = new Set(
    rescues.filter((r) => ACTIVE_RESCUE_STATUSES.has(r.status)).map((r) => r.shiftId),
  )
  return {
    uncovered: shifts.filter((s) => s.status === 'open' && !shiftsWithRescue.has(s.id)),
    seeking: rescues.filter((r) => r.status === 'OFFERING'),
    needsApproval: approvals.filter((a) => a.status === 'pending'),
    // Database vocabulary: `scheduled` = staffed normally (a normal day's rota,
  // assigned and untouched); `covered` = filled by a rescue. Both mean a
  // person is on the shift, so both count toward "Covered today".
  covered: shifts.filter((s) => s.status === 'covered' || s.status === 'scheduled'),
  }
}

export interface CountdownParts {
  text: string
  caption: string
}

/**
 * Adaptive countdown for rescue deadlines: the rescue window lives in
 * minutes (spec 5.3: deadline = shift start - 30 min), but when viewing a
 * deadline hours or days away, MM:SS is unreadable. Units scale with the
 * remaining time; only the final hour ticks seconds.
 */
export function formatCountdownParts(isoDeadline: string, now: Date): CountdownParts {
  const msLeft = new Date(isoDeadline).getTime() - now.getTime()
  const totalSeconds = Math.max(0, Math.floor(msLeft / 1000))
  if (totalSeconds < 3600) {
    return { text: formatCountdown(isoDeadline, now), caption: 'minutes left' }
  }
  const totalMinutes = Math.floor(totalSeconds / 60)
  if (totalMinutes < 48 * 60) {
    const hours = Math.floor(totalMinutes / 60)
    const minutes = totalMinutes % 60
    return { text: `${hours}h ${String(minutes).padStart(2, '0')}m`, caption: 'hours left' }
  }
  const hours = Math.floor(totalMinutes / 60)
  const days = Math.floor(hours / 24)
  return { text: `${days}d ${hours % 24}h`, caption: 'days left' }
}
