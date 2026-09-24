import type { ApprovalRequest, ApprovalStatus, RescueCase, RescueDetail, Shift } from '../domain/types'

/**
 * Data source abstraction for the dashboard. Today it is satisfied by mock
 * data; the `manager-dashboard` later slices replace the implementation with
 * the REST API client without touching components (they only see this
 * interface through query hooks).
 */
export interface DashboardDataSource {
  getShifts(dayIso: string): Promise<Shift[]>
  getActiveRescues(): Promise<RescueCase[]>
  getRescueDetail(rescueId: string): Promise<RescueDetail>
  getPendingApprovals(): Promise<ApprovalRequest[]>
  decideApproval(id: string, decision: Exclude<ApprovalStatus, 'pending' | 'expired'>, decidedBy: string): Promise<void>
}

const LOCATION_ID = 'la-terraza-del-puerto'

const mockShifts: Shift[] = [
  { id: 'shift_kitchen_01', locationId: LOCATION_ID, role: 'kitchen', startsAt: '2026-10-03T07:00:00+02:00', endsAt: '2026-10-03T15:00:00+02:00', assigneeName: 'Carlos M.', status: 'covered' },
  { id: 'shift_kitchen_02', locationId: LOCATION_ID, role: 'kitchen', startsAt: '2026-10-03T15:00:00+02:00', endsAt: '2026-10-03T23:00:00+02:00', assigneeName: 'Diego R.', status: 'scheduled' },
  { id: 'shift_floor_01', locationId: LOCATION_ID, role: 'floor', startsAt: '2026-10-03T07:00:00+02:00', endsAt: '2026-10-03T15:00:00+02:00', assigneeName: 'Lucía F.', status: 'absent' },
  { id: 'shift_floor_02', locationId: LOCATION_ID, role: 'floor', startsAt: '2026-10-03T07:00:00+02:00', endsAt: '2026-10-03T15:00:00+02:00', assigneeName: 'María G.', status: 'scheduled' },
  { id: 'shift_floor_03', locationId: LOCATION_ID, role: 'floor', startsAt: '2026-10-03T15:00:00+02:00', endsAt: '2026-10-03T23:00:00+02:00', assigneeName: null, status: 'open' },
  { id: 'shift_bar_01', locationId: LOCATION_ID, role: 'bar', startsAt: '2026-10-03T10:00:00+02:00', endsAt: '2026-10-03T18:00:00+02:00', assigneeName: 'Pablo S.', status: 'scheduled' },
  { id: 'shift_bar_02', locationId: LOCATION_ID, role: 'bar', startsAt: '2026-10-03T18:00:00+02:00', endsAt: '2026-10-04T01:00:00+02:00', assigneeName: 'Nerea V.', status: 'covered' },
  { id: 'shift_cleaning_01', locationId: LOCATION_ID, role: 'cleaning', startsAt: '2026-10-03T06:00:00+02:00', endsAt: '2026-10-03T10:00:00+02:00', assigneeName: 'Rosa L.', status: 'scheduled' },
  { id: 'shift_supervisor_01', locationId: LOCATION_ID, role: 'supervisor', startsAt: '2026-10-03T11:00:00+02:00', endsAt: '2026-10-03T19:00:00+02:00', assigneeName: 'Javier P.', status: 'scheduled' },
]

const mockRescues: RescueCase[] = [
  {
    id: 'rescue_001',
    shiftId: 'shift_floor_01',
    absentEmployeeName: 'Lucía F.',
    status: 'OFFERING',
    // Opened 06:40, deadline fell before start - 30min, so opened_at + 10 min (spec §5.3).
    deadlineAt: '2026-10-03T06:50:00+02:00',
  },
]

const mockApprovals: ApprovalRequest[] = [
  {
    id: 'appr_001',
    rescueId: 'rescue_001',
    kind: 'overtime',
    status: 'pending',
    requestedAt: '2026-10-03T06:41:30+02:00',
    context: {
      employeeName: 'Bruno T.',
      shiftTime: '07:00 – 15:00',
      detail: 'Covering would exceed contracted 30h weekly hours',
    },
  },
  {
    id: 'appr_002',
    rescueId: 'rescue_001',
    kind: 'partial_coverage',
    status: 'pending',
    requestedAt: '2026-10-03T06:43:00+02:00',
    context: {
      employeeName: 'Iván M.',
      shiftTime: '07:00 – 15:00',
      detail: 'Proposed start 07:15 instead of 07:00',
    },
  },
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

const rescueTimeline = (rescueId: string) => [
  { id: 'evt_1', rescueId, type: 'RESCUE_OPENED' as const, actor: 'system', createdAt: '2026-10-03T06:40:00+02:00' },
  { id: 'evt_2', rescueId, type: 'ABSENCE_MARKED' as const, actor: 'system', createdAt: '2026-10-03T06:40:01+02:00' },
  { id: 'evt_3', rescueId, type: 'CANDIDATES_COMPUTED' as const, actor: 'system', createdAt: '2026-10-03T06:40:02+02:00' },
  { id: 'evt_4', rescueId, type: 'OFFER_SENT' as const, actor: 'system', createdAt: '2026-10-03T06:41:00+02:00' },
  { id: 'evt_5', rescueId, type: 'OFFER_DECLINED' as const, actor: 'employee:emp_bar_02', createdAt: '2026-10-03T06:44:00+02:00' },
]

const rescueCandidates = [
  { employeeId: 'emp_sala_02', name: 'María G.', score: 0.86, eligible: true, requiresApproval: false, reasons: [] },
  { employeeId: 'emp_sala_05', name: 'Bruno T.', score: 0.74, eligible: true, requiresApproval: true, reasons: [{ code: 'OVERTIME_APPROVAL', message: 'Would exceed contracted 30h weekly hours' }] },
  { employeeId: 'emp_bar_02', name: 'Pablo S.', score: 0.71, eligible: true, requiresApproval: false, reasons: [] },
  { employeeId: 'emp_kitchen_04', name: 'Nerea V.', score: 0.0, eligible: false, requiresApproval: false, reasons: [{ code: 'REST_VIOLATION', message: 'Last shift ended 23:30, only 7.5h rest' }] },
  { employeeId: 'emp_office_01', name: 'Sara D.', score: 0.0, eligible: false, requiresApproval: false, reasons: [{ code: 'ROLE_MISMATCH', message: 'Office staff cannot cover floor shifts' }] },
]

const rescueOffers = (rescueId: string) => [
  { id: 'offer_1', rescueId, employeeName: 'Bruno T.', waveNumber: 1, status: 'PENDING' as const, sentAt: '2026-10-03T06:41:00+02:00', expiresAt: '2026-10-03T06:51:00+02:00' },
  { id: 'offer_2', rescueId, employeeName: 'Pablo S.', waveNumber: 1, status: 'DECLINED' as const, sentAt: '2026-10-03T06:41:00+02:00', expiresAt: '2026-10-03T06:51:00+02:00' },
]
