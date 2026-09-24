import { describe, expect, it } from 'vitest'
import { MockDashboardDataSource } from './mock'

describe('MockDashboardDataSource', () => {
  it('returns today\'s shifts for La Terraza del Puerto', async () => {
    const source = new MockDashboardDataSource()
    const shifts = await source.getShifts('2026-10-03')
    expect(shifts.length).toBeGreaterThan(0)
    expect(shifts.every((s) => s.locationId === 'la-terraza-del-puerto')).toBe(true)
  })

  it('seeds one shift per role at minimum', async () => {
    const source = new MockDashboardDataSource()
    const shifts = await source.getShifts('2026-10-03')
    const roles = new Set(shifts.map((s) => s.role))
    expect(roles).toEqual(new Set(['kitchen', 'floor', 'bar', 'cleaning', 'supervisor']))
  })

  it('returns active rescues with a deadline', async () => {
    const source = new MockDashboardDataSource()
    const rescues = await source.getActiveRescues()
    expect(rescues.length).toBeGreaterThan(0)
    expect(rescues.every((r) => r.deadlineAt.length > 0)).toBe(true)
  })
})
