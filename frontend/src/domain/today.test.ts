import { describe, expect, it } from 'vitest'
import type { ApprovalRequest, RescueCase, Shift } from './types'
import {
  buildTodayRows,
  formatCountdownParts,
  formatShiftTime,
  formatCountdown,
} from './today'
import { RoleOrder } from './types'

const TZ = 'Europe/Madrid'

function shift(overrides: Partial<Shift> & { id: string }): Shift {
  return {
    locationId: 'la-terraza-del-puerto',
    role: 'floor',
    startsAt: '2026-10-03T07:00:00+02:00',
    endsAt: '2026-10-03T15:00:00+02:00',
    assigneeName: null,
    status: 'scheduled',
    ...overrides,
  }
}

describe('formatShiftTime', () => {
  it('renders a 24h time range in the location timezone', () => {
    const s = shift({ id: 's1', startsAt: '2026-10-03T07:00:00+02:00', endsAt: '2026-10-03T15:00:00+02:00' })
    expect(formatShiftTime(s, TZ)).toBe('07:00 – 15:00')
  })

  it('handles shifts crossing midnight', () => {
    const s = shift({ id: 's1', startsAt: '2026-10-03T22:00:00+02:00', endsAt: '2026-10-04T01:00:00+02:00' })
    expect(formatShiftTime(s, TZ)).toBe('22:00 – 01:00')
  })
})

describe('formatCountdown', () => {
  it('renders minutes and seconds remaining as MM:SS', () => {
    const now = new Date('2026-10-03T06:45:48+02:00')
    expect(formatCountdown('2026-10-03T06:50:00+02:00', now)).toBe('04:12')
  })

  it('pads single-digit minutes', () => {
    const now = new Date('2026-10-03T06:49:05+02:00')
    expect(formatCountdown('2026-10-03T06:50:00+02:00', now)).toBe('00:55')
  })

  it('clamps to 00:00 once the deadline has passed', () => {
    const now = new Date('2026-10-03T06:51:00+02:00')
    expect(formatCountdown('2026-10-03T06:50:00+02:00', now)).toBe('00:00')
  })
})

describe('formatCountdownParts (adaptive units)', () => {
  it('keeps MM:SS below one hour', () => {
    const now = new Date('2026-10-03T06:45:48+02:00')
    expect(formatCountdownParts('2026-10-03T06:50:00+02:00', now)).toEqual({
      text: '04:12',
      caption: 'minutes left',
    })
  })

  it('switches to hours above one hour', () => {
    const now = new Date('2026-10-03T06:45:48+02:00')
    expect(formatCountdownParts('2026-10-03T10:15:00+02:00', now)).toEqual({
      text: '3h 29m',
      caption: 'hours left',
    })
  })

  it('switches to days above 48 hours', () => {
    const now = new Date('2026-10-03T06:45:48+02:00')
    expect(formatCountdownParts('2026-10-05T12:45:48+02:00', now)).toEqual({
      text: '2d 6h',
      caption: 'days left',
    })
  })

  it('clamps to zero once expired', () => {
    const now = new Date('2026-10-03T07:51:00+02:00')
    expect(formatCountdownParts('2026-10-03T07:50:00+02:00', now)).toEqual({
      text: '00:00',
      caption: 'minutes left',
    })
  })
})

describe('buildTodayRows', () => {
  const openShift: Shift = { id: 'shift_open', locationId: 'loc', role: 'kitchen', startsAt: '2026-10-03T15:00:00+02:00', endsAt: '2026-10-03T23:00:00+02:00', assigneeName: null, status: 'open' }
  const absentShift: Shift = { id: 'shift_absent', locationId: 'loc', role: 'floor', startsAt: '2026-10-03T15:00:00+02:00', endsAt: '2026-10-03T23:00:00+02:00', assigneeName: 'Iker M.', status: 'absent' }
  const coveredShift: Shift = { id: 'shift_covered', locationId: 'loc', role: 'bar', startsAt: '2026-10-03T07:00:00+02:00', endsAt: '2026-10-03T15:00:00+02:00', assigneeName: 'Marta L.', status: 'covered' }
  const scheduledShift: Shift = { id: 'shift_sched', locationId: 'loc', role: 'supervisor', startsAt: '2026-10-03T11:00:00+02:00', endsAt: '2026-10-03T19:00:00+02:00', assigneeName: 'Javier P.', status: 'scheduled' }
  const seeking: RescueCase = { id: 'r1', shiftId: 'shift_absent', absentEmployeeName: 'Iker M.', status: 'OFFERING', deadlineAt: '2026-10-03T15:00:00+02:00' }
  const approval: ApprovalRequest = { id: 'a1', rescueId: 'r1', kind: 'overtime', status: 'pending', requestedAt: '2026-10-03T06:43:00+02:00', context: { employeeName: 'Sonia P.', shiftTime: '19:00 – 23:00' } }

  it('derives one row per shift carrying the four grouping states of the board', () => {
    const rows = buildTodayRows(
      [openShift, absentShift, coveredShift, scheduledShift],
      [seeking],
      [],
      RoleOrder,
    )
    expect(rows.map((row) => [row.shift.id, row.state])).toEqual([
      ['shift_open', 'uncovered'],
      ['shift_absent', 'searching'],
      ['shift_covered', 'covered'],
      ['shift_sched', 'covered'],
    ])
  })

  it('keeps the board column order: uncovered, searching, awaiting approval, covered', () => {
    const awaiting: RescueCase = { ...seeking, id: 'r2', shiftId: 'shift_open', status: 'AWAITING_APPROVAL' }
    const rows = buildTodayRows(
      [scheduledShift, openShift, absentShift],
      [seeking, awaiting],
      [],
      RoleOrder,
    )
    expect(rows.map((row) => row.state)).toEqual([
      'searching',
      'awaiting-approval',
      'covered',
    ])
  })

  it('attaches the active rescue and its pending approvals to the shift row', () => {
    const rows = buildTodayRows([absentShift], [seeking], [approval], RoleOrder)
    expect(rows[0].rescue).toEqual(seeking)
    expect(rows[0].approvals).toEqual([approval])
  })

  it('excludes shifts with an active rescue from the uncovered state', () => {
    const awaiting: RescueCase = { ...seeking, id: 'r2', shiftId: 'shift_open', status: 'AWAITING_APPROVAL' }
    const rows = buildTodayRows([openShift], [awaiting], [], RoleOrder)
    expect(rows[0].state).toBe('awaiting-approval')
  })

  it('treats an absent shift with no active rescue as uncovered', () => {
    const rows = buildTodayRows([absentShift], [], [], RoleOrder)
    expect(rows[0].state).toBe('uncovered')
  })

  it('counts a scheduled shift as covered (staffed, not rescued)', () => {
    const rows = buildTodayRows([scheduledShift], [], [], RoleOrder)
    expect(rows[0].state).toBe('covered')
    expect(rows[0].rescue).toBeUndefined()
  })

  it('ignores settled approvals', () => {
    const decided: ApprovalRequest = { ...approval, status: 'approved' }
    const rows = buildTodayRows([absentShift], [seeking], [decided], RoleOrder)
    expect(rows[0].approvals).toEqual([])
  })

  // --- escalated rescues (the manager was notified; the row must say so) ------

  const escalated: RescueCase = {
    id: 'r3',
    shiftId: 'shift_absent',
    absentEmployeeName: 'Iker M.',
    status: 'ESCALATED',
    deadlineAt: '2026-10-03T15:00:00+02:00',
  }

  it('marks a shift whose rescue was escalated as escalated, never uncovered', () => {
    const rows = buildTodayRows([absentShift], [escalated], [], RoleOrder)
    expect(rows[0].state).toBe('escalated')
    expect(rows[0].rescue).toEqual(escalated)
  })

  it('keeps a covered shift covered even when its earlier case was escalated', () => {
    const coveredAfterEscalation: Shift = { ...coveredShift, id: 'shift_absent' }
    const rows = buildTodayRows([coveredAfterEscalation], [escalated], [], RoleOrder)
    expect(rows[0].state).toBe('covered')
    // The case stays attached so the Actions column can still open its detail.
    expect(rows[0].rescue).toEqual(escalated)
  })

  it('picks the most recent case per shift by openedAt', () => {
    const olderEscalated: RescueCase = {
      ...escalated,
      id: 'r_old',
      status: 'ESCALATED',
      openedAt: '2026-10-03T06:30:00+02:00',
    }
    const newerOffering: RescueCase = {
      ...seeking,
      id: 'r_new',
      status: 'OFFERING',
      openedAt: '2026-10-03T06:40:00+02:00',
    }
    const rows = buildTodayRows([absentShift], [olderEscalated, newerOffering], [], RoleOrder)
    expect(rows[0].state).toBe('searching')
    expect(rows[0].rescue).toEqual(newerOffering)
  })

  it('keeps an open case attached to an uncovered-looking row for the detail action', () => {
    // An OPEN case (absence reported, not confirmed) has no offers yet, so the
    // rescue cell stays honest — but a case exists and the row carries it.
    const openCase: RescueCase = { ...seeking, status: 'OPEN' }
    const rows = buildTodayRows([absentShift], [openCase], [], RoleOrder)
    expect(rows[0].state).toBe('uncovered')
    expect(rows[0].rescue).toEqual(openCase)
  })
})
