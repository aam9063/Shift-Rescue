import type { ApprovalRequest, ApprovalStatus, RescueCase, RescueDetail, Shift } from '../domain/types'

/**
 * Mock data mirroring the user's UI mockups (frontend/public/img/*.png).
 * Day under simulation: 2026-10-03 at La Terraza del Puerto.
 */
export interface DashboardDataSource {
  getShifts(dayIso: string): Promise<Shift[]>
  getActiveRescues(): Promise<RescueCase[]>
  getRescueDetail(rescueId: string): Promise<RescueDetail>
  getPendingApprovals(): Promise<ApprovalRequest[]>
  decideApproval(
    id: string,
    decision: Exclude<ApprovalStatus, 'pending' | 'expired'>,
    decidedBy: string,
  ): Promise<void>
}

const LOCATION_ID = 'la-terraza-del-puerto'

const mockShifts: Shift[] = [
  // Covered today (kanban column 4)
  { id: 'shift_bar_01', locationId: LOCATION_ID, role: 'bar', startsAt: '2026-10-03T07:00:00+02:00', endsAt: '2026-10-03T15:00:00+02:00', assigneeName: 'Marta L.', status: 'covered' },
  { id: 'shift_kitchen_02', locationId: LOCATION_ID, role: 'kitchen', startsAt: '2026-10-03T23:00:00+02:00', endsAt: '2026-10-04T07:00:00+02:00', assigneeName: 'Pau S.', status: 'covered' },
  // Uncovered (kanban column 1): open with no active rescue
  { id: 'shift_kitchen_01', locationId: LOCATION_ID, role: 'kitchen', startsAt: '2026-10-03T15:00:00+02:00', endsAt: '2026-10-03T23:00:00+02:00', assigneeName: null, status: 'open' },
  // Absent with active rescue -> Searching (kanban column 2)
  { id: 'shift_floor_01', locationId: LOCATION_ID, role: 'floor', startsAt: '2026-10-03T15:00:00+02:00', endsAt: '2026-10-03T23:00:00+02:00', assigneeName: 'Iker M.', status: 'absent' },
  // Shift with a conditional acceptance -> Needs your approval (kanban column 3)
  { id: 'shift_bar_02', locationId: LOCATION_ID, role: 'bar', startsAt: '2026-10-03T19:00:00+02:00', endsAt: '2026-10-03T23:00:00+02:00', assigneeName: 'Sonia P.', status: 'scheduled' },
  // Regular scheduled shifts
  { id: 'shift_floor_02', locationId: LOCATION_ID, role: 'floor', startsAt: '2026-10-03T07:00:00+02:00', endsAt: '2026-10-03T15:00:00+02:00', assigneeName: 'María G.', status: 'scheduled' },
  { id: 'shift_cleaning_01', locationId: LOCATION_ID, role: 'cleaning', startsAt: '2026-10-03T06:00:00+02:00', endsAt: '2026-10-03T10:00:00+02:00', assigneeName: 'Rosa L.', status: 'scheduled' },
  { id: 'shift_supervisor_01', locationId: LOCATION_ID, role: 'supervisor', startsAt: '2026-10-03T11:00:00+02:00', endsAt: '2026-10-03T19:00:00+02:00', assigneeName: 'Javier P.', status: 'scheduled' },
]

const mockRescues: RescueCase[] = [
  {
    id: 'rescue_001',
    shiftId: 'shift_floor_01',
    absentEmployeeName: 'Iker M.',
    status: 'OFFERING',
    openedAt: '2026-10-03T06:40:00+02:00',
    // Deadline = opened_at + 10 min (spec §5.3): 04:12 left at 06:45:48.
    deadlineAt: '2026-10-03T06:50:00+02:00',
    waveCurrent: 2,
    waveTotal: 3,
    offerPreviews: [
      { employeeName: 'Marta L.', status: 'pending' },
      { employeeName: 'Sonia P.', status: 'pending' },
      { employeeName: 'Ivan R.', status: 'declined' },
    ],
  },
  {
    id: 'rescue_002',
    shiftId: 'shift_bar_02',
    absentEmployeeName: 'Nerea V.',
    status: 'AWAITING_APPROVAL',
    openedAt: '2026-10-03T06:42:00+02:00',
    deadlineAt: '2026-10-03T06:57:00+02:00',
    offerPreviews: [{ employeeName: 'Sonia P.', status: 'pending' }],
  },
]

const mockApprovals: ApprovalRequest[] = [
  {
    id: 'appr_001',
    rescueId: 'rescue_002',
    kind: 'partial_coverage',
    status: 'pending',
    requestedAt: '2026-10-03T06:43:00+02:00',
    expiresAt: '2026-10-03T06:57:00+02:00',
    context: {
      employeeName: 'Sonia P.',
      shiftTime: '19:00 – 23:00',
      detail: 'Can cover from 19:00 to 22:00 (partial)',
    },
  },
  {
    id: 'appr_002',
    rescueId: 'rescue_001',
    kind: 'overtime',
    status: 'pending',
    requestedAt: '2026-10-03T06:41:30+02:00',
    expiresAt: '2026-10-03T06:50:00+02:00',
    context: {
      employeeName: 'Bruno T.',
      shiftTime: '15:00 – 23:00',
      detail: 'Covering would exceed contracted 30h weekly hours',
    },
  },
]

const rescueTimeline = (rescueId: string) => [
  { id: 'evt_1', rescueId, type: 'RESCUE_OPENED' as const, actor: 'system', createdAt: '2026-10-03T06:40:00+02:00' },
  { id: 'evt_2', rescueId, type: 'CANDIDATES_COMPUTED' as const, actor: 'system', createdAt: '2026-10-03T06:40:05+02:00' },
  { id: 'evt_3', rescueId, type: 'OFFER_SENT' as const, actor: 'system', createdAt: '2026-10-03T06:41:00+02:00' },
  { id: 'evt_4', rescueId, type: 'OFFER_DECLINED' as const, actor: 'employee:emp_ivan_r', createdAt: '2026-10-03T06:44:00+02:00', interpretedByAi: true },
  { id: 'evt_5', rescueId, type: 'OFFER_SENT' as const, actor: 'system', createdAt: '2026-10-03T06:45:00+02:00' },
]

const rescueCandidates = [
  { employeeId: 'emp_marta_l', name: 'Marta L.', score: 0.82, eligible: true, requiresApproval: false, reasons: [] },
  { employeeId: 'emp_ivan_r', name: 'Ivan R.', score: 0.8, eligible: true, requiresApproval: false, reasons: [] },
  { employeeId: 'emp_sonia_p', name: 'Sonia P.', score: 0.77, eligible: true, requiresApproval: false, reasons: [] },
  { employeeId: 'emp_lucia_g', name: 'Lucía G.', score: 0.71, eligible: true, requiresApproval: false, reasons: [] },
  { employeeId: 'emp_diego_f', name: 'Diego F.', score: 0.65, eligible: true, requiresApproval: false, reasons: [] },
  { employeeId: 'emp_pau_s', name: 'Pau S.', score: 0.0, eligible: false, requiresApproval: false, reasons: [{ code: 'MAX_WEEKLY_HOURS', message: 'Would exceed max weekly hours' }] },
  { employeeId: 'emp_ainhoa_t', name: 'Ainhoa T.', score: 0.0, eligible: false, requiresApproval: false, reasons: [{ code: 'REST_VIOLATION', message: 'Only 7.5h rest since last shift' }] },
]

const rescueOffers = (rescueId: string) => [
  { id: 'offer_1', rescueId, employeeName: 'Marta L.', waveNumber: 1, status: 'PENDING' as const, sentAt: '2026-10-03T06:41:00+02:00', expiresAt: '2026-10-03T06:51:00+02:00' },
  { id: 'offer_2', rescueId, employeeName: 'Sonia P.', waveNumber: 1, status: 'PENDING' as const, sentAt: '2026-10-03T06:41:00+02:00', expiresAt: '2026-10-03T06:51:00+02:00' },
  { id: 'offer_3', rescueId, employeeName: 'Ivan R.', waveNumber: 1, status: 'DECLINED' as const, sentAt: '2026-10-03T06:41:00+02:00', expiresAt: '2026-10-03T06:51:00+02:00' },
  { id: 'offer_4', rescueId, employeeName: 'Lucía G.', waveNumber: 2, status: 'PENDING' as const, sentAt: '2026-10-03T06:45:00+02:00', expiresAt: '2026-10-03T06:55:00+02:00' },
  { id: 'offer_5', rescueId, employeeName: 'Diego F.', waveNumber: 2, status: 'PENDING' as const, sentAt: '2026-10-03T06:45:00+02:00', expiresAt: '2026-10-03T06:55:00+02:00' },
]

export class MockDashboardDataSource implements DashboardDataSource {
  async getShifts(dayIso: string): Promise<Shift[]> {
    return mockShifts.filter((s) => s.startsAt.slice(0, 10) === dayIso)
  }

  async getActiveRescues(): Promise<RescueCase[]> {
    return mockRescues
  }

  async getRescueDetail(rescueId: string): Promise<RescueDetail> {
    const rescue = mockRescues.find((r) => r.id === rescueId)
    if (!rescue) {
      throw new Error(`Unknown rescue: ${rescueId}`)
    }
    const shift = mockShifts.find((s) => s.id === rescue.shiftId)
    if (!shift) {
      throw new Error(`Unknown shift for rescue: ${rescueId}`)
    }
    return {
      rescue,
      shift,
      timeline: rescueTimeline(rescueId),
      candidates: rescueCandidates,
      offers: rescueOffers(rescueId),
    }
  }

  async getPendingApprovals(): Promise<ApprovalRequest[]> {
    return mockApprovals.filter((a) => a.status === 'pending')
  }

  async decideApproval(
    id: string,
    decision: Exclude<ApprovalStatus, 'pending' | 'expired'>,
    decidedBy: string,
  ): Promise<void> {
    const approval = mockApprovals.find((a) => a.id === id)
    if (!approval) {
      throw new Error(`Unknown approval: ${id}`)
    }
    approval.status = decision
    approval.decidedBy = decidedBy
    approval.decidedAt = '2026-10-03T06:46:00+02:00'
  }
}
