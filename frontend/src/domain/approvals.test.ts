import { describe, expect, it } from 'vitest'
import type { ApprovalRequest } from './types'
import { approvalKindLabel, approvalStatusLabel, orderApprovalsByOldest } from './approvals'

function approval(overrides: Partial<ApprovalRequest> & { id: string }): ApprovalRequest {
  return {
    rescueId: 'rescue_001',
    kind: 'overtime',
    status: 'pending',
    requestedAt: '2026-10-03T06:42:00+02:00',
    context: { employeeName: 'Bruno T.', shiftTime: '07:00 – 15:00' },
    ...overrides,
  }
}

describe('approvalKindLabel', () => {
  it('maps kinds to human-readable English labels', () => {
    expect(approvalKindLabel('overtime')).toBe('Overtime')
    expect(approvalKindLabel('partial_coverage')).toBe('Partial coverage')
    expect(approvalKindLabel('schedule_change')).toBe('Schedule change')
    expect(approvalKindLabel('cancel_rescue')).toBe('Cancel rescue')
  })
})

describe('approvalStatusLabel', () => {
  it('maps statuses to human-readable English labels', () => {
    expect(approvalStatusLabel('pending')).toBe('Pending')
    expect(approvalStatusLabel('approved')).toBe('Approved')
    expect(approvalStatusLabel('rejected')).toBe('Rejected')
    expect(approvalStatusLabel('expired')).toBe('Expired')
  })
})

describe('orderApprovalsByOldest', () => {
  it('orders pending approvals oldest-first for fair review', () => {
    const approvals = [
      approval({ id: 'b', requestedAt: '2026-10-03T06:45:00+02:00' }),
      approval({ id: 'a', requestedAt: '2026-10-03T06:40:00+02:00' }),
    ]
    expect(orderApprovalsByOldest(approvals).map((x) => x.id)).toEqual(['a', 'b'])
  })

  it('does not mutate the input array', () => {
    const approvals = [approval({ id: 'b', requestedAt: '2026-10-03T06:45:00+02:00' })]
    const copy = [...approvals]
    orderApprovalsByOldest(approvals)
    expect(approvals).toEqual(copy)
  })
})
