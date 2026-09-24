import type { AuditEvent, AuditEventType, CandidateResult } from './types'

/**
 * Pure helpers for the Rescue detail screen. No React, no I/O, no `Date.now()`.
 */

export function sortEventsChronologically(events: AuditEvent[]): AuditEvent[] {
  return [...events].sort((a, b) =>
    a.createdAt.localeCompare(b.createdAt) || a.id.localeCompare(b.id),
  )
}

const eventLabels: Record<AuditEventType, string> = {
  RESCUE_OPENED: 'Rescue opened',
  ABSENCE_MARKED: 'Absence marked in HRIS',
  CANDIDATES_COMPUTED: 'Candidates computed',
  OFFER_SENT: 'Offer sent',
  OFFER_DECLINED: 'Offer declined',
  OFFER_ACCEPTED: 'Offer accepted',
  OFFER_EXPIRED: 'Offer expired',
  APPROVAL_REQUESTED: 'Manager approval requested',
  APPROVAL_DECIDED: 'Manager decision received',
  SHIFT_ASSIGNED: 'Shift assigned in HRIS',
  ESCALATED: 'Escalated to manager',
  CANCELLED: 'Rescue cancelled',
}

export function eventLabel(type: AuditEventType): string {
  return eventLabels[type]
}

/**
 * Score descending; ties broken by employee id so tests and renders are
 * reproducible (spec §5.2 requires deterministic tie-breaks).
 */
export function orderCandidates(candidates: CandidateResult[]): CandidateResult[] {
  return [...candidates].sort(
    (a, b) => b.score - a.score || a.employeeId.localeCompare(b.employeeId),
  )
}
