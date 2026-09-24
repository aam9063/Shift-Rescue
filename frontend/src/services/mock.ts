import type { RescueCase, Shift } from '../domain/types'

/**
 * Data source abstraction for the dashboard. Today it is satisfied by mock
 * data; the `manager-dashboard` later slices replace the implementation with
 * the REST API client without touching components (they only see this
 * interface through query hooks).
 */
export interface DashboardDataSource {
  getShifts(dayIso: string): Promise<Shift[]>
  getActiveRescues(): Promise<RescueCase[]>
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

export class MockDashboardDataSource implements DashboardDataSource {
  async getShifts(dayIso: string): Promise<Shift[]> {
    return mockShifts.filter((s) => s.startsAt.slice(0, 10) === dayIso)
  }

  async getActiveRescues(): Promise<RescueCase[]> {
    return mockRescues
  }
}
