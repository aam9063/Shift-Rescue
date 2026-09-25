import type { ApprovalRequest, RescueCase, Shift, ShiftRole } from './types'

/**
 * Pure helpers for the Today screen. No React, no I/O, no `Date.now()` —
 * the current time is always injected for deterministic tests.
 */

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

export function formatCountdown(isoDeadline: string, now: Date): string {
  const totalSeconds = Math.max(0, Math.floor((new Date(isoDeadline).getTime() - now.getTime()) / 1000))
  const minutes = Math.floor(totalSeconds / 60)
  const seconds = totalSeconds % 60
  return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`
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

// --- Today rows (one per shift; the former kanban grouping, per row) ---------

/**
 * The grouping intent of the old four-column board, kept per row:
 * - `uncovered`: nobody will work it and no rescue has tried anything yet.
 * - `searching`: a rescue is actively offering to candidates.
 * - `awaiting-approval`: a rescue is waiting on a manager decision.
 * - `escalated`: the rescue ran out of time and the manager was notified.
 * - `covered`: a person is on the shift (staffed normally or rescued).
 */
export type TodayRowState =
  | 'uncovered'
  | 'searching'
  | 'awaiting-approval'
  | 'escalated'
  | 'covered'

export interface TodayRow {
  shift: Shift
  state: TodayRowState
  /** Most recent rescue case attached to this shift (any status), if any. */
  rescue?: RescueCase
  /** Pending manager approvals for this shift's rescue, if any. */
  approvals: ApprovalRequest[]
}

/** Most recent case per shift: `openedAt` when both carry it, otherwise the
 * later array entry (the data source returns recency order). */
function isNewerRescue(candidate: RescueCase, current: RescueCase): boolean {
  if (candidate.openedAt !== undefined && current.openedAt !== undefined) {
    return candidate.openedAt > current.openedAt
  }
  return true
}

function rowState(shift: Shift, rescue: RescueCase | undefined): TodayRowState {
  const staffed = shift.status === 'covered' || shift.status === 'scheduled'
  if (rescue !== undefined) {
    switch (rescue.status) {
      case 'AWAITING_APPROVAL':
        // Manager decision pending: shown even on a staffed shift (the mock
        // demo pairs a partial-coverage approval with a scheduled shift).
        return 'awaiting-approval'
      case 'ESCALATED':
        // A staffed shift never reads as escalated: the manager (or the rota)
        // filled the shift after the escalation.
        return staffed ? 'covered' : 'escalated'
      case 'OFFERING':
        return 'searching'
      default:
        // An OPEN case (absence reported, not yet confirmed) has no offers to
        // show, so the rescue cell keeps the honest "nothing tried" caption —
        // but a case exists, so the Actions column offers the detail.
        return staffed ? 'covered' : 'uncovered'
    }
  }
  // No case at all: covered when staffed, uncovered when absent/open.
  return staffed ? 'covered' : 'uncovered'
}

/** Derives one row per shift, carrying the board's grouping intent. Pure. */
export function buildTodayRows(
  shifts: Shift[],
  rescues: RescueCase[],
  approvals: ApprovalRequest[],
  roleOrder: readonly ShiftRole[],
): TodayRow[] {
  const rescueByShift = new Map<string, RescueCase>()
  for (const rescue of rescues) {
    // Every case the data source delivers counts, active or terminal: an
    // escalated rescue must not collapse the shift back into "Uncovered".
    const current = rescueByShift.get(rescue.shiftId)
    if (current === undefined || isNewerRescue(rescue, current)) {
      rescueByShift.set(rescue.shiftId, rescue)
    }
  }
  const approvalsByRescue = new Map<string, ApprovalRequest[]>()
  for (const approval of approvals) {
    if (approval.status !== 'pending') {
      continue
    }
    const list = approvalsByRescue.get(approval.rescueId) ?? []
    list.push(approval)
    approvalsByRescue.set(approval.rescueId, list)
  }

  const stateRank: Record<TodayRowState, number> = {
    uncovered: 0,
    searching: 1,
    'awaiting-approval': 2,
    escalated: 3,
    covered: 4,
  }
  return shifts
    .map((shift): TodayRow => {
      const rescue = rescueByShift.get(shift.id)
      // Database vocabulary: `scheduled` = staffed normally (a normal day's
      // rota, assigned and untouched); `covered` = filled by a rescue. Both
      // mean a person is on the shift, so both count as covered.
      const state = rowState(shift, rescue)
      return {
        shift,
        state,
        rescue,
        approvals: rescue ? (approvalsByRescue.get(rescue.id) ?? []) : [],
      }
    })
    .sort((a, b) => {
      const byState = stateRank[a.state] - stateRank[b.state]
      if (byState !== 0) {
        return byState
      }
      const byRole = roleOrder.indexOf(a.shift.role) - roleOrder.indexOf(b.shift.role)
      if (byRole !== 0) {
        return byRole
      }
      return a.shift.startsAt.localeCompare(b.shift.startsAt)
    })
}
