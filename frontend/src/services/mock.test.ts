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

  it('returns the full rescue detail with timeline, candidates and offers', async () => {
    const source = new MockDashboardDataSource()
    const detail = await source.getRescueDetail('rescue_001')
    expect(detail.rescue.id).toBe('rescue_001')
    expect(detail.shift.id).toBe(detail.rescue.shiftId)
    expect(detail.timeline.length).toBeGreaterThan(0)
    expect(detail.candidates.length).toBeGreaterThan(0)
    expect(detail.offers.length).toBeGreaterThan(0)
  })

  it('includes candidates excluded with stable reason codes', async () => {
    const source = new MockDashboardDataSource()
    const detail = await source.getRescueDetail('rescue_001')
    const excluded = detail.candidates.filter((c) => !c.eligible)
    expect(excluded.length).toBeGreaterThan(0)
    expect(excluded.every((c) => c.reasons.every((r) => /^[A-Z_]+$/.test(r.code)))).toBe(true)
  })

  it('throws for an unknown rescue id', async () => {
    const source = new MockDashboardDataSource()
    await expect(source.getRescueDetail('unknown')).rejects.toThrow()
  })

  it('returns pending approvals with context', async () => {
    const source = new MockDashboardDataSource()
    const approvals = await source.getPendingApprovals()
    expect(approvals.length).toBeGreaterThan(0)
    expect(approvals.every((a) => a.status === 'pending')).toBe(true)
    expect(approvals.every((a) => a.context.employeeName.length > 0)).toBe(true)
  })

  it('decides an approval and removes it from the pending inbox', async () => {
    const source = new MockDashboardDataSource()
    const [first] = await source.getPendingApprovals()
    await source.decideApproval(first.id, 'approved', 'manager_01')
    const pending = await source.getPendingApprovals()
    expect(pending.find((a) => a.id === first.id)).toBeUndefined()
  })

  it('rejecting an approval also removes it from the pending inbox', async () => {
    const source = new MockDashboardDataSource()
    const approvals = await source.getPendingApprovals()
    const last = approvals[approvals.length - 1]
    await source.decideApproval(last.id, 'rejected', 'manager_01')
    const pending = await source.getPendingApprovals()
    expect(pending.find((a) => a.id === last.id)).toBeUndefined()
  })

  it('throws when deciding an unknown approval', async () => {
    const source = new MockDashboardDataSource()
    await expect(source.decideApproval('unknown', 'approved', 'manager_01')).rejects.toThrow()
  })
})
