import { describe, expect, it } from 'vitest'
import type { RescueCase, Shift } from './types'
import {
  minutesUntil,
  formatShiftTime,
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
