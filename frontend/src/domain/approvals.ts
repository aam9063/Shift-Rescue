import type { ApprovalKind, ApprovalRequest, ApprovalStatus } from './types'

/**
 * Pure helpers for the Approvals screen. No React, no I/O, no `Date.now()`.
 */

const kindLabels: Record<ApprovalKind, string> = {
  overtime: 'Overtime',
  partial_coverage: 'Partial coverage',
  schedule_change: 'Schedule change',
  cancel_rescue: 'Cancel rescue',
}

const statusLabels: Record<ApprovalStatus, string> = {
  pending: 'Pending',
  approved: 'Approved',
  rejected: 'Rejected',
  expired: 'Expired',
}

export function approvalKindLabel(kind: ApprovalKind): string {
  return kindLabels[kind]
}

export function approvalStatusLabel(status: ApprovalStatus): string {
  return statusLabels[status]
}

/** Oldest first, so managers review in fair order. */
export function orderApprovalsByOldest(approvals: ApprovalRequest[]): ApprovalRequest[] {
  return [...approvals].sort(
    (a, b) => a.requestedAt.localeCompare(b.requestedAt) || a.id.localeCompare(b.id),
  )
}
