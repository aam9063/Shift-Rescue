/**
 * Frontend domain types for the manager dashboard.
 * Mirrors the backend entities from spec §4.1 (RescueCase, Shift, Employee).
 * Kept minimal per slice; extended as screens land.
 */

export const SHIFT_ROLES = ['kitchen', 'floor', 'bar', 'cleaning', 'supervisor'] as const

export type ShiftRole = (typeof SHIFT_ROLES)[number]

/** Canonical display order for the Today screen: kitchen first. */
export const RoleOrder: readonly ShiftRole[] = SHIFT_ROLES

export type ShiftStatus = 'scheduled' | 'absent' | 'open' | 'covered'

export interface Shift {
  id: string
  locationId: string
  role: ShiftRole
  startsAt: string
  endsAt: string
  /** Display name of the assigned employee; null when the shift is open. */
  assigneeName: string | null
  status: ShiftStatus
}

export type RescueStatus = 'OPEN' | 'OFFERING' | 'AWAITING_APPROVAL' | 'COVERED' | 'ESCALATED'

export type OfferPreviewStatus = 'pending' | 'declined' | 'accepted'

export interface OfferPreview {
  employeeName: string
  status: OfferPreviewStatus
}

export interface RescueCase {
  id: string
  shiftId: string
  /** Display name of the absent employee; health details never reach the dashboard (spec §10). */
  absentEmployeeName: string
  status: RescueStatus
  deadlineAt: string
  openedAt?: string
  waveCurrent?: number
  waveTotal?: number
  /** Compact offer list for kanban cards; full detail comes from the detail query. */
  offerPreviews?: OfferPreview[]
}

/* Rescue detail entities (spec §4.1: AuditEvent, Offer, Interpretation). */

export type AuditEventType =
  | 'RESCUE_OPENED'
  | 'ABSENCE_MARKED'
  | 'CANDIDATES_COMPUTED'
  | 'OFFER_SENT'
  | 'OFFER_DECLINED'
  | 'OFFER_ACCEPTED'
  | 'OFFER_EXPIRED'
  | 'APPROVAL_REQUESTED'
  | 'APPROVAL_DECIDED'
  | 'SHIFT_ASSIGNED'
  | 'ESCALATED'
  | 'CANCELLED'

export interface AuditEvent {
  id: string
  rescueId: string
  type: AuditEventType
  actor: string
  createdAt: string
  /** True when the inbound message was interpreted by the LLM (spec section 6.2). */
  interpretedByAi?: boolean
}

export type OfferStatus = 'PENDING' | 'ACCEPTED' | 'DECLINED' | 'COUNTER_PROPOSED' | 'EXPIRED' | 'CANCELLED' | 'SUPERSEDED' | 'WITHDRAWN'

export interface Offer {
  id: string
  rescueId: string
  employeeName: string
  waveNumber: number
  status: OfferStatus
  sentAt: string
  expiresAt: string
}

export interface ExclusionReason {
  /** Stable machine code, e.g. REST_VIOLATION (spec §5.1). */
  code: string
  /** Human-readable English message for the dashboard. */
  message: string
}

export interface CandidateResult {
  employeeId: string
  name: string
  score: number
  eligible: boolean
  requiresApproval: boolean
  reasons: ExclusionReason[]
}

export interface RescueDetail {
  rescue: RescueCase
  shift: Shift
  timeline: AuditEvent[]
  candidates: CandidateResult[]
  offers: Offer[]
}

/* Approval entities (spec §4.1: ApprovalRequest). */

export type ApprovalKind = 'overtime' | 'partial_coverage' | 'schedule_change' | 'cancel_rescue'

export type ApprovalStatus = 'pending' | 'approved' | 'rejected' | 'expired'

export interface ApprovalRequest {
  id: string
  rescueId: string
  kind: ApprovalKind
  status: ApprovalStatus
  requestedAt: string
  decidedBy?: string
  decidedAt?: string
  /** Display context resolved server-side; no health details ever (spec §10). */
  context: {
    employeeName: string
    shiftTime: string
    detail?: string
  }
}
