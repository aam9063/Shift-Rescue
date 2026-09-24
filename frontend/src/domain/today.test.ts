import { describe, expect, it } from 'vitest'
import type { ApprovalRequest, RescueCase, Shift } from './types'
import {
  buildTodayColumns,
  formatCountdownParts,
  minutesUntil,
  formatShiftTime,
  formatCountdown,
  groupShiftsByRole,
  rescueCountdown,
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

function rescue(overrides: Partial<RescueCase> & { id: string }): RescueCase {
  return {
    shiftId: 'shift_1',
    absentEmployeeName: 'Lucía',
    status: 'OFFERING',
    deadlineAt: '2026-10-03T07:00:00+02:00',
    ...overrides,
  }
}

describe('groupShiftsByRole', () => {
  it('groups shifts by role in the canonical kitchen-first order', () => {
    const shifts = [
      shift({ id: 's1', role: 'bar' }),
      shift({ id: 's2', role: 'kitchen' }),
      shift({ id: 's3', role: 'floor' }),
    ]
    const groups = groupShiftsByRole(shifts, RoleOrder)
    expect(groups.map((g) => g.role)).toEqual(['kitchen', 'floor', 'bar'])
  })

  it('skips roles with no shifts', () => {
    const shifts = [shift({ id: 's1', role: 'bar' })]
    const groups = groupShiftsByRole(shifts, RoleOrder)
    expect(groups.map((g) => g.role)).toEqual(['bar'])
  })

  it('keeps shifts in chronological order inside each group', () => {
    const shifts = [
      shift({ id: 'late', role: 'floor', startsAt: '2026-10-03T15:00:00+02:00' }),
      shift({ id: 'early', role: 'floor', startsAt: '2026-10-03T07:00:00+02:00' }),
    ]
    const groups = groupShiftsByRole(shifts, RoleOrder)
    expect(groups[0].shifts.map((s) => s.id)).toEqual(['early', 'late'])
  })
})

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

describe('minutesUntil', () => {
  it('computes whole minutes remaining between now and a deadline', () => {
    const now = new Date('2026-10-03T06:48:00+02:00')
    expect(minutesUntil('2026-10-03T07:00:00+02:00', now)).toBe(12)
  })

  it('returns negative minutes for a past deadline', () => {
    const now = new Date('2026-10-03T07:05:00+02:00')
    expect(minutesUntil('2026-10-03T07:00:00+02:00', now)).toBe(-5)
  })
})

describe('rescueCountdown', () => {
  const r = rescue({ id: 'r1', deadlineAt: '2026-10-03T07:00:00+02:00' })

  it('labels remaining minutes for a live rescue', () => {
    const now = new Date('2026-10-03T06:45:00+02:00')
    expect(rescueCountdown(r, now)).toEqual({ minutes: 15, label: '15m left', urgent: false })
  })

  it('flags urgency inside 5 minutes', () => {
    const now = new Date('2026-10-03T06:57:00+02:00')
    expect(rescueCountdown(r, now)).toEqual({ minutes: 3, label: '3m left', urgent: true })
  })

  it('marks an overdue deadline', () => {
    const now = new Date('2026-10-03T07:02:00+02:00')
    expect(rescueCountdown(r, now)).toEqual({ minutes: -2, label: 'Overdue', urgent: true })
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

describe('buildTodayColumns', () => {
  const openShift: Shift = { id: 'shift_open', locationId: 'loc', role: 'kitchen', startsAt: '2026-10-03T15:00:00+02:00', endsAt: '2026-10-03T23:00:00+02:00', assigneeName: null, status: 'open' }
  const absentShift: Shift = { id: 'shift_absent', locationId: 'loc', role: 'floor', startsAt: '2026-10-03T15:00:00+02:00', endsAt: '2026-10-03T23:00:00+02:00', assigneeName: 'Iker M.', status: 'absent' }
  const coveredShift: Shift = { id: 'shift_covered', locationId: 'loc', role: 'bar', startsAt: '2026-10-03T07:00:00+02:00', endsAt: '2026-10-03T15:00:00+02:00', assigneeName: 'Marta L.', status: 'covered' }
  const scheduledShift: Shift = { id: 'shift_sched', locationId: 'loc', role: 'supervisor', startsAt: '2026-10-03T11:00:00+02:00', endsAt: '2026-10-03T19:00:00+02:00', assigneeName: 'Javier P.', status: 'scheduled' }
  const seeking: RescueCase = { id: 'r1', shiftId: 'shift_absent', absentEmployeeName: 'Iker M.', status: 'OFFERING', deadlineAt: '2026-10-03T15:00:00+02:00' }
  const approval: ApprovalRequest = { id: 'a1', rescueId: 'r2', kind: 'partial_coverage', status: 'pending', requestedAt: '2026-10-03T06:43:00+02:00', context: { employeeName: 'Sonia P.', shiftTime: '19:00 – 23:00' } }

  it('derives the four kanban columns from shifts, rescues and approvals', () => {
    const columns = buildTodayColumns([openShift, absentShift, coveredShift, scheduledShift], [seeking], [approval])
    expect(columns.uncovered.map((s) => s.id)).toEqual(['shift_open'])
    expect(columns.seeking).toEqual([seeking])
    expect(columns.needsApproval).toEqual([approval])
    expect(columns.covered.map((s) => s.id)).toEqual(['shift_covered'])
  })

  it('excludes shifts with an active rescue from the uncovered column', () => {
    const awaiting: RescueCase = { ...seeking, id: 'r2', shiftId: 'shift_open', status: 'AWAITING_APPROVAL' }
    const columns = buildTodayColumns([openShift], [awaiting], [])
    expect(columns.uncovered).toEqual([])
  })

  it('keeps scheduled shifts out of every column', () => {
    const columns = buildTodayColumns([scheduledShift], [], [])
    expect(columns.uncovered).toEqual([])
    expect(columns.covered).toEqual([])
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
